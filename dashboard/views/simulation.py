"""Simulation : où en seraient les lignes du portefeuille si elles rendaient comme sur les 10 dernières années."""
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import bundle, empty_state, eur, plot, profile_name
from finmon import charts
from finmon.analytics import simulation as sim

b = bundle()
st.title("Line simulator")
cur = b.portfolio.current
if cur.empty:
    empty_state("positions")
    st.stop()
pass

ETF_RE = re.compile(r"\bETF\b|UCITS|AMUNDI|ISHARES|VANECK|LYXOR|XTRACKERS|SPDR|VANGUARD|INVESCO|WISDOMTREE|"
                    r"\bPEA\b.*(?:NASDAQ|S&P|MSCI|STOXX)|PROFILE", re.I)
names = b.accounts.set_index("id")["name"].to_dict()
lines = (cur.assign(acc=cur["account_id"].map(names))
         .groupby("ticker", dropna=True)
         .agg(Ligne=("name", "first"), Comptes=("acc", lambda s: ", ".join(sorted(set(s)))),
              value=("value", "sum"), currency=("currency", "first"), asset_class=("asset_class", "first"))
         .reset_index())
lines = lines[lines["value"] > 1]
lines["ETF"] = lines["Ligne"].fillna("").str.contains(ETF_RE)

c1, c2, c3 = st.columns([1, 1, 2])
horizon = c1.segmented_control("Horizon", [5, 10, 15, 20], default=10, format_func=lambda y: f"{y} ans") or 10
scope = c2.segmented_control("Lignes", ["ETF", "Toutes"], default="ETF") or "ETF"
view = lines[lines["ETF"]] if scope == "ETF" else lines
if view.empty:
    st.info("No ETF line found.")
    st.stop()

if profile_name() == "demo":
    st.info("Not available on the demo profile.")
    st.stop()


@st.cache_data(ttl=24 * 3600, show_spinner="Téléchargement de 10 ans d'historique…")
def _stats(tickers: tuple, currencies: tuple):
    close = sim.monthly_history(list(tickers), dict(currencies))
    return sim.stats_from_history(close), close


stats, close = _stats(tuple(sorted(lines["ticker"])), tuple(sorted(zip(lines["ticker"], lines["currency"].fillna("EUR")))))
view = view.assign(
    years=view["ticker"].map(lambda t: stats[t].years if t in stats else 0.0),
    cagr=view["ticker"].map(lambda t: stats[t].cagr if t in stats else None),
    vol=view["ticker"].map(lambda t: stats[t].vol if t in stats else None),
).sort_values("value", ascending=False)

# ------------------------------------------------------------- hypothèses modifiables
st.subheader("Assumptions")
pass
hyp = pd.DataFrame({
    "Ligne": view["Ligne"], "Ticker": view["ticker"], "Comptes": view["Comptes"], "Valeur": view["value"],
    "Historique (ans)": view["years"].round(1), "Rendement / an (%)": (view["cagr"] * 100).round(1),
    "Volatilité (%)": (view["vol"] * 100).round(1), "Versement / mois (€)": 0.0,
})
ed = st.data_editor(hyp, hide_index=True, width="stretch", key=f"hyp_{scope}",
                    disabled=["Ligne", "Ticker", "Comptes", "Valeur", "Historique (ans)"],
                    column_config={
                        "Valeur": st.column_config.NumberColumn(format="%,.0f €"),
                        "Rendement / an (%)": st.column_config.NumberColumn(format="%.1f %%", min_value=-50.0, max_value=100.0),
                        "Volatilité (%)": st.column_config.NumberColumn(format="%.1f %%", min_value=0.0, max_value=200.0),
                        "Versement / mois (€)": st.column_config.NumberColumn(format="%,.0f €", min_value=0.0, step=50.0)})
short = ed[ed["Historique (ans)"] < 5]["Ligne"].tolist()
wild = ed[(ed["Volatilité (%)"] > 60) | (ed["Rendement / an (%)"] > 40)]["Ligne"].tolist()
if short:
    st.caption("Historique de moins de 5 ans (rendement peu représentatif) : " + ", ".join(short) + ".")
if wild:
    st.warning("Rendement ou volatilité extrêmes (" + ", ".join(wild) + ") : prolonger un tel rendement sur "
               "plusieurs années donne des montants irréalistes. Mieux vaut saisir une hypothèse prudente.")

