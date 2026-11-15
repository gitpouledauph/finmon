from datetime import date

import pandas as pd
import streamlit as st

from common import bundle, eur, get_db, invalidate, profile_name
from finmon import manual, market

st.title("Saisir une opération")
st.caption("Après l'import historique, c'est ici que vous ajoutez vos nouvelles opérations : "
           "aucune connexion à vos banques ou courtiers n'est nécessaire.")

db = get_db()
online = profile_name() != "demo"
accounts = db.table("accounts")
inv = accounts[accounts["type"].isin(["pea", "cto", "crypto", "assurance_vie"])]

mode = st.segmented_control("Saisie", ["Une opération", "Un relevé de positions"], default="Une opération",
                            label_visibility="collapsed") or "Une opération"

if mode == "Un relevé de positions":
    st.markdown("Indiquez **tout ce que contient le compte** aujourd'hui (ce que vous voyez dans l'application). "
                "finmon recale le portefeuille : une ligne absente est considérée comme vendue ou sortie, "
                "une ligne nouvelle (dépôt, conversion, Earn, staking…) est ajoutée au cours du jour.")
    labels_h = {r.id: r.name for r in inv.itertuples()}
    if not labels_h:
        st.info("Aucun compte d'investissement : importez un historique ou saisissez d'abord une opération.")
        st.stop()
    h1, h2 = st.columns([2, 1])
    acc_h = h1.selectbox("Compte", list(labels_h), format_func=labels_h.get, key="h_acc")
    d_h = h2.date_input("Date du relevé", value=date.today(), max_value=date.today(), format="DD/MM/YYYY", key="h_d")
    is_crypto = accounts.set_index("id").loc[acc_h, "type"] == "crypto"
    cur = bundle().portfolio.current
    cur = cur[cur["account_id"] == acc_h] if not cur.empty else cur
    base = pd.DataFrame({
        "ticker": [(t.split("-")[0] if is_crypto and isinstance(t, str) else t) for t in cur.get("ticker", [])],
        "isin": [i if not str(i).startswith(("CRYPTO-", "TICKER:", "IBKR:")) else "" for i in cur.get("isin", [])],
        "name": list(cur.get("name", [])), "quantity": list(cur.get("qty", [])),
    })
    st.caption("Lignes pré-remplies avec ce que finmon connaît. Corrigez les quantités, ajoutez les lignes manquantes "
               "(ex. ticker SOL sur un compte crypto, CW8.PA ou un ISIN pour un titre), videz la quantité d'une "
               "ligne qui n'existe plus.")
    ed_h = st.data_editor(base, num_rows="dynamic", hide_index=True, width="stretch", key=f"h_ed_{acc_h}",
                          column_config={
                              "ticker": st.column_config.TextColumn("Ticker" + (" (BTC, SOL…)" if is_crypto else " Yahoo")),
                              "isin": st.column_config.TextColumn("ISIN (facultatif)"),
                              "name": st.column_config.TextColumn("Nom (facultatif)"),
                              "quantity": st.column_config.NumberColumn("Quantité", format="%.8g", min_value=0.0)})
    if st.button("Enregistrer le relevé", type="primary"):
        try:
            n = manual.save_holdings(db, acc_h, d_h, ed_h, crypto=bool(is_crypto), online=online)
            if online:
                market.update_all(db)
                market.live_update(db)
            invalidate()
            st.success(f"Relevé enregistré : {n} ligne(s) au {d_h:%d/%m/%Y}.")
        except Exception as e:
            st.error(str(e))
    st.stop()

# ------------------------------------------------------------- compte
c1, c2 = st.columns([2, 1])
labels = {r.id: f"{r.name} ({r.institution})" if r.institution != r.name else r.name for r in inv.itertuples()}
choice = c1.selectbox("Compte", list(labels) + ["__new__"],
                      format_func=lambda k: "Nouveau compte…" if k == "__new__" else labels[k])
if choice == "__new__":
    n1, n2 = st.columns([2, 1])
    new_name = n1.text_input("Nom du nouveau compte", placeholder="ex. PEA Fortuneo")
    new_type = n2.selectbox("Type de compte", list(manual.ACCOUNT_TYPES))
kind_label = st.segmented_control("Type d'opération", list(manual.KINDS), default="Achat", key="kind") or "Achat"
kind = manual.KINDS[kind_label]
with_title = kind in ("buy", "sell", "dividend", "reward")

# ------------------------------------------------------------- titre
NEW = "__new__"


