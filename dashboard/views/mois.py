"""Bilan d'un mois : où est passé l'argent, comparaison avec la moyenne et l'an dernier."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import bundle, empty_state, eur, plot
from finmon import charts
from finmon.analytics import budget

b = bundle()
st.title("Bilan du mois")
tx = b.tx
if tx.empty:
    empty_state("opérations bancaires")
    st.stop()

types = b.accounts.set_index("id")["type"]
tx = tx[tx["account_id"].map(types).isin(["courant", "autre"])]   # le budget se lit sur courant + carte
months = sorted(tx["month"].unique(), reverse=True)
last_data = tx["date"].max()
# Mois proposé : le dernier mois complet (le mois en cours reste consultable).
default = next((i for i, m in enumerate(months) if m + pd.offsets.MonthEnd(0) <= last_data), 0)
m = st.selectbox("Mois", months, index=default, format_func=charts.mois)
m = pd.Timestamp(m)
partial = m + pd.offsets.MonthEnd(0) > last_data
if partial:
    st.caption(f"Mois incomplet : opérations jusqu'au {last_data:%d/%m/%Y}.")

cur = tx[tx["month"] == m]
prev12 = tx[(tx["month"] < m) & (tx["month"] >= m - pd.DateOffset(months=12))]
n_prev = max(prev12["month"].nunique(), 1)
ly = tx[tx["month"] == m - pd.DateOffset(years=1)]


def flows(d: pd.DataFrame) -> dict:
    return {
        "income": d.loc[d["cat_type"] == "income", "amount"].sum(),
        "expenses": budget.expenses(d)["spend"].sum(),
        "invest": -d.loc[d["category"] == "Épargne & investissement", "amount"].sum(),
        "livrets": -d.loc[d["category"] == "Épargne livrets", "amount"].sum(),
    }


f, fa = flows(cur), {k: v / n_prev for k, v in flows(prev12).items()}

# ------------------------------------------------------------- KPIs
k = st.columns(4)
k[0].metric("Revenus", eur(f["income"]), f"{eur(f['income'] - fa['income'], sign=True)} vs moy. 12 mois")
k[1].metric("Dépenses", eur(f["expenses"]), f"{eur(f['expenses'] - fa['expenses'], sign=True)} vs moy. 12 mois",
            delta_color="inverse", help="Dépenses nettes : remboursements des colocataires et des amis déduits.")
k[2].metric("Investi (courtiers)", eur(f["invest"]),
            f"{f['invest'] / f['income'] * 100:.0f} % des revenus" if f["income"] > 0 else None, delta_color="off",
            help="Virements vers IBKR, Trade Republic, Binance… rapprochés des versements reçus par le courtier.")
k[3].metric("Épargne livrets (nette)", eur(f["livrets"], sign=True),
            "vers les livrets" if f["livrets"] >= 0 else "retiré des livrets", delta_color="off",
            help="Virements vers les livrets moins retours des livrets dans le mois.")

# ------------------------------------------------------------- où va l'argent
st.subheader("Où est passé l'argent")
rest = f["income"] - f["expenses"] - f["invest"] - f["livrets"]
steps = [("Dépenses", -f["expenses"]), ("Investissements", -f["invest"]), ("Livrets", -f["livrets"])]
fig = charts.waterfall(steps, "Revenus", f["income"], "Reste sur le compte")
plot(fig, key="wf")
st.caption(f"Reste sur le compte courant ce mois : {eur(rest, sign=True)} "
           "(une valeur négative signifie que le mois a puisé dans le solde ou les livrets).")

# ------------------------------------------------------------- par catégorie
st.subheader("Dépenses par catégorie")
e_cur = budget.expenses(cur).groupby("category")["spend"].sum()
e_avg = budget.expenses(prev12).groupby("category")["spend"].sum() / n_prev
e_ly = budget.expenses(ly).groupby("category")["spend"].sum()
tab = pd.DataFrame({"Ce mois": e_cur, "Moyenne 12 mois": e_avg, "Même mois l'an dernier": e_ly}).fillna(0.0)
tab = tab[(tab.abs() > 0.5).any(axis=1)]
tab["Écart vs moyenne"] = tab["Ce mois"] - tab["Moyenne 12 mois"]
tab = tab.sort_values("Ce mois", ascending=False)
left, right = st.columns([3, 2])
with left:
    st.dataframe(tab, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="%,.0f €") for c in tab.columns} | {
        "Écart vs moyenne": st.column_config.NumberColumn(format="%+,.0f €")})
with right:
    d = tab["Écart vs moyenne"].sort_values()
    d = d[d.abs() >= 10]
    if not d.empty:
        st.markdown("**Écart à la moyenne**")
        plot(charts.signed_hbar(d.index, d.values), key="delta_cat")

# ------------------------------------------------------------- logement
logt = cur[cur["category"] == "Logement"]
if not logt.empty:
    st.subheader("Logement")
    paid = -logt.loc[logt["amount"] < 0, "amount"].sum()
    got = logt.loc[logt["amount"] > 0, "amount"].sum()
    lg12 = prev12[prev12["category"] == "Logement"]
    l1, l2, l3, l4 = st.columns(4)
    l1.metric("Loyer et charges payés", eur(paid))
    l2.metric("Parts reçues (colocataires)", eur(got))
    l3.metric("Coût net du logement", eur(paid - got))
    l4.metric("Coût net moyen (12 mois)", eur(-lg12["amount"].sum() / n_prev),
              help="Les parts des colocataires arrivent parfois groupées sur deux mois : la moyenne lisse ces décalages.")
    st.caption("Les virements passés à partir du 25 sont comptés sur le mois suivant (le mois qu'ils couvrent).")
    st.dataframe(logt.sort_values("date")[["date", "label", "amount"]].rename(
        columns={"date": "Date", "label": "Libellé", "amount": "Montant"}), hide_index=True, width="stretch",
        column_config={"Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                       "Montant": st.column_config.NumberColumn(format="%+,.2f €")})

# ------------------------------------------------------------- plus grosses dépenses
st.subheader("Plus grosses dépenses du mois")
big = budget.expenses(cur).sort_values("spend", ascending=False).head(12)
st.dataframe(big[["date", "merchant", "category", "spend"]].rename(columns={
    "date": "Date", "merchant": "Marchand", "category": "Catégorie", "spend": "Montant"}),
    hide_index=True, width="stretch",
    column_config={"Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                   "Montant": st.column_config.NumberColumn(format="%,.2f €")})

todo = cur[cur["category"] == "À classer"]
if not todo.empty:
    st.info(f"{len(todo)} opération(s) à classer ce mois ({eur(-todo['amount'].sum())}) : "
            "corrigez-les dans la page Dépenses, en cochant « Règle » pour que le marchand soit reconnu "
            "automatiquement aux prochains imports.")

# ------------------------------------------------------------- historique
st.subheader("Mois par mois")
hist = budget.monthly_flows(tx)
inv = -tx[tx["category"] == "Épargne & investissement"].groupby("month")["amount"].sum()
liv = -tx[tx["category"] == "Épargne livrets"].groupby("month")["amount"].sum()
hist = hist.assign(invest=inv, livrets=liv).fillna(0.0).tail(24)
fig = go.Figure()
for col, lab, color in (("income", "Revenus", charts.FIXED["Revenus"]), ("expenses", "Dépenses", charts.FIXED["Dépenses"]),
                        ("invest", "Investi", charts.SERIES[0]), ("livrets", "Livrets (net)", charts.SERIES[3])):
    fig.add_trace(go.Bar(x=hist.index, y=hist[col], name=lab, marker_color=color,
                         hovertemplate="%{y:,.0f} €<extra>" + lab + "</extra>"))
fig.add_vline(x=m, line_dash="dot", line_color=charts.MUTED)
fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05)
plot(charts.layout(fig, 340), key="hist")
