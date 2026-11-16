"""Meridian — visual layer: Inter typography, quiet surfaces, one accent."""
import streamlit as st

ACCENT = "#7d9bd6"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root { --bg:#0b0e14; --panel:#121620; --panel2:#161b26; --line:#1f2533; --muted:#8a93a6; --ink:#e6e9ef;
        --accent:#7d9bd6; --gold:#c9a96e; --good:#4fb286; --bad:#e06c75; }
html, body, .stApp, .stMarkdown, button, input, textarea, select, [data-testid="stMetricValue"] {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
  font-feature-settings: 'tnum' 1, 'cv11' 1; }
.stApp { background: var(--bg); }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1360px; }
header[data-testid="stHeader"] { background: transparent; }

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"] { background: #0d1118; border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] .block-container, section[data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding-top: .6rem; }
[data-testid="stSidebarNav"] { padding-top: .2rem; }
[data-testid="stSidebarHeader"] { padding: 1rem 1rem .4rem 1rem; }
[data-testid="stSidebarLogo"], [data-testid="stLogo"] { height: 2.4rem !important; max-width: 13rem !important; }
[data-testid="stNavSectionHeader"] { text-transform: uppercase; letter-spacing: .09em; font-size: .66rem !important;
  color: #6b7383 !important; font-weight: 600; margin-top: .9rem; }
[data-testid="stSidebarNav"] a { border-radius: 8px; margin: 1px 0; padding: .32rem .6rem; }
[data-testid="stSidebarNav"] a span { color: #b9c0cc !important; font-size: .9rem; font-weight: 450; }
[data-testid="stSidebarNav"] a:hover { background: #161a22; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: rgba(125,155,214,.13); }
[data-testid="stSidebarNav"] a[aria-current="page"] span { color: var(--ink) !important; font-weight: 600; }
[data-testid="stSidebarNav"] a[aria-current="page"] [data-testid="stIconMaterial"] { color: var(--accent) !important; }
[data-testid="stSidebarNav"] [data-testid="stIconMaterial"] { color: #7d8595 !important; }
.fm-brand { display:flex; align-items:center; gap:.55rem; padding:.2rem 0 .8rem 0; }
.fm-brand .name { font-weight:700; font-size:1.12rem; letter-spacing:-.02em; color:var(--ink); }
.fm-brand .tag { font-size:.68rem; color:var(--muted); letter-spacing:.04em; text-transform:uppercase; margin-top:-2px; }
.fm-side-sep { height:1px; background:var(--line); margin:.6rem 0; }
.fm-live { font-size:.75rem; color:var(--muted); display:flex; align-items:center; gap:.4rem; }
.fm-live .dot { width:6px; height:6px; border-radius:50%; background:var(--good); display:inline-block; }

/* ---------- typography ---------- */
h1 { font-weight:650 !important; font-size:1.5rem !important; letter-spacing:-.02em; margin-bottom:.2rem !important; }
h2, h3 { font-weight:600 !important; letter-spacing:-.01em; }
h3 { font-size:.95rem !important; color:var(--ink); text-transform:none; margin-top:.6rem !important; }
[data-testid="stCaptionContainer"] { color: var(--muted) !important; }

/* ---------- cards ---------- */
[data-testid="stMetric"] { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 16px; }
[data-testid="stMetricDelta"] svg { display:none; }
[data-testid="stMetricLabel"] p { font-size:.68rem !important; text-transform:uppercase; letter-spacing:.08em;
  color:var(--muted) !important; font-weight:600; }
[data-testid="stMetricValue"] { font-weight:600; font-size:1.42rem !important; letter-spacing:-.02em; }
[data-testid="stMetricDelta"] { font-size:.78rem !important; }
[data-testid="stExpander"] details { border:1px solid var(--line); border-radius:12px; background:var(--panel); }
[data-testid="stDataFrame"], [data-testid="stTable"] { border:1px solid var(--line); border-radius:10px; }
[data-testid="stPlotlyChart"] { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:6px 6px 2px 6px; }
.stTabs [data-baseweb="tab-list"] { gap:1.1rem; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-weight:500; font-size:.88rem; }
hr { border-color: var(--line) !important; }

/* ---------- custom blocks ---------- */
.fm-eyebrow { text-transform:uppercase; letter-spacing:.09em; font-size:.68rem; color:var(--muted); font-weight:600; margin:0 0 .15rem 0; }
.fm-hero { font-size:2.4rem; font-weight:650; letter-spacing:-.03em; line-height:1.1; color:var(--ink); }
.fm-chip { display:inline-block; margin-top:.4rem; padding:.16rem .55rem; border-radius:999px; font-size:.8rem; font-weight:500; }
.fm-chip.up { color:var(--good); background:rgba(79,178,134,.12); }
.fm-chip.down { color:var(--bad); background:rgba(224,108,117,.12); }
.fm-sub { color:var(--muted); font-size:.8rem; margin-left:.5rem; }
.fm-section { display:flex; align-items:baseline; justify-content:space-between; margin:1.2rem 0 .4rem 0;
  border-bottom:1px solid var(--line); padding-bottom:.35rem; }
.fm-section .t { font-size:.78rem; text-transform:uppercase; letter-spacing:.09em; color:#c3c9d4; font-weight:600; }
.fm-section .n { font-size:.75rem; color:var(--muted); }
.fm-score { display:flex; align-items:center; gap:1rem; }
.fm-score .v { font-size:2.6rem; font-weight:700; letter-spacing:-.03em; }
.fm-bar { height:6px; background:#1b2029; border-radius:6px; overflow:hidden; }
.fm-bar > div { height:100%; border-radius:6px; }
</style>
"""

LOGO = """<svg width="26" height="26" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
<circle cx="16" cy="16" r="12" fill="none" stroke="#1e2633" stroke-width="5"/>
<circle cx="16" cy="16" r="12" fill="none" stroke="#7d9bd6" stroke-width="5" stroke-dasharray="48 100"
 transform="rotate(-90 16 16)" stroke-linecap="round"/>
<circle cx="16" cy="16" r="12" fill="none" stroke="#c9a96e" stroke-width="5" stroke-dasharray="14 100"
 stroke-dashoffset="-52" transform="rotate(-90 16 16)" stroke-linecap="round"/></svg>"""


def apply() -> None:
    st.html(CSS)


def brand() -> None:
    st.html(f"<div class='fm-brand'>{LOGO}<div><div class='name'>Meridian</div>"
            f"<div class='tag'>Wealth intelligence</div></div></div>")


def hero(label: str, value: str, delta: float | None = None, delta_txt: str = "", sub: str = "") -> None:
    chip = ""
    if delta is not None and delta == delta:
        cls = "up" if delta >= 0 else "down"
        arrow = "▲" if delta >= 0 else "▼"
        chip = f"<span class='fm-chip {cls}'>{arrow} {delta_txt}</span><span class='fm-sub'>{sub}</span>"
    st.html(f"<div class='fm-eyebrow'>{label}</div><div class='fm-hero'>{value}</div>{chip}")


def section(title: str, note: str = "") -> None:
    st.html(f"<div class='fm-section'><span class='t'>{title}</span><span class='n'>{note}</span></div>")
