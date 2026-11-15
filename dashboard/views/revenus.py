from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import bundle, empty_state, eur, get_db, invalidate, plot
from finmon import charts
from finmon.analytics import budget

b = bundle()
st.title("Revenus & épargne")

flows = budget.monthly_flows(b.tx)
if not flows.empty:
    complete = flows[flows.index < pd.Timestamp.today().to_period("M").to_timestamp()].tail(24)
    st.subheader("Revenus, dépenses et épargne par mois")
    fig = go.Figure()
    for col, lab in (("income", "Revenus"), ("expenses", "Dépenses")):
        fig.add_trace(go.Bar(x=complete.index, y=complete[col], name=lab, marker_color=charts.FIXED[lab],
                             hovertemplate="%{y:,.0f} €<extra>" + lab + "</extra>"))
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    plot(charts.layout(fig, 340), key="flows")

    l, r = st.columns(2)
    with l:
        st.subheader("Épargne mensuelle")
        plot(charts.signed_hbar([d.strftime("%m/%Y") for d in complete.index[::-1]], complete["savings"].values[::-1]),
             key="sav")
    with r:
        st.subheader("Taux d'épargne (moyenne glissante 3 mois)")
        roll = (complete["savings"].rolling(3).sum() / complete["income"].rolling(3).sum() * 100).to_frame("Taux d'épargne")
        plot(charts.line(roll.dropna(), ["Taux d'épargne"], ysuffix=" %", yfmt=".0f", hover_fmt=".0f",
                         colors={"Taux d'épargne": charts.SERIES[0]}), key="rate")

    inc = b.tx[b.tx["cat_type"] == "income"]
    if not inc.empty:
        st.subheader("Sources de revenus (12 derniers mois)")
        rec = inc[inc["date"] > pd.Timestamp.today() - pd.DateOffset(months=12)]
        src = rec.groupby("category")["amount"].sum().sort_values(ascending=False)
        plot(charts.hbar(src.index, src.values, color=charts.SERIES[2], text=[eur(v) for v in src.values]), key="src")
else:
    empty_state("opérations bancaires")

# ------------------------------------------------------------- livrets
st.subheader("Livrets et épargne réglementée")
types = b.accounts.set_index("id")["type"]
names = b.accounts.set_index("id")["name"]
liv = b.cash[b.cash["account_id"].map(types) == "livret"]
if not liv.empty:
    piv = liv.pivot_table(index="date", columns="account_id", values="balance").rename(columns=names.to_dict())
    plot(charts.line(piv, list(piv.columns), area=True), key="liv")
    last = liv.sort_values("date").groupby("account_id").tail(1)
    st.dataframe(pd.DataFrame({"Livret": last["account_id"].map(names), "Solde": last["balance"],
                               "Au": last["date"]}), hide_index=True,
                 column_config={"Solde": st.column_config.NumberColumn(format="%.2f €"),
                                "Au": st.column_config.DateColumn(format="DD/MM/YYYY")})

with st.form("manual"):
    st.markdown("**Saisir un solde à la main** — pour un livret ou un compte qui n'est pas chez Boursorama "
                "(chaque saisie ajoute un point ; le solde est conservé entre deux saisies).")
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    existing = b.accounts[b.accounts["id"].str.startswith("manuel:")]
    name = c1.text_input("Nom du compte", placeholder="ex. LDDS Crédit Agricole")
    kind = c2.selectbox("Type", ["livret", "courant", "autre"])
    bal = c3.number_input("Solde (€)", step=100.0)
    d = c4.date_input("Date", value=date.today(), format="DD/MM/YYYY")
    if not existing.empty:
        st.caption("Comptes manuels existants : " + ", ".join(existing["name"]))
    if st.form_submit_button("Ajouter") and name:
        acc_id = "manuel:" + name.strip().lower().replace(" ", "-")
        db = get_db()
        db.upsert("accounts", pd.DataFrame([{"id": acc_id, "institution": "Saisie manuelle", "name": name.strip(),
                                             "type": kind, "currency": "EUR"}]), mode="ignore")
        db.upsert("balance_snapshots", pd.DataFrame([{"account_id": acc_id, "date": d.isoformat(), "balance": bal,
                                                      "source": "manuel"}]), mode="replace")
        invalidate()
        st.success(f"Solde de {eur(bal)} enregistré pour {name}.")
        st.rerun()