@st.cache_data(ttl=300, show_spinner=False)
def _known_lines(db_path: str, _mtime: float):
    """Lignes connues : détenues (par compte) + tous les titres déjà vus, avec dernier cours en devise."""
    from finmon.db import DB as _DB

    d = _DB(db_path)
    inst = d.read("SELECT isin, ticker, name, currency FROM instruments")
    last = d.read("SELECT p.symbol AS ticker, p.close AS last FROM prices p "
                  "JOIN (SELECT symbol, MAX(date) d FROM prices GROUP BY symbol) m ON p.symbol = m.symbol AND p.date = m.d")
    return inst.merge(last, on="ticker", how="left")


info = {}
instrument = None
ticker, isin = "", ""
if with_title:
    cur = bundle().portfolio.current
    held = cur[cur["account_id"] == choice][["isin", "qty"]] if not cur.empty and choice != NEW else \
        pd.DataFrame(columns=["isin", "qty"])
    held = held.groupby("isin")["qty"].sum()
    held_any = set(cur["isin"]) if not cur.empty else set()
    lines = _known_lines(str(db.path), db.path.stat().st_mtime).set_index("isin")
    # Vente / dividende : les lignes du compte. Achat : celles du compte, puis celles des autres comptes.
    if kind in ("sell", "dividend"):
        opts = [i for i in held.index if i in lines.index]
    else:
        opts = [i for i in held.index if i in lines.index] + \
            sorted((i for i in held_any if i in lines.index and i not in held.index),
                   key=lambda i: str(lines.loc[i, "name"]))

    def _n(x, dec=None):
        txt = f"{x:,.{dec}f}" if dec is not None else f"{x:,.6g}" if abs(x) >= 1e5 else f"{x:.6g}"
        return txt.replace(",", " ").replace(".", ",")

    def _label(i):
        if i == NEW:
            return "Autre titre (saisir un ticker)…"
        r = lines.loc[i]
        q = f" · {_n(held[i])} détenu(s)" if i in held.index else ""
        return f"{r['name'] or r['ticker']} ({r['ticker'] or i}){q}"

    pick = st.selectbox("Titre", opts + ([NEW] if kind != "sell" or not opts else []), format_func=_label, key=f"line_{choice}_{kind}",
                        help="Les titres que vous détenez déjà sur ce compte apparaissent en premier.")
    if pick != NEW:
        r = lines.loc[pick]
        instrument, ticker = pick, (r["ticker"] or "")
        isin = pick if not str(pick).startswith(("CRYPTO-", "TICKER:", "IBKR:")) else ""
        info = {"ticker": ticker, "name": r["name"], "currency": r["currency"],
                "last": float(r["last"]) if r["last"] == r["last"] and r["last"] is not None else None}
        if (r["currency"] or "").upper() in ("GBP", "GBX") and ticker.endswith(".L"):
            info["currency"] = r["currency"]
        st.caption(f"Dernier cours connu : {_n(info['last'], 2)} {info['currency']}"
                   if info.get("last") else "Pas de cours connu pour ce titre.")
    else:
        t1, t2, t3 = st.columns([1.2, 1.2, 0.6])
        ticker = t1.text_input("Ticker Yahoo Finance", placeholder="AAPL, CW8.PA, IWDA.AS, BTC-USD…",
                               help="Le symbole tel qu'affiché sur finance.yahoo.com. Suffixe de place : .PA Paris, "
                                    ".AS Amsterdam, .DE Xetra, .L Londres, .MI Milan ; crypto : BTC-USD.").strip().upper()
        isin = t2.text_input("ISIN (facultatif)", placeholder="LU1681043599").strip().upper()
        t3.write("")
        t3.write("")
        if ticker and t3.button("Vérifier", width="stretch") and online:
            with st.spinner("Recherche…"):
                st.session_state["lookup"] = market.lookup(ticker)
        info = st.session_state.get("lookup", {})
        if info and info.get("ticker") != ticker:
            info = {}
        if info:
            st.success(f"**{info.get('name')}** — dernier cours {info['last']:,.2f} {info.get('currency')}"
                       .replace(",", " "))
        elif ticker and online:
            st.caption("Cliquez sur Vérifier pour contrôler le ticker et récupérer sa devise.")

