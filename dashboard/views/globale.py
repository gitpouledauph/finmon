"""Vue globale : salaire, loyer, dépenses et épargne, mois par mois et année par année."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import bundle, empty_state, eur, operations_dialog, plot
from finmon import charts
from finmon.analytics import budget

b = bundle()
st.title("Vue globale")
tx = b.tx
if tx.empty:
    empty_state("opérations bancaires")
    st.stop()
types = b.accounts.set_index("id")["type"]
tx = tx[tx["account_id"].map(types).isin(["courant", "autre"])]

c1, c2, c3 = st.columns([1, 2, 2], vertical_alignment="bottom")
gran = c1.segmented_control("Vue", ["Mois", "Année"], default="Mois") or "Mois"
span = c2.segmented_control("Période", ["Depuis le 1er salaire", "12 mois", "24 mois"],
                            default="Depuis le 1er salaire") or "Depuis le 1er salaire"
refunds = c3.toggle("Déduire les avoirs carte (remboursements de marchands)", value=False,
                    help="Revenu = salaire. Dépenses = paiements par carte uniquement (aucun virement, prélèvement ni "
                         "retrait). Loyer = votre part fixe. Activé : les avoirs carte sont déduits.")

g = budget.global_monthly(tx, deduct_refunds=refunds)
last_data = tx["date"].max()
g = g[g.index + pd.offsets.MonthEnd(0) <= last_data]          # mois complets uniquement
g = g[(g["salaire"] != 0) | (g["depenses"] != 0)]
if span == "Depuis le 1er salaire":
    first = g.index[g["salaire"] > 0].min() if (g["salaire"] > 0).any() else g.index.min()
    g = g[g.index >= first]
else:
    g = g.tail(12 if span == "12 mois" else 24)
if g.empty:
    st.info("Pas encore de mois complet.")
    st.stop()

if gran == "Année":
    view = g.groupby(g.index.year)[["salaire", "loyer", "depenses", "economise", "investi", "livrets"]].sum()
    view["taux"] = view["economise"] / view["salaire"].where(view["salaire"] > 0)
    view["mois"] = g.groupby(g.index.year).size()
    xs = [str(y) + (f" ({n} mois)" if n < 12 else "") for y, n in zip(view.index, view["mois"])]
else:
    view = g
    xs = list(view.index)

# ------------------------------------------------------------- KPIs
tot = g[["salaire", "loyer", "depenses", "economise", "investi", "livrets"]].sum()
n = len(g)
k = st.columns(5)
k[0].metric("Salaire moyen / mois", eur(tot["salaire"] / n))
k[1].metric("Loyer moyen / mois", eur(tot["loyer"] / n))
k[2].metric("Dépenses hors loyer / mois", eur(tot["depenses"] / n))
k[3].metric("Économisé / mois", eur(tot["economise"] / n, sign=True))
k[4].metric("Taux d'épargne", f"{tot['economise'] / tot['salaire'] * 100:.0f} %" if tot["salaire"] else "—",
            help=f"Sur {n} mois complets : économisé / salaire.")

# ------------------------------------------------------------- décomposition du salaire
st.subheader("Que devient le salaire")
COL = {"Loyer": charts.SERIES[6], "Dépenses hors loyer": charts.FIXED["Dépenses"], "Économisé": charts.GOOD}
fig = go.Figure()
for col, lab in (("loyer", "Loyer"), ("depenses", "Dépenses hors loyer"), ("economise", "Économisé")):
    fig.add_trace(go.Bar(x=xs, y=view[col], name=lab, marker_color=COL[lab],
                         marker_line=dict(width=1, color="#0b0d12"),
                         hovertemplate="%{y:,.0f} €<extra>" + lab + "</extra>"))
fig.add_trace(go.Scatter(x=xs, y=view["salaire"], name="Salaire", mode="lines+markers",
                         line=dict(color="#e8e9ed", width=2), marker=dict(size=7),
                         hovertemplate="%{y:,.0f} €<extra>Salaire</extra>"))
fig.update_layout(barmode="relative", bargap=0.3)
plot(charts.layout(fig, 380), key="split")
st.caption("Chaque barre = loyer + dépenses hors loyer + économisé = salaire du mois. "
           "Un « économisé » négatif (sous l'axe) signifie un mois où les dépenses ont dépassé le salaire.")

l, r = st.columns(2)
with l:
    st.subheader("Taux d'épargne")
    rate = pd.DataFrame({"Taux d'épargne": view["taux"] * 100}, index=xs)
    fig = go.Figure(go.Bar(x=xs, y=rate["Taux d'épargne"],
                           marker_color=[charts.GOOD if v >= 0 else charts.BAD for v in rate["Taux d'épargne"].fillna(0)],
                           hovertemplate="%{y:.0f} %<extra></extra>"))
    avg = tot["economise"] / tot["salaire"] * 100 if tot["salaire"] else None
    if avg is not None:
        fig.add_hline(y=avg, line_dash="dot", line_color=charts.MUTED,
                      annotation_text=f"moyenne {avg:.0f} %", annotation_position="top left")
    plot(charts.layout(fig, 300, legend=False, yfmt=".0f", ysuffix=" %"), key="rate")
with r:
    st.subheader("Économies cumulées")
    cum = g["economise"].cumsum()
    fig = go.Figure(go.Scatter(x=cum.index, y=cum, fill="tozeroy", line=dict(color=charts.GOOD, width=2),
                               fillcolor="rgba(60,207,122,0.15)", hovertemplate="%{y:,.0f} €<extra>Cumul</extra>"))
    plot(charts.layout(fig, 300, legend=False), key="cum")

# ------------------------------------------------------------- tableau
st.subheader("Détail")
table = pd.DataFrame({
    "Période": [x.strftime("%m/%Y") if isinstance(x, pd.Timestamp) else x for x in xs],
    "Salaire": view["salaire"].values, "Loyer": view["loyer"].values,
    "Dépenses hors loyer": view["depenses"].values, "Économisé": view["economise"].values,
    "Taux": (view["taux"] * 100).values, "Investi": view["investi"].values, "Livrets (net)": view["livrets"].values,
})
money = st.column_config.NumberColumn(format="%,.0f €")
st.caption("Cliquez sur une ligne pour voir toutes les dépenses hors loyer de la période.")
table = table.iloc[::-1].reset_index(drop=True)
sel_ev = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                      key=f"glob_sel_{gran}", column_config={
    "Salaire": money, "Loyer": money, "Dépenses hors loyer": money,
    "Économisé": st.column_config.NumberColumn(format="%+,.0f €"),
    "Taux": st.column_config.NumberColumn(format="%.0f %%"),
    "Investi": st.column_config.NumberColumn(format="%+,.0f €"),
    "Livrets (net)": st.column_config.NumberColumn(format="%+,.0f €")})
if sel_ev.selection.rows:
    i = sel_ev.selection.rows[0]
    per = list(view.index)[::-1][i]
    if gran == "Année":
        part_tx, title = tx[tx["month"].dt.year == per], f"Dépenses hors loyer — {per}"
    else:
        part_tx, title = tx[tx["month"] == per], f"Dépenses hors loyer — {charts.mois(per)}"
    if st.session_state.get("_glob_last") != (gran, i):
        st.session_state["_glob_last"] = (gran, i)
        operations_dialog(title, budget.global_ops(part_tx, "depenses", refunds))
    elif st.button("Rouvrir le détail", type="tertiary", icon=":material/open_in_new:"):
        operations_dialog(title, budget.global_ops(part_tx, "depenses", refunds))

# ------------------------------------------------------------- mis de côté
st.subheader("Où est allé l'argent mis de côté")
st.caption("Investi : virements vers les courtiers. Livrets : versements moins retraits du mois, les allers-retours "
           "entre le compte courant et les livrets s'annulent.")
fig = go.Figure()
for col, lab, color in (("investi", "Investi (courtiers)", charts.SERIES[0]), ("livrets", "Livrets (net)", charts.SERIES[3])):
    fig.add_trace(go.Bar(x=xs, y=view[col], name=lab, marker_color=color,
                         hovertemplate="%{y:+,.0f} €<extra>" + lab + "</extra>"))
fig.update_layout(barmode="relative", bargap=0.3)
plot(charts.layout(fig, 320), key="aside")
cumul = pd.DataFrame({"Investi cumulé": g["investi"].cumsum(), "Livrets cumulés (net)": g["livrets"].cumsum(),
                      "Économisé cumulé": g["economise"].cumsum()})
plot(charts.line(cumul, list(cumul.columns), height=300,
                 colors={"Investi cumulé": charts.SERIES[0], "Livrets cumulés (net)": charts.SERIES[3],
                         "Économisé cumulé": charts.GOOD}), key="aside_cum")