# ------------------------------------------------------------- projections par ligne
rows = []
for r in ed.itertuples(index=False):
    rr = None if pd.isna(r[5]) else r[5] / 100
    vv = None if pd.isna(r[6]) else r[6] / 100
    p = sim.project(r.Valeur, rr, vv, horizon, r[7] or 0.0)
    rows.append({"Ligne": r.Ligne, "Aujourd'hui": r.Valeur, "Versé d'ici là": p["invested"],
                 f"Dans {horizon} ans": p["central"], "Fourchette basse": p["low"], "Fourchette haute": p["high"],
                 "Multiplié par": (p["central"] / p["invested"]) if p["central"] and p["invested"] else None})
res = pd.DataFrame(rows)

# Portefeuille : combinaison des rendements mensuels pondérés par la valeur actuelle.
valid = ed.dropna(subset=["Rendement / an (%)"])
w = valid.set_index("Ticker")["Valeur"]
w = w / w.sum()
port_r = float((valid.set_index("Ticker")["Rendement / an (%)"] / 100 * w).sum())
rets = close[[t for t in w.index if t in close.columns]].pct_change(fill_method=None)
port_series = rets.mul(w.reindex(rets.columns), axis=1).sum(axis=1, min_count=1).dropna()
port_vol = float(port_series.std() * (12 ** 0.5)) if len(port_series) > 12 else None
monthly_total = float(ed["Versement / mois (€)"].fillna(0).sum())
pp = sim.project(float(ed["Valeur"].sum()), port_r, port_vol, horizon, monthly_total)

k = st.columns(4)
k[0].metric("Valeur aujourd'hui", eur(ed["Valeur"].sum()), help="Lignes affichées uniquement.")
k[1].metric(f"Projection à {horizon} ans", eur(pp["central"]),
            f"rendement moyen pondéré {port_r * 100:.1f} % / an".replace(".", ","), delta_color="off")
k[2].metric("Fourchette (10 % – 90 %)", f"{eur(pp['low'])} – {eur(pp['high'])}",
            help="Quantiles 10 % et 90 % d'un modèle log-normal utilisant la volatilité du portefeuille "
                 "(rendements mensuels combinés selon les poids actuels).")
k[3].metric("Total versé", eur(pp["invested"]), f"dont {eur(monthly_total)} / mois" if monthly_total else None,
            delta_color="off")

st.dataframe(res, hide_index=True, width="stretch", column_config={
    c: st.column_config.NumberColumn(format="%,.0f €") for c in res.columns if c not in ("Ligne", "Multiplié par")} | {
    "Multiplié par": st.column_config.NumberColumn(format="× %.2f")})

# ------------------------------------------------------------- trajectoire
st.subheader("Trajectory")
choices = ["Portefeuille (lignes affichées)"] + ed["Ligne"].tolist()
pick = st.selectbox("Line", choices, label_visibility="collapsed")
if pick == choices[0]:
    traj = sim.path(float(ed["Valeur"].sum()), port_r, port_vol, horizon, monthly_total)
else:
    r = ed[ed["Ligne"] == pick].iloc[0]
    rr = None if pd.isna(r["Rendement / an (%)"]) else r["Rendement / an (%)"] / 100
    vv = None if pd.isna(r["Volatilité (%)"]) else r["Volatilité (%)"] / 100
    traj = sim.path(float(r["Valeur"]), rr, vv, horizon, float(r["Versement / mois (€)"] or 0))
if traj["central"].isna().all():
    st.info("Not enough history: set a return in the assumptions.")
else:
    years = [pd.Timestamp.today().year + y for y in traj.index]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=years, y=traj["high"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=years, y=traj["low"], fill="tonexty", fillcolor="rgba(57,135,229,0.15)",
                             line=dict(width=0), name="Fourchette 10–90 %",
                             hovertemplate="%{y:,.0f} €<extra>Basse</extra>"))
    fig.add_trace(go.Scatter(x=years, y=traj["central"], name="Projection centrale",
                             line=dict(color=charts.SERIES[0], width=2), hovertemplate="%{y:,.0f} €<extra>Centrale</extra>"))
    fig.add_trace(go.Scatter(x=years, y=traj["invested"], name="Total versé",
                             line=dict(color=charts.MUTED, width=1.5, dash="dot"), hovertemplate="%{y:,.0f} €<extra>Versé</extra>"))
    fig.update_xaxes(dtick=1 if horizon <= 10 else 5)
    plot(charts.layout(fig, 360), key="traj")
