from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import bundle, empty_state, eur, get_db, invalidate, plot
from finmon import charts, config
from finmon.analytics import budget

b = bundle()
st.title("Savings accounts")

flows = budget.monthly_flows(b.tx)
if not flows.empty:
    complete = flows[flows.index < pd.Timestamp.today().to_period("M").to_timestamp()].tail(24)
    st.subheader("Income, spending and savings")
    fig = go.Figure()
    for col, lab in (("income", "Revenus"), ("expenses", "Dépenses")):
        fig.add_trace(go.Bar(x=complete.index, y=complete[col], name=lab, marker_color=charts.FIXED[lab],
                             hovertemplate="%{y:,.0f} €<extra>" + lab + "</extra>"))
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    plot(charts.layout(fig, 340), key="flows")

    l, r = st.columns(2)
    with l:
        st.subheader("Monthly savings")
        plot(charts.signed_hbar([d.strftime("%m/%Y") for d in complete.index[::-1]], complete["savings"].values[::-1]),
             key="sav")
    with r:
        st.subheader("Savings rate · 3-month rolling")
        roll = (complete["savings"].rolling(3).sum() / complete["income"].rolling(3).sum() * 100).to_frame("Taux d'épargne")
        plot(charts.line(roll.dropna(), ["Taux d'épargne"], ysuffix=" %", yfmt=".0f", hover_fmt=".0f",
                         colors={"Taux d'épargne": charts.SERIES[0]}), key="rate")

    inc = b.tx[b.tx["cat_type"] == "income"]
    if not inc.empty:
        st.subheader("Income sources · 12 m")
        rec = inc[inc["date"] > pd.Timestamp.today() - pd.DateOffset(months=12)]
        src = rec.groupby("category")["amount"].sum().sort_values(ascending=False)
        plot(charts.hbar(src.index, src.values, color=charts.SERIES[2], text=[eur(v) for v in src.values]), key="src")
else:
    empty_state("bank transactions")

# ------------------------------------------------------------- livrets
st.subheader("Savings accounts")
types = b.accounts.set_index("id")["type"]
names = b.accounts.set_index("id")["name"]
liv = b.cash[b.cash["account_id"].map(types) == "livret"]
if not liv.empty:
    piv = liv.pivot_table(index="date", columns="account_id", values="balance").rename(columns=names.to_dict())
    plot(charts.line(piv, list(piv.columns), area=True), key="liv")
    last = liv.sort_values("date").groupby("account_id").tail(1)
    rates = b.accounts.set_index("id")["rate"] if "rate" in b.accounts else pd.Series(dtype=float)
    tab = pd.DataFrame({"Livret": last["account_id"].map(names), "Solde": last["balance"],
                        "Taux": last["account_id"].map(rates), "Au": last["date"]})
    tab["Intérêts / an"] = tab["Solde"] * tab["Taux"].fillna(0) / 100
    k1, k2, k3 = st.columns(3)
    k1.metric("Total épargne réglementée", eur(tab["Solde"].sum()))
    k2.metric("Intérêts estimés sur 12 mois", eur(tab["Intérêts / an"].sum()),
              help="Solde actuel × taux en vigueur, sans versement ni changement de taux. "
                   "Les intérêts sont versés au 31 décembre, calculés par quinzaine.")
    reg = config.settings().get("taux_reglementes") or {}
    if reg:
        k3.metric("Taux Livret A / LDDS", f"{reg.get('Livret A', 0):.2f} %".replace(".", ","),
                  help=f"En vigueur depuis le {pd.Timestamp(reg.get('date')).strftime('%d/%m/%Y')} "
                       "(config/settings.yaml › taux_reglementes).")
    st.dataframe(tab, hide_index=True,
                 column_config={"Solde": st.column_config.NumberColumn(format="%.2f €"),
                                "Taux": st.column_config.NumberColumn(format="%.2f %%"),
                                "Intérêts / an": st.column_config.NumberColumn(format="%.2f €"),
                                "Au": st.column_config.DateColumn(format="DD/MM/YYYY")})

with st.form("manual"):
    st.markdown("**Saisir un solde à la main** — pour un livret ou un compte qui n'est pas chez Boursorama "
                "(chaque saisie ajoute un point ; le solde est conservé entre deux saisies).")
    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
    existing = b.accounts[b.accounts["id"].str.startswith("manuel:")]
    name = c1.text_input("Nom du compte", placeholder="ex. LDDS Crédit Agricole")
    kind = c2.selectbox("Type", ["livret", "courant", "autre"])
    bal = c3.number_input("Solde (€)", step=100.0)
    default_rate = float((config.settings().get("taux_reglementes") or {}).get("Livret A", 0.0))
    rate = c4.number_input("Taux (% / an)", value=default_rate, step=0.05, format="%.2f",
                           help="Livret A et LDDS : même taux réglementé. Mettez 0 pour un compte courant.")
    d = c5.date_input("Date", value=date.today(), format="DD/MM/YYYY")
    if not existing.empty:
        st.caption("Manual accounts: " + ", ".join(existing["name"]))
    if st.form_submit_button("Add") and name:
        acc_id = "manuel:" + name.strip().lower().replace(" ", "-")
        db = get_db()
        db.upsert("accounts", pd.DataFrame([{"id": acc_id, "institution": "Saisie manuelle", "name": name.strip(),
                                             "type": kind, "currency": "EUR"}]), mode="ignore")
        db.execute("UPDATE accounts SET rate = ? WHERE id = ?", [rate if kind == "livret" else None, acc_id])
        db.upsert("balance_snapshots", pd.DataFrame([{"account_id": acc_id, "date": d.isoformat(), "balance": bal,
                                                      "source": "manuel"}]), mode="replace")
        invalidate()
        st.success(f"Solde de {eur(bal)} enregistré pour {name}.")
        st.rerun()
