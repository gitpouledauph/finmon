"""Fee scanner: running costs of funds, broker costs, fee drag, cheaper equivalents."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from common import bundle, empty_state, eur, get_db, invalidate, plot, profile_name, signed_style
from finmon import charts
from finmon.analytics import fees as fee_mod

b = bundle()
st.title("Fee scanner")
cur = b.portfolio.current
if cur.empty:
    empty_state("positions")
    st.stop()
if profile_name() == "demo":
    st.info("Fee data is fetched from Yahoo Finance and is not available on the demo profile.")
    st.stop()


@st.cache_data(ttl=24 * 3600, show_spinner="Fetching fund fees…")
def _ters(tickers: tuple) -> dict:
    return fee_mod.fetch_ter(list(tickers))


db = get_db()
ters = _ters(tuple(fee_mod.candidate_tickers(cur)))
ov = db.read("SELECT isin, ter FROM fee_overrides").set_index("isin")["ter"].to_dict()
types = b.accounts.set_index("id")["type"].to_dict()
names = b.accounts.set_index("id")["name"].to_dict()
r_assumed = st.sidebar.number_input("Gross return assumed (%)", value=6.0, step=0.5, key="fee_r") / 100
res = fee_mod.scan(cur, types, ters, ov, r_assumed)

trades = db.read("SELECT account_id, date, kind, amount, fees FROM trades")
trades["date"] = pd.to_datetime(trades["date"])
broker = trades.assign(cost=trades["fees"].fillna(0).abs() + (-trades["amount"]).where(trades["kind"] == "fee", 0).fillna(0))
last12 = broker[broker["date"] >= pd.Timestamp.today() - pd.DateOffset(months=12)]
invested_funds = res["value"].sum() if not res.empty else 0.0
annual = res["annual"].sum() if not res.empty else 0.0

k = st.columns(4)
k[0].metric("Fund running costs", f"{eur(annual)} / yr",
            f"weighted TER {annual / invested_funds * 100:.2f} %" if invested_funds else None, delta_color="off")
k[1].metric("Broker costs · 12 m", eur(last12["cost"].sum()), f"{eur(broker['cost'].sum())} all time", delta_color="off")
k[2].metric("Fee drag · 10 y", eur(res["drag10"].sum() if not res.empty else 0),
            f"{eur(res['drag20'].sum())} over 20 y" if not res.empty else None, delta_color="off")
k[3].metric("Potential saving", f"{eur(res['saving'].sum() if not res.empty else 0)} / yr",
            f"{int((res['saving'] > 0).sum())} line(s)" if not res.empty else None, delta_color="off")

if res.empty:
    st.info("No fund or ETF line found.")
    st.stop()

theme.section("Funds & ETFs", f"{len(res)} lines · TER from Yahoo Finance, editable")
t = pd.DataFrame({
    "isin": res["isin"], "Security": res["name"], "Account": res["account_id"].map(names), "Value": res["value"],
    "TER %": (res["ter"] * 100).round(3), "Cost / yr": res["annual"], "Drag 10 y": res["drag10"],
    "Cheaper equivalent": [f"{n} ({t_})" if isinstance(t_, str) else "—" for n, t_ in zip(res["alt_name"].fillna(""), res["alt_ticker"])],
    "Alt TER %": (res["alt_ter"] * 100).round(3), "Saving / yr": res["saving"],
}).sort_values("Cost / yr", ascending=False)
ed = st.data_editor(t, hide_index=True, width="stretch", key="fee_ed",
                    disabled=[c for c in t.columns if c != "TER %"],
                    column_config={"isin": None, "Value": st.column_config.NumberColumn(format="%,.0f €"),
                                   "TER %": st.column_config.NumberColumn(format="%.2f", min_value=0.0, max_value=5.0, step=0.01),
                                   "Cost / yr": st.column_config.NumberColumn(format="%,.2f €"),
                                   "Drag 10 y": st.column_config.NumberColumn(format="%,.0f €"),
                                   "Alt TER %": st.column_config.NumberColumn(format="%.2f"),
                                   "Saving / yr": st.column_config.NumberColumn(format="%,.2f €"),
                                   "Cheaper equivalent": st.column_config.TextColumn(width="large")})
if st.button("Save TER overrides"):
    before = t.set_index("isin")["TER %"]
    for r in ed.itertuples(index=False):
        v = r[4]
        if v == v and v is not None and (before[r.isin] != before[r.isin] or abs(v - before[r.isin]) > 1e-6):
            db.upsert("fee_overrides", pd.DataFrame([{"isin": r.isin, "ter": v / 100}]), mode="replace")
    invalidate()
    st.rerun()

l, r = st.columns(2)
with l:
    theme.section("Annual running cost by line")
    d = res.dropna(subset=["annual"]).sort_values("annual", ascending=False)
    plot(charts.hbar(d["name"], d["annual"], color=charts.CAT[1],
                     text=[f"{eur(v, 2)}  ·  {x * 100:.2f} %" for v, x in zip(d["annual"], d["ter"])]), key="fee_bar")
with r:
    theme.section("Cumulative fee drag", f"gross return {r_assumed * 100:.1f} %")
    yrs = list(range(0, 21))
    drag = [sum(fee_mod.fee_drag(v, x, y, r_assumed) for v, x in zip(d["value"], d["ter"])) for y in yrs]
    fig = go.Figure(go.Scatter(x=yrs, y=drag, fill="tozeroy", line=dict(color=charts.CAT[1], width=2),
                               fillcolor="rgba(242,166,90,0.15)", hovertemplate="Year %{x}: %{y:,.0f} €<extra></extra>"))
    fig = charts.layout(fig, max(260, 34 * len(d) + 40), legend=False)
    fig.update_xaxes(ticksuffix=" y", dtick=5)
    plot(fig, key="fee_drag")

theme.section("Broker costs by account")
bc = broker.assign(Year=broker["date"].dt.year).groupby(["account_id", "Year"])["cost"].sum().unstack(fill_value=0.0)
bc.index = [names.get(i, i) for i in bc.index]
st.dataframe(bc.style.format("{:,.2f} €"), width="stretch")
