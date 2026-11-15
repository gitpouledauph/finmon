import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import bundle, download_df, empty_state, eur, pct, period_picker, period_start, plot, show_warnings
from finmon import charts
from finmon.analytics import portfolio

b = bundle()
st.title("Performance des investissements")
pf = b.portfolio
if pf.accounts.empty:
    empty_state("comptes d'investissement")
    st.stop()
show_warnings(b)

names = b.accounts.set_index("id")["name"].to_dict()
inv_ids = sorted(pf.accounts["account_id"].unique())
sel = st.multiselect("Comptes", inv_ids, default=inv_ids, format_func=lambda a: names.get(a, a))
if not sel:
    st.stop()
s = portfolio.summary(pf, sel)
ser = s["series"]

# ------------------------------------------------------------- KPIs
c = st.columns(4)
c[0].metric("Valeur", eur(s["value"]), help="Titres + liquidités sur les comptes sélectionnés.")
c[1].metric("Versé net", eur(s["net_invested"]), help="Versements − retraits (ou achats − ventes si les versements ne sont pas connus).")
c[2].metric("Plus-value totale", eur(s["pnl_total"], sign=True), pct(s["pnl_total"] / s["net_invested"]) if s["net_invested"] > 0 else None)
c[3].metric("TWR / TRI", pct(s["twr"]), f"TRI {pct(s['xirr'])} /an" if s["xirr"] is not None else None,
            help="TWR : performance du portefeuille, neutre vis-à-vis du calendrier des versements. TRI : rendement annualisé de votre argent.")
c = st.columns(4)
c[0].metric("Plus-value latente", eur(s["latent"], sign=True), pct(s["latent"] / s["cost"]) if s["cost"] else None)
c[1].metric("Plus-value réalisée", eur(s["realized"], sign=True))
c[2].metric("Dividendes + intérêts", eur(s["dividends"] + s["interest"]))
c[3].metric("Frais et impôts", eur(s["fees"]),
            help="Frais de courtage et impôts prélevés (inclus dans le prix de revient / déduits des dividendes).")

# ------------------------------------------------------------- évolution
key = period_picker("inv_period", "Tout")
last = ser.index[-1]
start = period_start(key, last, ser.index[(ser["total"] > 0).argmax()])
view = ser[ser.index >= start]

left, right = st.columns(2)
with left:
    st.subheader("Valeur et capital investi")
    df = view.rename(columns={"total": "Valeur", "invested": "Capital investi"})
    plot(charts.line(df, ["Valeur", "Capital investi"], dash={"Capital investi": "dot"},
                     colors={"Valeur": charts.SERIES[0], "Capital investi": charts.MUTED}), key="val")
with right:
    st.subheader("Performance (base 100)")
    perf = pd.DataFrame({"Mon portefeuille": view["twr"] / view["twr"].iloc[0] * 100})
    bench_name = "Indice de référence"
    from finmon import config

    bench_name = config.settings()["benchmark"].get("name", bench_name)
    if not b.benchmark.empty:
        bm = b.benchmark.reindex(b.benchmark.index.union(view.index)).ffill().reindex(view.index)
        if bm.notna().any():
            perf[bench_name] = bm / bm.dropna().iloc[0] * 100
    plot(charts.line(perf, list(perf.columns), ysuffix="", yfmt=",.0f", hover_fmt=",.1f",
                     colors={"Mon portefeuille": charts.SERIES[0], bench_name: charts.MUTED},
                     dash={bench_name: "dot"}), key="perf")

# ------------------------------------------------------------- effet change
st.subheader("D'où vient la performance : sous-jacent ou change ?")
st.caption(
    "Pour chaque titre, la plus-value latente est séparée entre la performance du sous-jacent "
    "dans sa devise et l'effet de change EUR, selon l'exposition devise du sous-jacent "
    "(un ETF MSCI World coté en euros reste exposé ≈ 72 % au dollar). "
    "Exposition modifiable dans Données › Titres.")
