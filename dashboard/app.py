"""Meridian — entry point: streamlit run dashboard/app.py"""
import time

import streamlit as st

st.set_page_config(page_title="Meridian", page_icon=":material/donut_small:", layout="wide",
                   initial_sidebar_state="expanded")

from common import get_db, invalidate  # noqa: E402
import theme  # noqa: E402

theme.apply()
from pathlib import Path  # noqa: E402

_static = Path(__file__).parent / "static"
st.logo(str(_static / "logo.svg"), size="large", icon_image=str(_static / "icon.svg"))

P = {
    "home": st.Page("views/accueil.py", title="Net worth", icon=":material/space_dashboard:", default=True),
    "perf": st.Page("views/investissements.py", title="Performance", icon=":material/show_chart:"),
    "alloc": st.Page("views/allocation.py", title="Allocation", icon=":material/donut_large:"),
    "market": st.Page("views/marche.py", title="Market watch", icon=":material/monitoring:"),
    "fees": st.Page("views/frais.py", title="Fee scanner", icon=":material/percent:"),
    "proj": st.Page("views/projections.py", title="Projections & goals", icon=":material/flag:"),
    "sim": st.Page("views/simulation.py", title="Line simulator", icon=":material/insights:"),
    "entry": st.Page("views/saisie.py", title="Transactions", icon=":material/edit_note:"),
    "cash": st.Page("views/globale.py", title="Cash flow", icon=":material/account_balance_wallet:"),
    "month": st.Page("views/mois.py", title="Monthly review", icon=":material/calendar_month:"),
    "spend": st.Page("views/depenses.py", title="Spending", icon=":material/receipt_long:"),
    "income": st.Page("views/revenus.py", title="Savings accounts", icon=":material/savings:"),
    "travel": st.Page("views/vacances.py", title="Travel", icon=":material/flight:"),
    "data": st.Page("views/donnees.py", title="Data & imports", icon=":material/database:"),
}
pages = {
    "Overview": [P["home"]],
    "Investments": [P["perf"], P["alloc"], P["market"], P["fees"], P["proj"], P["sim"], P["entry"]],
    "Cash flow": [P["cash"], P["month"], P["spend"], P["income"], P["travel"]],
    "Settings": [P["data"]],
}

INTERVALS = {"1 min": 60, "5 min": 300, "15 min": 900}

with st.sidebar:
    choice = st.segmented_control("Profile", ["Personal", "Demo"],
                                  default="Demo" if st.session_state.get("profile") == "demo" else "Personal",
                                  label_visibility="collapsed") or "Personal"
    new = "demo" if choice == "Demo" else "reel"
    if new != st.session_state.get("profile"):
        st.session_state["profile"] = new
        invalidate()
    demo = new == "demo"
    st.session_state["_full_run"] = True

with st.sidebar:
    st.html("<div class='fm-side-sep'></div>")
    with st.expander("Market data", icon=":material/sync:"):
        live = st.toggle("Live prices", value=not demo, disabled=demo)
        every = INTERVALS[st.select_slider("Refresh", list(INTERVALS), value="5 min", disabled=not live or demo)]
        if st.button("Recompute", width="stretch", icon=":material/refresh:"):
            invalidate()
            st.rerun()

    if live and not demo:
        @st.fragment(run_every=every)
        def live_prices():
            from finmon import market

            last = st.session_state.get("_live_ts", 0.0)
            changed = False
            if time.time() - last >= every - 1:
                try:
                    n, hhmm = market.live_update(get_db())
                    st.session_state["_live_ts"] = time.time()
                    st.session_state["_live_label"] = hhmm
                    changed = n > 0
                except Exception as e:  # pas de réseau, quota…
                    st.session_state["_live_label"] = f"unavailable ({type(e).__name__})"
            st.html(f"<div class='fm-live'><span class='dot'></span>Prices · {st.session_state.get('_live_label', '—')}</div>")
            full = st.session_state.get("_full_run", False)
            st.session_state["_full_run"] = False
            if changed and not full:
                invalidate()
                st.rerun(scope="app")

        live_prices()

st.navigation(pages, expanded=True).run()
