"""Investment performance: value, P&L, benchmark, attribution, positions, realized trades."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from common import (bundle, closed_trades_dialog, detail_button, download_df, empty_state, eur, pct, period_picker,
                    period_start, plot, show_warnings, signed_style)
from finmon import charts
from finmon.analytics import portfolio

b = bundle()
pf = b.portfolio
if pf.accounts.empty:
    st.title("Performance")
    empty_state("investment accounts")
    st.stop()

names = b.accounts.set_index("id")["name"].to_dict()
inv_ids = sorted(pf.accounts["account_id"].unique(), key=lambda a: names.get(a, a))
head, right = st.columns([2, 3], vertical_alignment="bottom")
head.title("Performance")
sel = right.pills("Accounts", inv_ids, selection_mode="multi", default=inv_ids,
                  format_func=lambda a: names.get(a, a), label_visibility="collapsed")
if not sel:
    st.stop()
show_warnings(b, "perf")
s = portfolio.summary(pf, sel)
ser = s["series"]

# ------------------------------------------------------------- KPIs
c = st.columns(4)
c[0].metric("Market value", eur(s["value"]))
c[1].metric("Net invested", eur(s["net_invested"]))
c[2].metric("Total P&L", eur(s["pnl_total"], sign=True),
            pct(s["pnl_total"] / s["net_invested"]) if s["net_invested"] > 0 else None)
c[3].metric("TWR", pct(s["twr"]), f"IRR {pct(s['xirr'])} p.a." if s["xirr"] is not None else None, delta_color="off")
c = st.columns(4)
c[0].metric("Unrealized", eur(s["latent"], sign=True), pct(s["latent"] / s["cost"]) if s["cost"] else None)
c[1].metric("Realized", eur(s["realized"], sign=True))
if detail_button(c[1], "rz_dialog", "Closed trades") and not pf.closed.empty:
    closed_trades_dialog(pf.closed[pf.closed["account_id"].isin(sel)], names)
c[2].metric("Dividends & interest", eur(s["dividends"] + s["interest"]))
c[3].metric("Fees & taxes", eur(s["fees"]))

# ------------------------------------------------------------- charts
key = period_picker("inv_period", "All")
last = ser.index[-1]
start = period_start(key, last, ser.index[(ser["total"] > 0).argmax()])
view = ser[ser.index >= start]

BENCHMARKS = {
    "MSCI World": "IWDA.AS", "S&P 500": "SXR8.DE", "Nasdaq-100": "SXRV.DE", "Euro Stoxx 50": "^STOXX50E",
    "CAC 40": "^FCHI", "DAX": "^GDAXI", "IBEX 35": "^IBEX", "MSCI Emerging Markets": "IS3N.DE",
    "Gold": "4GLD.DE", "Bitcoin": "BTC-EUR",
}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _bench(ticker: str, start: str) -> pd.Series:
    import yfinance as yf

    try:
        h = yf.Ticker(ticker).history(start=start, auto_adjust=True)["Close"]
    except Exception:
        return pd.Series(dtype=float)
    h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
    return h


l, r = st.columns(2)
with l:
    theme.section("Value vs invested capital")
    df = view.rename(columns={"total": "Value", "invested": "Invested"})
    plot(charts.line(df, ["Value", "Invested"], height=300, dash={"Invested": "dot"},
                     colors={"Value": charts.CAT[0], "Invested": charts.INK_MUTED}), key="val")
with r:
    hl, hr = st.columns([1, 1], vertical_alignment="bottom")
    with hl:
        theme.section("Relative performance")
    bench_names = hr.multiselect("Benchmarks", list(BENCHMARKS), default=["MSCI World"], max_selections=4,
                                 label_visibility="collapsed", placeholder="Add benchmark")
    perf = pd.DataFrame({"Portfolio": view["twr"] / view["twr"].iloc[0] * 100})
    for i, bn in enumerate(bench_names):
        h = _bench(BENCHMARKS[bn], (view.index[0] - pd.Timedelta(days=7)).strftime("%Y-%m-%d"))
        if not h.empty:
            bm = h.reindex(h.index.union(view.index)).ffill().reindex(view.index)
            if bm.notna().any():
                perf[bn] = bm / bm.dropna().iloc[0] * 100
    cols = list(perf.columns)
    colors = {"Portfolio": charts.CAT[0]} | {bn: charts.CAT[i + 1] for i, bn in enumerate(cols[1:])}
    plot(charts.line(perf, cols, height=300, ysuffix="", yfmt=",.0f", hover_fmt=",.1f", colors=colors,
                     dash={bn: "dot" for bn in cols[1:]}), key="perf")

theme.section("P&L vs invested capital")
g0 = view["total"] - view["invested"]
lat = pf.positions[pf.positions["account_id"].isin(sel)].groupby("date")["latent"].sum().reindex(view.index).fillna(0.0)
fig = go.Figure()
fig.add_trace(go.Scatter(x=g0.index, y=g0.clip(lower=0), fill="tozeroy", mode="none",
                         fillcolor="rgba(52,195,143,0.16)", showlegend=False, hoverinfo="skip"))
fig.add_trace(go.Scatter(x=g0.index, y=g0.clip(upper=0), fill="tozeroy", mode="none",
                         fillcolor="rgba(240,106,106,0.16)", showlegend=False, hoverinfo="skip"))
fig.add_trace(go.Scatter(x=g0.index, y=g0, name="Total P&L", line=dict(color=charts.CAT[0], width=2),
                         hovertemplate="%{y:+,.0f} €<extra>Total P&L</extra>"))
fig.add_trace(go.Scatter(x=lat.index, y=lat, name="Unrealized", line=dict(color=charts.INK_MUTED, width=1.4, dash="dot"),
                         hovertemplate="%{y:+,.0f} €<extra>Unrealized</extra>"))
plot(charts.layout(fig, 300), key="gain")

# ------------------------------------------------------------- attribution
pos = pf.positions[pf.positions["account_id"].isin(sel)]
cur = pf.current[pf.current["account_id"].isin(sel)] if not pf.current.empty else pf.current
if not cur.empty:
    theme.section("Return attribution", "unrealized · local market vs currency")
    a = st.columns(4)
    a[0].metric("Cost basis", eur(s["cost"]))
    a[1].metric("Local market", eur(s["latent_local"], sign=True))
    a[2].metric("Currency", eur(s["latent_fx"], sign=True))
    a[3].metric("Interaction", eur(s["latent_cross"], sign=True))
    d = cur[cur["asset_class"] != "Épargne salariale"].assign(tot=lambda x: x["local"] + x["fx"]).sort_values("tot")
    fig = go.Figure()
    for col, lab, colr in (("local", "Local market", charts.CAT[0]), ("fx", "Currency", charts.CAT[1])):
        fig.add_trace(go.Bar(y=d["name"], x=d[col], name=lab, orientation="h", marker=dict(color=colr, line=dict(width=0)),
                             hovertemplate="%{y}<br>%{x:+,.0f} €<extra>" + lab + "</extra>"))
    fig = charts._clean(fig, max(260, 24 * len(d) + 60))
    fig.update_layout(barmode="relative", bargap=0.4, hovermode="closest")
    fig.update_yaxes(showgrid=False, ticksuffix="  ", tickfont=dict(color=charts.INK_MUTED))
    fig.update_xaxes(showgrid=True, gridcolor=charts.GRID, ticksuffix=" €", tickformat=",.0f", nticks=7,
                     zeroline=True, zerolinecolor="#3a4252", tickfont=dict(color=charts.INK_MUTED))
    plot(fig, key="fxpos")

    # --------------------------------------------------------- positions
    theme.section("Positions", f"{len(cur)} lines")
    t = pd.DataFrame({
        "Security": cur["name"], "Account": cur["account_id"].map(names), "Class": cur.get("asset_class"),
        "Qty": cur["qty"], "Avg cost": cur["pru"], "Price": cur["price"], "Value": cur["value"],
        "Weight": cur["value"] / cur["value"].sum() * 100, "P&L": cur["latent"], "P&L %": cur["perf"] * 100,
        "Local": cur["local"], "FX": cur["fx"],
    }).sort_values("Value", ascending=False)
    st.dataframe(signed_style(t, ["P&L", "P&L %", "Local", "FX"]).format({
        "Qty": "{:.4g}", "Avg cost": "{:,.2f}", "Price": "{:,.2f}", "Value": "{:,.0f} €", "Weight": "{:.1f} %",
        "P&L": "{:+,.0f} €", "P&L %": "{:+.1f} %", "Local": "{:+,.0f} €", "FX": "{:+,.0f} €"}, na_rep="—"),
        hide_index=True, width="stretch")
    download_df(t.set_index("Security"), "positions", "Export CSV")

# ------------------------------------------------------------- realized
cl = pf.closed[pf.closed["account_id"].isin(sel)] if not pf.closed.empty else pf.closed
if not cl.empty:
    trades_ = cl[~cl["fee_only"]].copy()
    theme.section("Realized P&L", f"{eur(cl['realized'].sum(), sign=True)} · {len(trades_)} closed trades")
    by_line = (trades_.groupby(["name", "account_id"])
               .agg(Trades=("date", "size"), Realized=("realized", "sum")).reset_index().sort_values("Realized"))
    by_line["Account"] = by_line["account_id"].map(names)
    l3, r3 = st.columns([2, 3])
    with l3:
        ev = st.dataframe(signed_style(by_line[["name", "Account", "Trades", "Realized"]].rename(columns={"name": "Security"}),
                                       ["Realized"]).format({"Realized": "{:+,.2f} €"}),
                          hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="rz_sel")
    with r3:
        det = trades_
        if ev.selection.rows:
            row = by_line.iloc[ev.selection.rows[0]]
            det = trades_[(trades_["name"] == row["name"]) & (trades_["account_id"] == row["account_id"])]
        det = det.sort_values("date", ascending=False)
        dd = pd.DataFrame({"Date": det["date"].dt.strftime("%d %b %Y"), "Security": det["name"], "Qty": det["quantity"],
                           "Cost": det["cost"], "Proceeds": det["proceeds"], "P&L": det["realized"],
                           "P&L %": (det["realized"] / det["cost"] * 100).where(det["cost"] > 0)})
        st.dataframe(signed_style(dd, ["P&L", "P&L %"]).format({"Qty": "{:.6g}", "Cost": "{:,.2f} €",
                                                                 "Proceeds": "{:,.2f} €", "P&L": "{:+,.2f} €",
                                                                 "P&L %": "{:+.1f} %"}, na_rep="—"),
                     hide_index=True, width="stretch")

inc = pf.income[pf.income["account_id"].isin(sel)].copy() if not pf.income.empty else pf.income
if not inc.empty:
    theme.section("Income & costs by year")
    inc["Year"] = inc["date"].dt.year
    piv = inc.pivot_table(index="Year", columns="kind", values="amount", aggfunc="sum", fill_value=0)
    piv = piv.rename(columns={"dividend": "Dividends", "interest": "Interest", "fee": "Fees", "tax": "Taxes"})
    st.dataframe(signed_style(piv, list(piv.columns)).format("{:+,.2f} €"), width="stretch")
