"""Market watch: price charts of every underlying held, each with its own timeframe."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from common import bundle, empty_state, profile_name
from finmon import charts

FRAMES = {  # label: (yfinance period, interval, keep last n days or None)
    "1D": ("1d", "5m", None), "3D": ("5d", "15m", 3), "1W": ("5d", "30m", None), "1M": ("1mo", "90m", None),
    "3M": ("3mo", "1d", None), "6M": ("6mo", "1d", None), "YTD": ("ytd", "1d", None), "1Y": ("1y", "1d", None),
    "5Y": ("5y", "1wk", None),
}
INDICES = {"MSCI World": "IWDA.AS", "S&P 500": "^GSPC", "Nasdaq-100": "^NDX", "Euro Stoxx 50": "^STOXX50E",
           "CAC 40": "^FCHI", "DAX": "^GDAXI", "EUR/USD": "EURUSD=X", "Gold": "GC=F", "Brent": "BZ=F", "Bitcoin": "BTC-EUR"}

b = bundle()
head, right = st.columns([1.4, 3], vertical_alignment="bottom")
head.title("Market watch")
default_frame = right.segmented_control("All charts", list(FRAMES), default="1M", key="mw_all",
                                        label_visibility="collapsed") or "1M"
if profile_name() == "demo":
    st.info("Live market data is not available on the demo profile.")
    st.stop()

cur = b.portfolio.current
held = []
if not cur.empty:
    c = cur[cur["ticker"].notna()].groupby("ticker").agg(name=("name", "first"), value=("value", "sum"))
    held = [(t, r["name"]) for t, r in c.sort_values("value", ascending=False).iterrows()]
extra = st.multiselect("Add markets", list(INDICES), default=[], placeholder="Indices, FX, commodities…",
                       label_visibility="collapsed")
items = held + [(INDICES[k], k) for k in extra]
if not items:
    empty_state("positions")
    st.stop()


@st.cache_data(ttl=300, show_spinner=False)
def _history(ticker: str, frame: str) -> tuple[pd.Series, str]:
    import yfinance as yf

    period, interval, keep = FRAMES[frame]
    try:
        tk = yf.Ticker(ticker)
        h = tk.history(period=period, interval=interval, auto_adjust=True)["Close"].dropna()
        ccy = (tk.fast_info.get("currency") or "") if hasattr(tk, "fast_info") else ""
    except Exception:
        return pd.Series(dtype=float), ""
    if h.empty:
        return h, ccy
    h.index = pd.to_datetime(h.index)
    if keep:
        days = sorted({d.date() for d in h.index})[-keep:]
        h = h[[d.date() in days for d in h.index]]
    return h, ccy


def _card(ticker: str, name: str, idx: int):
    top_l, top_r = st.columns([3, 1.1], vertical_alignment="center")
    frame = top_r.selectbox("Frame", list(FRAMES), index=list(FRAMES).index(default_frame),
                            key=f"mw_{ticker}_{default_frame}", label_visibility="collapsed")
    h, ccy = _history(ticker, frame)
    if h.empty:
        st.html(f"<div class='fm-eyebrow'>{name}</div><div style='color:#8b93a3;font-size:.8rem'>{ticker} · no data</div>")
        return
    first, last = float(h.iloc[0]), float(h.iloc[-1])
    chg = last / first - 1 if first else 0.0
    color = charts.GOOD if chg >= 0 else charts.BAD
    fill = "rgba(79,178,134,0.10)" if chg >= 0 else "rgba(224,108,117,0.10)"
    with top_l:
        st.html(f"<div style='font-weight:600;font-size:.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{name}</div>"
                f"<div style='color:#8a93a6;font-size:.72rem'>{ticker}</div>")
    st.html(f"<div style='display:flex;justify-content:space-between;align-items:baseline;margin-top:-4px'>"
            f"<span style='font-weight:600;font-size:1.15rem'>{last:,.2f} <span style='color:#8a93a6;font-size:.72rem'>{ccy}</span></span>"
            f"<span style='color:{color};font-size:.82rem;font-weight:500'>{chg * 100:+.2f} %</span></div>")
    lo, hi = float(h.min()), float(h.max())
    pad = (hi - lo) * 0.08 or hi * 0.01
    fig = go.Figure(go.Scatter(x=h.index, y=h.values, mode="lines", line=dict(color=color, width=1.6),
                               fill="tozeroy", fillcolor=fill, hovertemplate="%{x|%d %b %Y %H:%M}<br>%{y:,.2f}<extra></extra>"))
    fig.add_hline(y=first, line_dash="dot", line_color="#343c4d", line_width=1)
    fig = charts._clean(fig, 170, legend=False)
    fig.update_layout(margin=dict(l=4, r=4, t=4, b=4), hovermode="x")
    intraday = frame in ("1D", "3D", "1W")
    fig.update_xaxes(showgrid=False, tickfont=dict(color=charts.INK_MUTED, size=10), nticks=5,
                     tickformat="%H:%M" if frame == "1D" else ("%d %b" if intraday or frame in ("1M", "3M") else "%b %y"),
                     rangebreaks=[dict(bounds=["sat", "mon"])] if intraday and not ticker.endswith(("-EUR", "-USD")) else [])
    fig.update_yaxes(range=[lo - pad, hi + pad], showgrid=True, gridcolor=charts.GRID, tickfont=dict(color=charts.INK_MUTED, size=10),
                     nticks=4, tickformat=",.0f" if hi > 100 else ",.2f", zeroline=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"mwc_{ticker}_{idx}")


theme.section("Holdings" if held else "Markets", f"{len(items)} charts")
for i in range(0, len(items), 3):
    cols = st.columns(3)
    for j, (col, (t, name)) in enumerate(zip(cols, items[i:i + 3])):
        with col:
            with st.container(border=True):
                _card(t, name, i + j)
