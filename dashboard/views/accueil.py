"""Net worth: total, history, clickable breakdown (category > account > lines), key indicators."""
from datetime import date

import pandas as pd
import streamlit as st

import theme
from common import (bundle, empty_state, en, eur, get_db, invalidate, pct, period_picker, period_start, plot,
                    show_warnings, signed_style)
from finmon import charts
from finmon.analytics import budget, portfolio

b = bundle()
if not b.has_data or b.networth.empty:
    from common import build_demo, profile_name

    st.html("<div style='padding:1.2rem 0 .4rem 0'><div class='fm-eyebrow'>Welcome</div>"
            "<div class='fm-hero'>Meridian</div>"
            "<div style='color:var(--muted);font-size:.95rem;margin-top:.4rem;max-width:640px'>"
            "Net worth, investment performance and cash flow — computed on this machine from your own exports."
            "</div></div>")
    CARDS = [("1", "Import your history", "Broker statements, crypto exchanges, bank exports. Detected automatically, "
              "re-imports never duplicate.", "views/donnees.py", "Open Data & imports", ":material/upload:"),
             ("2", "Add accounts by hand", "Tracked holdings (trades, statements) or manual value (invested amount "
              "and current value).", "views/saisie.py", "Open Transactions", ":material/add:"),
             ("3", "Explore the demo", "A synthetic profile with every page filled in. Switch back to Personal "
              "from the sidebar.", None, "Generate demo", ":material/play_arrow:")]
    cols = st.columns(3)
    for col, (n, title, text, page, cta, icon) in zip(cols, CARDS):
        with col, st.container(border=True):
            st.html(f"<div style='color:var(--accent);font-weight:700;font-size:.8rem'>STEP {n}</div>"
                    f"<div style='font-weight:600;font-size:1.05rem;margin:.25rem 0'>{title}</div>"
                    f"<div style='color:var(--muted);font-size:.85rem;min-height:3.6rem'>{text}</div>")
            if page:
                st.page_link(page, label=cta, icon=icon)
            elif profile_name() != "demo":
                if st.button(cta, icon=icon, type="primary", key="welcome_demo"):
                    build_demo()
            else:
                st.caption("You are on the demo profile.")
    st.html("<div style='color:var(--muted);font-size:.8rem;margin-top:1rem'>Guides: docs/USER_GUIDE.md · "
            "supported formats: docs/FORMATS.md · github.com/gitpouledauph/finmon</div>")
    st.stop()

nw = b.networth.copy()
by_bucket = nw.pivot_table(index="date", columns="bucket", values="value", aggfunc="sum").fillna(0.0).sort_index()
total = by_bucket.sum(axis=1)
last = total.index[-1]
ORDER = ["Investissements", "Liquidités", "Épargne réglementée", "Autres actifs"]
COLORS = {"Investments": charts.CAT[0], "Cash": charts.CAT[1], "Regulated savings": charts.CAT[2], "Other assets": charts.CAT[3]}

head, per = st.columns([3, 2], vertical_alignment="bottom")
with per:
    key = period_picker("home_period", "1Y")
start = period_start(key, last, total.index[0])
t0 = total.asof(start)
var = total.iloc[-1] - t0
with head:
    theme.hero("Net worth", eur(total.iloc[-1]), var, f"{eur(var, sign=True)} ({pct(var / t0) if t0 else '—'})", key)
show_warnings(b, "home")

view = by_bucket[by_bucket.index >= start]
order = [c for c in ORDER if c in view.columns]
plot(charts.line(view[order].rename(columns=en), [en(c) for c in order], height=320, area=True, colors=COLORS), key="nw")

# ------------------------------------------------------------- breakdown
cur = nw[nw["date"] == last]
cur = cur[cur["value"].abs() > 0.5]
cats = (cur.groupby("bucket")["value"].sum().reindex([c for c in ORDER if c in set(cur["bucket"])]).dropna()
        .rename("Value").to_frame())
cats["Share"] = cats["Value"] / cats["Value"].sum() * 100
cats["Accounts"] = cur.groupby("bucket")["account_id"].nunique()
cats = cats.reset_index().rename(columns={"bucket": "key"})
cats["Category"] = cats["key"].map(en)

MONEY = st.column_config.NumberColumn(format="%,.0f €")
SHARE = st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100)
PART = {"Espèces": "Cash", "Titres": "Holdings", "Solde": "Balance"}

theme.section("Breakdown", "select a category, then an account")
d1, d2, d3 = st.columns([1, 1.5, 2.2])
with d1:
    plot(charts.donut(cats["Category"], cats["Value"], height=200, colors=COLORS,
                      center=f"<b>{eur(cats['Value'].sum())}</b>"), key="nw_donut")
with d2:
    ev = st.dataframe(cats[["Category", "Value", "Share"]], hide_index=True, width="stretch", on_select="rerun",
                      selection_mode="single-row", key="cat_sel", column_config={"Value": MONEY, "Share": SHARE})
    picked = ev.selection.rows[0] if ev.selection.rows else 0
    cat = cats.iloc[picked]["key"]
with d3:
    acc = cur[cur["bucket"] == cat].copy()
    acc["Type"] = acc["part"].map(PART).fillna("")
    acc = (acc.groupby(["account_id", "name", "institution", "Type"], dropna=False)["value"].sum()
           .sort_values(ascending=False).reset_index())
    acc["Share"] = acc["value"] / acc["value"].sum() * 100
    ev2 = st.dataframe(acc.rename(columns={"name": "Account", "institution": "Institution", "value": "Value"})
                       [["Account", "Institution", "Type", "Value", "Share"]],
                       hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                       key=f"acc_sel_{cat}", column_config={"Value": MONEY, "Share": SHARE})

