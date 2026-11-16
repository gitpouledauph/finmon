"""Transactions: trades, holdings statements, and manually valued accounts (employee savings…)."""
import uuid
from datetime import date

import pandas as pd
import streamlit as st

import theme
from common import bundle, eur, get_db, invalidate, pct, profile_name
from finmon import manual, market

st.title("Transactions")

db = get_db()
online = profile_name() != "demo"
accounts = db.table("accounts")
INV_TYPES = ["pea", "cto", "crypto", "assurance_vie", "epargne_salariale"]
inv = accounts[accounts["type"].isin(INV_TYPES)]
MANUAL_TYPES = {"epargne_salariale"}

KINDS = {"Buy": "buy", "Sell": "sell", "Dividend": "dividend", "Deposit": "deposit", "Withdrawal": "withdrawal",
         "Fee": "fee", "Interest": "interest", "Reward": "reward"}
ACCOUNT_TYPES = {"Brokerage account": "cto", "PEA": "pea", "Crypto": "crypto", "Life insurance": "assurance_vie",
                 "Employee savings (PEE / PERCO)": "epargne_salariale"}
TYPE_LABEL = {"pea": "PEA", "cto": "Brokerage", "crypto": "Crypto", "assurance_vie": "Life insurance",
              "epargne_salariale": "Employee savings"}


def _n(x, dec=None):
    if x is None or x != x:
        return "—"
    txt = f"{x:,.{dec}f}" if dec is not None else (f"{x:,.6g}" if abs(x) >= 1e5 else f"{x:.6g}")
    return txt.replace(",", " ")


# ------------------------------------------------------------- account
if "tracking" not in accounts.columns:
    accounts["tracking"] = None
accounts["tracking"] = accounts["tracking"].fillna(accounts["type"].map(lambda t: "manual" if t in MANUAL_TYPES else "holdings"))
inv = accounts[accounts["type"].isin(INV_TYPES)]
TRACK = {"holdings": "Tracked holdings", "manual": "Manual value"}
view_mode = st.segmented_control("Accounts", list(TRACK.values()), default="Tracked holdings",
                                 label_visibility="collapsed", key="track_view") or "Tracked holdings"
mode_key = "manual" if view_mode == "Manual value" else "holdings"
pool = inv[inv["tracking"] == mode_key]
labels = {r.id: f"{r.name} · {TYPE_LABEL.get(r.type, r.type)}" for r in pool.itertuples()}
choice = st.selectbox("Account", list(labels) + ["__new__"],
                      format_func=lambda k: "New account…" if k == "__new__" else labels[k], key=f"acc_{mode_key}")
new_name, new_type = "", None
if choice == "__new__":
    with st.container(border=True):
        n1, n2 = st.columns(2)
        new_name = n1.text_input("Name", placeholder="e.g. Fortuneo PEA, Amundi PEE")
        new_type = ACCOUNT_TYPES[n2.selectbox("Type", list(ACCOUNT_TYPES))]
        track = st.radio("Tracking", ["holdings", "manual"], format_func=lambda k: {
            "holdings": "Tracked holdings — securities, quantities and prices are followed line by line",
            "manual": "Manual value — you enter the amount invested and the current value; nothing is tracked"}[k],
            index=1 if mode_key == "manual" or new_type == "epargne_salariale" else 0)
        if st.button("Create account", type="primary") and new_name.strip():
            acc_id = ("manuel:" if track == "manual" else "manuel-inv:") + manual.slug(new_name)
            db.upsert("accounts", pd.DataFrame([{"id": acc_id, "institution": new_name.strip(), "name": new_name.strip(),
                                                 "type": new_type, "currency": "EUR", "tracking": track}]), mode="ignore")
            invalidate()
            st.success("Account created.")
            st.rerun()
    st.stop()
acc_type = accounts.set_index("id").loc[choice, "type"]