pos = pf.positions[pf.positions["account_id"].isin(sel)]
cur = pf.current[pf.current["account_id"].isin(sel)] if not pf.current.empty else pf.current
if not cur.empty:
    l, r = st.columns([1, 1.2])
    with l:
        plot(charts.waterfall([("Sous-jacent", s["latent_local"]), ("Change", s["latent_fx"]),
                               ("Effet croisé", s["latent_cross"])],
                              "Prix de revient", s["cost"], "Valeur des titres"), key="wf")
    with r:
        d = cur.sort_values("value")
        fig = go.Figure()
        for col, lab in (("local", "Sous-jacent"), ("fx", "Change")):
            fig.add_trace(go.Bar(y=d["name"], x=d[col], name=lab, orientation="h",
                                 marker_color=charts.FIXED[lab], hovertemplate="%{x:,.0f} €<extra>" + lab + "</extra>"))
        fig.update_layout(barmode="group", bargap=0.3)
        fig = charts.layout(fig, max(300, 56 * len(d) + 60), ysuffix="")
        fig.update_layout(hovermode="y unified")
        fig.update_xaxes(ticksuffix=" €", tickformat=",.0f", showgrid=True, gridcolor=charts.GRID, nticks=5)
        plot(fig, key="fxpos")
    hist = pos.groupby("date")[["local", "fx"]].sum().rename(columns={"local": "Sous-jacent", "fx": "Change"})
    hist = hist[hist.index >= start]
    st.markdown("**Plus-value latente cumulée : sous-jacent vs change**")
    plot(charts.line(hist, ["Sous-jacent", "Change"], height=300), key="fxhist")
    if abs(s["realized"]) > 0.5:
        st.caption(f"Sur les ventes : réalisé {eur(s['realized'], sign=True)}, dont sous-jacent "
                   f"{eur(s['realized_local'], sign=True)} et change {eur(s['realized_fx'], sign=True)}.")

# ------------------------------------------------------------- positions
st.subheader("Positions")
if not cur.empty:
    t = pd.DataFrame({
        "Titre": cur["name"], "Compte": cur["account_id"].map(names), "ISIN": cur["isin"],
        "Quantité": cur["qty"], "PRU": cur["pru"], "Cours": cur["price"], "Valeur": cur["value"],
        "Poids": cur["value"] / cur["value"].sum() * 100, "+/- value": cur["latent"], "+/- %": cur["perf"] * 100,
        "dont sous-jacent": cur["local"], "dont change": cur["fx"], "Classe": cur.get("asset_class"),
    })
    st.dataframe(t, hide_index=True, width="stretch", column_config={
        "Quantité": st.column_config.NumberColumn(format="%.4g"),
        "PRU": st.column_config.NumberColumn(format="%.2f €"),
        "Cours": st.column_config.NumberColumn(format="%.2f €"),
        "Valeur": st.column_config.NumberColumn(format="%.0f €"),
        "Poids": st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100),
        "+/- value": st.column_config.NumberColumn(format="%+.0f €"),
        "+/- %": st.column_config.NumberColumn(format="%+.1f %%"),
        "dont sous-jacent": st.column_config.NumberColumn(format="%+.0f €"),
        "dont change": st.column_config.NumberColumn(format="%+.0f €"),
    })
    download_df(t.set_index("Titre"), "positions")

with st.expander("Plus-values réalisées, dividendes, intérêts et frais"):
    rz = pf.realized[pf.realized["account_id"].isin(sel)]
    rz = rz[rz["realized"].abs() > 0.005]
    if not rz.empty:
        st.dataframe(rz.rename(columns={"name": "Titre", "realized": "Réalisé", "r_local": "dont sous-jacent",
                                        "r_fx": "dont change", "r_cross": "croisé"}).drop(columns=["account_id"]),
                     hide_index=True, width="stretch")
    inc = pf.income[pf.income["account_id"].isin(sel)].copy()
    if not inc.empty:
        inc["Année"] = inc["date"].dt.year
        piv = inc.pivot_table(index="Année", columns="kind", values="amount", aggfunc="sum", fill_value=0)
        piv = piv.rename(columns={"dividend": "Dividendes", "interest": "Intérêts", "fee": "Frais", "tax": "Impôts"})
        st.dataframe(piv.style.format("{:,.2f} €"), width="stretch")
