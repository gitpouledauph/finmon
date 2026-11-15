"""Habillage visuel du dashboard : typographie Inter, cartes sobres, mode sombre."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, .stApp, .stMarkdown, button, input, textarea, select, [data-testid="stMetricValue"] {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
  font-feature-settings: 'tnum' 1, 'cv11' 1;
}
.stApp { background: var(--fm-bg); }
:root { --fm-bg:#0b0d12; --fm-card:#12151c; --fm-line:#1f2430; --fm-muted:#8a90a0; --fm-ink:#e8e9ed;
        --fm-good:#3ccf7a; --fm-bad:#f0625d; }
.block-container { padding-top: 2.2rem; max-width: 1280px; }
section[data-testid="stSidebar"] { background:#0e1117; border-right:1px solid var(--fm-line); }
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {
  text-transform: uppercase; letter-spacing:.08em; font-size:.68rem; color:var(--fm-muted); font-weight:600; }
h1 { font-weight:600 !important; font-size:1.65rem !important; letter-spacing:-.02em; }
h2, h3 { font-weight:600 !important; letter-spacing:-.01em; }
h3 { font-size:1.05rem !important; color:var(--fm-ink); }
[data-testid="stMetric"] { background:var(--fm-card); border:1px solid var(--fm-line); border-radius:12px;
  padding:14px 18px; }
[data-testid="stMetricLabel"] p { font-size:.72rem !important; text-transform:uppercase; letter-spacing:.07em;
  color:var(--fm-muted) !important; font-weight:500; }
[data-testid="stMetricValue"] { font-weight:600; font-size:1.55rem !important; letter-spacing:-.02em; }
[data-testid="stExpander"] details { border:1px solid var(--fm-line); border-radius:12px; background:var(--fm-card); }
[data-testid="stDataFrame"], [data-testid="stTable"] { border:1px solid var(--fm-line); border-radius:12px; }
.stTabs [data-baseweb="tab-list"] { gap: 1.2rem; border-bottom:1px solid var(--fm-line); }
.stTabs [data-baseweb="tab"] { font-weight:500; }
.fm-eyebrow { text-transform:uppercase; letter-spacing:.08em; font-size:.72rem; color:var(--fm-muted);
  font-weight:600; margin:0 0 .2rem 0; }
.fm-hero { font-size:2.6rem; font-weight:650; letter-spacing:-.03em; line-height:1.1; color:var(--fm-ink); }
.fm-chip { display:inline-block; margin-top:.45rem; padding:.18rem .55rem; border-radius:999px; font-size:.82rem;
  font-weight:500; }
.fm-chip.up { color:var(--fm-good); background:rgba(60,207,122,.12); }
.fm-chip.down { color:var(--fm-bad); background:rgba(240,98,93,.12); }
.fm-sub { color:var(--fm-muted); font-size:.82rem; margin-left:.5rem; }
.fm-brand { font-weight:700; font-size:1.15rem; letter-spacing:-.02em; color:var(--fm-ink); }
.fm-brand span { color:#3987e5; }
hr { border-color: var(--fm-line) !important; }
</style>
"""


def apply() -> None:
    st.html(CSS)


def hero(label: str, value: str, delta: float | None = None, delta_txt: str = "", sub: str = "") -> None:
    chip = ""
    if delta is not None and delta == delta:
        cls = "up" if delta >= 0 else "down"
        arrow = "▲" if delta >= 0 else "▼"
        chip = f"<span class='fm-chip {cls}'>{arrow} {delta_txt}</span><span class='fm-sub'>{sub}</span>"
    st.html(f"<div class='fm-eyebrow'>{label}</div><div class='fm-hero'>{value}</div>{chip}")
