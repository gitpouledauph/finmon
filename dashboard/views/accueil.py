import pandas as pd
import streamlit as st

from common import bundle, empty_state, eur, pct, period_picker, period_start, plot, show_warnings
from finmon import charts
from finmon.analytics import budget, portfolio

b = bundle()
st.title("Vue d'ensemble")
if not b.has_data or b.networth.empty:
    empty_state()
    st.stop()
show_warnings(b)

nw = b.networth.copy()
by_bucket = nw.pivot_table(index="date", columns="bucket", values="value", aggfunc="sum").fillna(0.0).sort_index()
total = by_bucket.sum(axis=1)
last = total.index[-1]

key = period_picker("home_period", "1A")
start = period_start(key, last, total.index[0])
t0 = total.asof(start)

pf = portfolio.summary(b.portfolio) if not b.portfolio.accounts.empty else {}
flows = budget.monthly_flows(b.tx)
full_months = flows[flows.index < pd.Timestamp(last.year, last.month, 1)]
last12 = full_months.tail(12)

# ------------------------------------------------------------- héros + KPIs
c0, c1, c2, c3 = st.columns([1.4, 1, 1, 1])
c0.metric("Patrimoine net", eur(total.iloc[-1]), f"{eur(total.iloc[-1] - t0, sign=True)} sur {key}",
          help="Comptes courants + livrets + valeur des comptes-titres et PEA (titres + liquidités).")
inv = by_bucket.get("Investissements", pd.Series([0.0]))
c1.metric("Investissements", eur(inv.iloc[-1]),
          f"{eur(pf.get('pnl_total'), sign=True)} de plus-value" if pf else None,
          help="Plus-value totale = valeur actuelle − argent net versé (latent + réalisé + dividendes + intérêts − frais).")
c2.metric("Épargne réglementée", eur(by_bucket.get("Épargne réglementée", pd.Series([0.0])).iloc[-1]))
c3.metric("Liquidités", eur(by_bucket.get("Liquidités", pd.Series([0.0])).iloc[-1]))

c4, c5, c6, c7 = st.columns([1.4, 1, 1, 1])
if not full_months.empty:
    lm = full_months.iloc[-1]
    avg = last12["expenses"].mean()
    c4.metric(f"Dépenses {charts.mois(full_months.index[-1])}", eur(lm["expenses"]),
              f"{eur(lm['expenses'] - avg, sign=True)} vs moyenne 12 mois", delta_color="inverse")
    c5.metric("Revenus (moy. 12 mois)", eur(last12["income"].mean()))
    rate = last12["savings"].sum() / last12["income"].sum() if last12["income"].sum() else None
    c6.metric("Taux d'épargne 12 mois", pct(rate, 0, sign=False),
              help="(revenus − dépenses) / revenus. Les virements vers livrets/courtiers ne sont pas des dépenses.")
if pf:
    c7.metric("Performance (TWR)", pct(pf["twr"]), f"TRI annualisé {pct(pf['xirr'])}" if pf.get("xirr") is not None else None,
              help="TWR : performance indépendante des versements, sur tout l'historique. "
                   "TRI : rendement annualisé de votre argent, versements compris.")

# ------------------------------------------------------------- évolution
st.subheader("Évolution du patrimoine")
view = by_bucket[by_bucket.index >= start]
order = [c for c in ["Investissements", "Épargne réglementée", "Liquidités", "Autres actifs"] if c in view.columns]
plot(charts.line(view, order, height=380, area=True), key="nw")

left, right = st.columns(2)
with left:
    st.subheader("Par compte")
    cur = nw[nw["date"] == last].groupby("name")["value"].sum().sort_values(ascending=False)
    cur = cur[cur.abs() > 0.5]
    plot(charts.hbar(cur.index, cur.values, text=[eur(v) for v in cur.values]), key="acc")
with right:
    st.subheader(f"Variation sur {key}")
    by_acc = nw.pivot_table(index="date", columns="name", values="value", aggfunc="sum").ffill().fillna(0.0)
    delta = (by_acc.iloc[-1] - by_acc.asof(start)).sort_values(ascending=False)
    delta = delta[delta.abs() > 0.5]
    plot(charts.signed_hbar(delta.index, delta.values), key="delta")

if not full_months.empty:
    st.subheader("Revenus et dépenses — 12 derniers mois")
    m = last12.rename(columns={"income": "Revenus", "expenses": "Dépenses"})
    import plotly.graph_objects as go

    fig = go.Figure()
    for c in ["Revenus", "Dépenses"]:
        fig.add_trace(go.Bar(x=m.index, y=m[c], name=c, marker_color=charts.FIXED[c],
                             hovertemplate="%{y:,.0f} €<extra>" + c + "</extra>"))
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    plot(charts.layout(fig, 320), key="ie")
