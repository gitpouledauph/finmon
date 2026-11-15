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

# ------------------------------------------------------------- compte
c1, c2 = st.columns([2, 1])
labels = {r.id: f"{r.name} ({r.institution})" if r.institution != r.name else r.name for r in inv.itertuples()}
choice = c1.selectbox("Compte", list(labels) + ["__new__"],
                      format_func=lambda k: "➕ Nouveau compte…" if k == "__new__" else labels[k])
if choice == "__new__":
    n1, n2 = st.columns([2, 1])
    new_name = n1.text_input("Nom du nouveau compte", placeholder="ex. PEA Fortuneo")
    new_type = n2.selectbox("Type de compte", list(manual.ACCOUNT_TYPES))
kind_label = c2.selectbox("Type d'opération", list(manual.KINDS))
kind = manual.KINDS[kind_label]
with_title = kind in ("buy", "sell", "dividend", "reward")

# ------------------------------------------------------------- titre
info = {}
if with_title:
    t1, t2, t3 = st.columns([1.2, 1.2, 0.6])
    ticker = t1.text_input("Ticker Yahoo Finance", placeholder="AAPL, CW8.PA, IWDA.AS, BTC-USD…",
                           help="Le symbole tel qu'affiché sur finance.yahoo.com. Suffixe de place : .PA Paris, "
                                ".AS Amsterdam, .DE Xetra, .L Londres, .MI Milan ; crypto : BTC-USD.").strip().upper()
    isin = t2.text_input("ISIN (facultatif)", placeholder="LU1681043599").strip().upper()
    t3.write("")
    t3.write("")
    if ticker and t3.button("🔍 Vérifier", width="stretch") and online:
        with st.spinner("Recherche…"):
            st.session_state["lookup"] = market.lookup(ticker)
    info = st.session_state.get("lookup", {})
    if info and info.get("ticker") != ticker:
        info = {}
    if info:
        st.success(f"**{info.get('name')}** — dernier cours {info['last']:,.2f} {info.get('currency')}"
                   .replace(",", " "), icon="✅")
    elif ticker and online:
        st.caption("Cliquez sur Vérifier pour contrôler le ticker et récupérer sa devise.")
else:
    ticker, isin = "", ""

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
    qty = d2.number_input("Quantité", min_value=0.0, step=1.0, format="%.6g")
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
        if with_title and not (ticker or isin):
            raise ValueError("Indiquez un ticker (ou un ISIN).")
        row = manual.add_operation(
            db, account_id=acc_id, kind=kind, d=op_date, ticker=ticker or None, isin=isin or None,
            name=info.get("name") if info else (ticker or None), quantity=qty or None, price=price,
            currency=currency, fees=fees, amount=amount, note=note, fund_with_deposit=fund, online=online)
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
    if to_del and st.button(f"🗑️ Supprimer {len(to_del)} opération(s)"):
        manual.delete_operations(db, to_del)
        invalidate()
        st.rerun()