# ============================================================= manually valued account
if mode_key == "manual":
    contrib = db.read("SELECT * FROM manual_contributions WHERE account_id = ? ORDER BY date", [choice])
    vals = db.read("SELECT date, balance FROM balance_snapshots WHERE account_id = ? ORDER BY date", [choice])
    contrib["date"] = pd.to_datetime(contrib["date"]) if not contrib.empty else contrib.get("date")
    value = float(vals["balance"].iloc[-1]) if not vals.empty else None
    invested = float(contrib["amount"].sum()) if not contrib.empty else None
    gain = value - invested if value is not None and invested else None
    k = st.columns(3)
    k[0].metric("Current value", eur(value) if value is not None else "—",
                f"as of {pd.Timestamp(vals['date'].iloc[-1]):%d %b %Y}" if value is not None else None, delta_color="off")
    k[1].metric("Invested", eur(invested) if invested is not None else "—")
    k[2].metric("Gain", eur(gain, sign=True) if gain is not None else "—",
                pct(gain / invested) if gain is not None and invested else None)

    theme.section("Update", "total invested to date + current value")
    with st.form("manual_update", border=False):
        x1, x2, x3, x4 = st.columns([1, 1.2, 1.2, 0.8], vertical_alignment="bottom")
        du = x1.date_input("Date", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
        inv_total = x2.number_input("Total invested (€)", min_value=0.0, step=100.0, format="%.2f",
                                    value=float(invested or 0.0))
        val_now = x3.number_input("Current value (€)", min_value=0.0, step=100.0, format="%.2f",
                                  value=float(value or 0.0))
        if x4.form_submit_button("Save", type="primary", width="stretch"):
            before = float(contrib.loc[contrib["date"] <= pd.Timestamp(du), "amount"].sum()) if not contrib.empty else 0.0
            delta = inv_total - before
            if abs(delta) > 0.005:
                db.upsert("manual_contributions", pd.DataFrame([{"id": uuid.uuid4().hex[:10], "account_id": choice,
                                                                 "date": du.isoformat(), "amount": delta,
                                                                 "label": "Invested total update"}]))
            if val_now > 0:
                db.upsert("balance_snapshots", pd.DataFrame([{"account_id": choice, "date": du.isoformat(),
                                                              "balance": val_now, "source": "manuel"}]), mode="replace")
            invalidate()
            st.rerun()

    theme.section("History")
    hist = pd.DataFrame({"Date": pd.to_datetime(vals["date"]), "Value": vals["balance"]}) if not vals.empty else \
        pd.DataFrame(columns=["Date", "Value"])
    if not contrib.empty:
        inv_by = contrib.groupby(contrib["date"].dt.normalize())["amount"].sum().cumsum()
        all_d = sorted(set(hist["Date"]) | set(inv_by.index))
        hist = pd.DataFrame({"Date": all_d}).merge(hist, on="Date", how="left")
        hist["Invested"] = inv_by.reindex(all_d).ffill().values
        hist["Value"] = hist["Value"].ffill()
        hist["Gain"] = hist["Value"] - hist["Invested"]
    if not hist.empty:
        ed = st.data_editor(hist.assign(Delete=False).iloc[::-1], hide_index=True, width="stretch", key="hist_ed",
                            disabled=[c for c in hist.columns],
                            column_config={"Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                           "Value": st.column_config.NumberColumn(format="%,.2f €"),
                                           "Invested": st.column_config.NumberColumn(format="%,.2f €"),
                                           "Gain": st.column_config.NumberColumn(format="%+,.2f €")})
        if st.button("Delete selected dates"):
            for r in ed[ed["Delete"]].itertuples(index=False):
                d = pd.Timestamp(r.Date).date().isoformat()
                db.execute("DELETE FROM balance_snapshots WHERE account_id = ? AND date = ?", [choice, d])
                db.execute("DELETE FROM manual_contributions WHERE account_id = ? AND date = ?", [choice, d])
            invalidate()
            st.rerun()
    st.stop()

# ============================================================= broker account
mode = st.segmented_control("Mode", ["Trade", "Holdings statement"], default="Trade",
                            label_visibility="collapsed") or "Trade"

if mode == "Holdings statement":
    if choice == "__new__":
        st.info("Create the account with a first trade.")
        st.stop()
    h1, h2 = st.columns([2, 1])
    d_h = h1.date_input("Statement date", value=date.today(), max_value=date.today(), format="DD/MM/YYYY", key="h_d")
    is_crypto = acc_type == "crypto"
    cur = bundle().portfolio.current
    cur = cur[cur["account_id"] == choice] if not cur.empty else cur
    base = pd.DataFrame({
        "ticker": [(t.split("-")[0] if is_crypto and isinstance(t, str) else t) for t in cur.get("ticker", [])],
        "isin": [i if not str(i).startswith(("CRYPTO-", "TICKER:", "IBKR:")) else "" for i in cur.get("isin", [])],
        "name": list(cur.get("name", [])), "quantity": list(cur.get("qty", [])),
    })
    st.caption("Full holdings of the account. Missing lines are treated as closed; new lines as transfers in.")
    ed_h = st.data_editor(base, num_rows="dynamic", hide_index=True, width="stretch", key=f"h_ed_{choice}",
                          column_config={
                              "ticker": st.column_config.TextColumn("Ticker" + (" (BTC, SOL…)" if is_crypto else "")),
                              "isin": st.column_config.TextColumn("ISIN"),
                              "name": st.column_config.TextColumn("Name"),
                              "quantity": st.column_config.NumberColumn("Quantity", format="%.8g", min_value=0.0)})
    if st.button("Save statement", type="primary"):
        try:
            n = manual.save_holdings(db, choice, d_h, ed_h, crypto=bool(is_crypto), online=online)
            if online:
                market.update_all(db)
                market.live_update(db)
            invalidate()
            st.success(f"{n} line(s) saved as of {d_h:%d %b %Y}.")
        except Exception as e:
            st.error(str(e))
    st.stop()

kind_label = st.segmented_control("Type", list(KINDS), default="Buy", key="kind") or "Buy"
kind = KINDS[kind_label]
with_title = kind in ("buy", "sell", "dividend", "reward")
NEW = "__new__"


@st.cache_data(ttl=300, show_spinner=False)
def _known_lines(db_path: str, _mtime: float):
    from finmon.db import DB as _DB

    d = _DB(db_path)
    inst = d.read("SELECT isin, ticker, name, currency FROM instruments")
    last = d.read("SELECT p.symbol AS ticker, p.close AS last FROM prices p "
                  "JOIN (SELECT symbol, MAX(date) d FROM prices GROUP BY symbol) m ON p.symbol = m.symbol AND p.date = m.d")
    return inst.merge(last, on="ticker", how="left")


info, instrument, ticker, isin = {}, None, "", ""
held = pd.Series(dtype=float)
if with_title:
    cur = bundle().portfolio.current
    held = (cur[cur["account_id"] == choice].groupby("isin")["qty"].sum()
            if not cur.empty and choice != NEW else pd.Series(dtype=float))
    held_any = set(cur["isin"]) if not cur.empty else set()
    lines = _known_lines(str(db.path), db.path.stat().st_mtime).set_index("isin")
    if kind in ("sell", "dividend"):
        opts = [i for i in held.index if i in lines.index]
    else:
        opts = [i for i in held.index if i in lines.index] + \
            sorted((i for i in held_any if i in lines.index and i not in held.index), key=lambda i: str(lines.loc[i, "name"]))

    def _label(i):
        if i == NEW:
            return "Other security (enter ticker)…"
        r = lines.loc[i]
        q = f"  ·  {_n(held[i])} held" if i in held.index else ""
        return f"{r['name'] or r['ticker']} ({r['ticker'] or i}){q}"

    pick = st.selectbox("Security", opts + ([NEW] if kind != "sell" or not opts else []), format_func=_label,
                        key=f"line_{choice}_{kind}")
    if pick != NEW:
        r = lines.loc[pick]
        instrument, ticker = pick, (r["ticker"] or "")
        isin = pick if not str(pick).startswith(("CRYPTO-", "TICKER:", "IBKR:", "MANUAL:")) else ""
        info = {"ticker": ticker, "name": r["name"], "currency": r["currency"],
                "last": float(r["last"]) if r["last"] == r["last"] and r["last"] is not None else None}
        st.caption(f"Last price {_n(info['last'], 2)} {info['currency']}" if info.get("last") else "No price available.")
    else:
        t1, t2, t3 = st.columns([1.2, 1.2, 0.6], vertical_alignment="bottom")
        ticker = t1.text_input("Yahoo ticker", placeholder="AAPL, CW8.PA, IWDA.AS, BTC-USD").strip().upper()
        isin = t2.text_input("ISIN (optional)", placeholder="LU1681043599").strip().upper()
        if ticker and t3.button("Check", width="stretch") and online:
            with st.spinner("Looking up…"):
                st.session_state["lookup"] = market.lookup(ticker)
        info = st.session_state.get("lookup", {})
        if info and info.get("ticker") != ticker:
            info = {}
        if info:
            st.success(f"**{info.get('name')}** · last {_n(info['last'], 2)} {info.get('currency')}")

d1, d2, d3, d4 = st.columns(4)
op_date = d1.date_input("Date", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
ccy_default = (info.get("currency") or "EUR").upper() if info else "EUR"
ccys = ["EUR", "USD", "GBP", "CHF", "JPY", "CAD"]
if ccy_default not in ccys:
    ccys.insert(0, ccy_default)
currency = d4.selectbox("Currency", ccys, index=ccys.index(ccy_default))
qty = price = amount = None
if kind in ("buy", "sell", "reward"):
    max_q = float(held[instrument]) if kind == "sell" and instrument in held.index else None
    qty = d2.number_input("Quantity", min_value=0.0, step=1.0, format="%.6g", help=f"Held: {_n(max_q)}" if max_q else None)
    if kind == "sell" and max_q and qty > max_q + 1e-9:
        st.warning(f"Only {_n(max_q)} held on this account.")
    if kind != "reward":
        price = d3.number_input(f"Unit price ({currency})", min_value=0.0, step=0.01, format="%.4f",
                                value=float(info["last"]) if info and info.get("last") else 0.0)
        tot = st.number_input(f"or total amount excl. fees ({currency})", min_value=0.0, step=10.0)
        if tot and price and not qty:
            qty = tot / price
            st.caption(f"Quantity: {qty:.6g}")
else:
    amount = d2.number_input(f"Amount ({currency})", min_value=0.0, step=10.0)
f1, f2 = st.columns([1, 3])
fees = f1.number_input(f"Fees ({currency})", min_value=0.0, step=0.5) if kind in ("buy", "sell") else 0.0
note = f2.text_input("Note")
fund = st.checkbox("Funded by a new deposit", value=False) if kind == "buy" else False

if kind in ("buy", "sell") and qty and price:
    rate = market.fx_on(db, currency, op_date, online) or 1.0
    gross = qty * price / rate
    total = gross + fees / rate if kind == "buy" else gross - fees / rate
    st.caption(f"{'Cost' if kind == 'buy' else 'Proceeds'}: **{eur(total, 2)}**"
               + (f" · {currency}/EUR {rate:.4f}" if currency != "EUR" else ""))

if st.button("Save transaction", type="primary"):
    try:
        if choice == "__new__":
            if not new_name.strip():
                raise ValueError("Name the new account.")
            acc_id = manual.ensure_account(db, new_name.strip(), new_type)
        else:
            acc_id = choice
        if with_title and not (ticker or isin or instrument):
            raise ValueError("Enter a ticker or an ISIN.")
        row = manual.add_operation(
            db, account_id=acc_id, kind=kind, d=op_date, ticker=ticker or None, isin=isin or None,
            name=info.get("name") if info else (ticker or None), quantity=qty or None, price=price,
            currency=currency, fees=fees, amount=amount, note=note, fund_with_deposit=fund, online=online,
            instrument=instrument)
        if online and kind in ("buy", "sell", "reward"):
            market.update_all(db)
            market.live_update(db)
        invalidate()
        st.session_state.pop("lookup", None)
        st.success(f"Saved: {kind_label} {row['name']} · {eur(row['amount'], 2, sign=True)}")
    except Exception as e:
        st.error(str(e))

# ------------------------------------------------------------- recent
theme.section("Recent transactions")
names = accounts.set_index("id")["name"].to_dict()
ops = db.read("SELECT id, date, account_id, kind, name, quantity, amount, fees, source FROM trades "
              "ORDER BY date DESC, rowid DESC LIMIT 300")
if not ops.empty:
    rev = {v: k for k, v in KINDS.items()} | {"transfer_in": "Transfer in", "transfer_out": "Transfer out",
                                              "tax": "Tax", "split": "Split"}
    view = pd.DataFrame({
        "Delete": False, "id": ops["id"], "Date": pd.to_datetime(ops["date"]),
        "Account": ops["account_id"].map(names).fillna(ops["account_id"]),
        "Type": ops["kind"].map(rev).fillna(ops["kind"]), "Security": ops["name"], "Quantity": ops["quantity"],
        "Amount": ops["amount"], "Source": ops["source"],
    })
    if st.toggle("Manual entries only", value=True):
        view = view[view["Source"].fillna("").str.startswith("manuel")]
    ed = st.data_editor(view, hide_index=True, width="stretch", disabled=[c for c in view.columns if c != "Delete"],
                        column_config={"id": None, "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                       "Quantity": st.column_config.NumberColumn(format="%.6g"),
                                       "Amount": st.column_config.NumberColumn(format="%+,.2f €")}, key="ops_editor")
    to_del = ed.loc[ed["Delete"], "id"].tolist()
    if to_del and st.button(f"Delete {len(to_del)} transaction(s)"):
        manual.delete_operations(db, to_del)
        invalidate()
        st.rerun()