if ev2.selection.rows:
    row = acc.iloc[ev2.selection.rows[0]]
    a_id = row["account_id"]
    theme.section(row["name"], f"{row['Type'].lower()} · {eur(row['value'])}")
    c = b.portfolio.current
    lines = c[c["account_id"] == a_id] if not c.empty else c
    if row["Type"] == "Holdings" and not lines.empty:
        t = lines.sort_values("value", ascending=False)
        t = pd.DataFrame({"Security": t["name"], "Qty": t["qty"], "Avg cost": t["pru"], "Price": t["price"],
                          "Value": t["value"], "P&L": t["value"] - t["cost"],
                          "P&L %": (t["value"] / t["cost"] - 1) * 100})
        st.dataframe(signed_style(t, ["P&L", "P&L %"]).format({"Qty": "{:.4g}", "Avg cost": "{:,.2f}", "Price": "{:,.2f}",
                                                               "Value": "{:,.0f} €", "P&L": "{:+,.0f} €",
                                                               "P&L %": "{:+.1f} %"}, na_rep="—"),
                     hide_index=True, width="stretch")
    elif row["Type"] == "Cash":
        KIND = {"deposit": "Deposits", "withdrawal": "Withdrawals", "buy": "Purchases", "sell": "Sales",
                "dividend": "Dividends", "interest": "Interest", "fee": "Fees", "tax": "Taxes", "reward": "Rewards"}
        ops = get_db().read("SELECT kind, SUM(amount) AS amount, COUNT(*) AS n FROM trades WHERE account_id = ? "
                            "GROUP BY kind", [a_id])
        ops = ops[ops["kind"].isin(KIND)]
        st.dataframe(signed_style(pd.DataFrame({"Flow": ops["kind"].map(KIND), "Transactions": ops["n"],
                                                "Amount": ops["amount"]}), ["Amount"]).format({"Amount": "{:+,.2f} €"}),
                     hide_index=True, width="content")
    else:
        rate = b.accounts.set_index("id").get("rate")
        if rate is not None and a_id in rate.index and rate[a_id] == rate[a_id]:
            st.caption(f"Rate {rate[a_id]:.2f} % · expected interest 12 m {eur(row['value'] * rate[a_id] / 100)}")

# ------------------------------------------------------------- manual values
manual_acc = b.accounts[b.accounts["type"].isin(["livret", "autre"]) & b.accounts["id"].str.startswith("manuel:")]
if not manual_acc.empty:
    missing = not set(manual_acc["id"]) <= set(b.balance_snapshots["account_id"])
    with st.expander("Update manually valued accounts", expanded=missing, icon=":material/edit:"):
        bs = b.balance_snapshots.sort_values("date").groupby("account_id").tail(1).set_index("account_id")
        rows = pd.DataFrame({"id": manual_acc["id"], "Account": manual_acc["name"],
                             "Current": manual_acc["id"].map(bs["balance"]),
                             "As of": pd.to_datetime(manual_acc["id"].map(bs["date"])),
                             "New value": manual_acc["id"].map(bs["balance"]).astype(float),
                             "Date": pd.Timestamp(date.today())})
        ed_v = st.data_editor(rows, hide_index=True, width="stretch", key="manual_values",
                              disabled=["id", "Account", "Current", "As of"],
                              column_config={"id": None, "Current": st.column_config.NumberColumn(format="%,.2f €"),
                                             "As of": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                             "New value": st.column_config.NumberColumn(format="%,.2f €", min_value=0.0),
                                             "Date": st.column_config.DateColumn(format="DD/MM/YYYY")})
        if st.button("Save values", type="primary", key="save_manual_values"):
            for r in ed_v.itertuples(index=False):
                new_v, old_v = r[4], r[2]
                if new_v is not None and new_v == new_v and (old_v != old_v or abs(new_v - old_v) > 0.005):
                    get_db().upsert("balance_snapshots", pd.DataFrame([{
                        "account_id": r.id, "date": pd.Timestamp(r.Date).date().isoformat(), "balance": float(new_v),
                        "source": "manuel"}]), mode="replace")
            invalidate()
            st.rerun()

# ------------------------------------------------------------- indicators
pf = portfolio.summary(b.portfolio) if not b.portfolio.accounts.empty else {}
types = b.accounts.set_index("id")["type"]
tx = b.tx[b.tx["account_id"].map(types).isin(["courant", "autre"])] if not b.tx.empty else b.tx
theme.section("Key indicators")
k = st.columns(4)
if pf:
    k[0].metric("Investment P&L", eur(pf.get("pnl_total"), sign=True))
    k[1].metric("TWR", pct(pf["twr"]), f"IRR {pct(pf['xirr'])} p.a." if pf.get("xirr") is not None else None,
                delta_color="off")
if not tx.empty:
    g = budget.global_monthly(tx)
    last_data = budget.last_real_date(tx)
    g = g[g.index + pd.offsets.MonthEnd(0) <= last_data]
    g = g[g.index >= (g.index[g["salaire"] > 0].min() if (g["salaire"] > 0).any() else g.index.min())]
    if not g.empty:
        lm = g.iloc[-1]
        k[2].metric(f"Spending · {g.index[-1]:%b %Y}", eur(lm["depenses"]),
                    f"{eur(lm['depenses'] - g['depenses'].tail(12).mean(), sign=True)} vs 12-m avg", delta_color="inverse")
        t12 = g.tail(12)
        inc = (t12["salaire"] + t12["exceptionnel"]).sum()
        k[3].metric("Savings rate · 12 m", pct(t12["economise"].sum() / inc, 0, sign=False) if inc else "—")