# ------------------------------------------------------------- montants
d1, d2, d3, d4 = st.columns(4)
op_date = d1.date_input("Date", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
ccy_default = (info.get("currency") or "EUR").upper() if info else "EUR"
ccys = ["EUR", "USD", "GBP", "CHF", "JPY", "CAD"]
if ccy_default not in ccys:
    ccys.insert(0, ccy_default)
currency = d4.selectbox("Devise", ccys, index=ccys.index(ccy_default))
qty = price = amount = None
if kind in ("buy", "sell", "reward"):
    max_q = float(held[instrument]) if kind == "sell" and instrument in held.index else None
    qty = d2.number_input("Quantité", min_value=0.0, step=1.0, format="%.6g",
                          help=f"Détenu : {_n(max_q)}" if max_q else None)
    if kind == "sell" and max_q and qty > max_q + 1e-9:
        st.warning(f"Vous ne détenez que {_n(max_q)} sur ce compte.")
    if kind != "reward":
        price = d3.number_input(f"Prix unitaire ({currency})", min_value=0.0, step=0.01, format="%.4f",
                                value=float(info["last"]) if info and info.get("last") else 0.0)
        tot = st.number_input(f"…ou montant total hors frais ({currency}) — calcule la quantité", min_value=0.0, step=10.0)
        if tot and price and not qty:
            qty = tot / price
            st.caption(f"Quantité calculée : {qty:.6g}")
else:
    amount = d2.number_input(f"Montant ({currency})", min_value=0.0, step=10.0)
f1, f2 = st.columns([1, 3])
fees = f1.number_input(f"Frais ({currency})", min_value=0.0, step=0.5) if kind in ("buy", "sell") else 0.0
note = f2.text_input("Note (facultatif)")
fund = False
if kind == "buy":
    fund = st.checkbox("Achat payé avec de l'argent frais versé sur le compte (ajoute un versement du même montant)",
                       value=False, help="À cocher si le compte n'a pas de solde espèces suivi (ex. versement puis achat "
                                         "immédiat). Laisser décoché si l'achat est payé avec les liquidités du compte.")

if kind in ("buy", "sell") and qty and price:
    rate = market.fx_on(db, currency, op_date, online) or 1.0
    gross = qty * price / rate
    total = gross + fees / rate if kind == "buy" else gross - fees / rate
    st.info(f"{'Coût' if kind == 'buy' else 'Produit'} : **{eur(total, 2)}**"
            + (f" (taux {currency}/EUR du {op_date:%d/%m/%Y} : {rate:.4f})" if currency != "EUR" else ""))

if st.button("Enregistrer l'opération", type="primary"):
    try:
        if choice == "__new__":
            if not new_name.strip():
                raise ValueError("Donnez un nom au nouveau compte.")
            acc_id = manual.ensure_account(db, new_name.strip(), manual.ACCOUNT_TYPES[new_type])
        else:
            acc_id = choice
        if with_title and not (ticker or isin or instrument):
            raise ValueError("Indiquez un ticker (ou un ISIN).")
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
        st.success(f"Opération enregistrée : {kind_label} {row['name']} — {eur(row['amount'], 2, sign=True)}")
    except Exception as e:
        st.error(str(e))

# ------------------------------------------------------------- dernières opérations
st.subheader("Dernières opérations")
b = bundle()
names = accounts.set_index("id")["name"].to_dict()
ops = db.read("SELECT id, date, account_id, kind, name, quantity, amount, fees, source FROM trades "
              "ORDER BY date DESC, rowid DESC LIMIT 300")
if ops.empty:
    st.caption("Aucune opération.")
else:
    rev = {v: k for k, v in manual.KINDS.items()} | {"transfer_in": "Transfert entrant", "transfer_out": "Transfert sortant",
                                                     "tax": "Impôts", "split": "Split"}
    view = pd.DataFrame({
        "Supprimer": False, "id": ops["id"], "Date": pd.to_datetime(ops["date"]),
        "Compte": ops["account_id"].map(names).fillna(ops["account_id"]),
        "Type": ops["kind"].map(rev).fillna(ops["kind"]), "Titre": ops["name"], "Quantité": ops["quantity"],
        "Montant (EUR)": ops["amount"], "Origine": ops["source"],
    })
    only_manual = st.toggle("Seulement mes saisies", value=True)
    if only_manual:
        view = view[view["Origine"].fillna("").str.startswith("manuel")]
    ed = st.data_editor(view, hide_index=True, width="stretch", disabled=[c for c in view.columns if c != "Supprimer"],
                        column_config={"id": None, "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                       "Quantité": st.column_config.NumberColumn(format="%.6g"),
                                       "Montant (EUR)": st.column_config.NumberColumn(format="%+.2f €")},
                        key="ops_editor")
    to_del = ed.loc[ed["Supprimer"], "id"].tolist()
    if to_del and st.button(f"Supprimer {len(to_del)} opération(s)"):
        manual.delete_operations(db, to_del)
        invalidate()
        st.rerun()
