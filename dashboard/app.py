"""Point d'entrée du dashboard : streamlit run dashboard/app.py"""
import time

import streamlit as st

st.set_page_config(page_title="finmon", page_icon=":material/donut_small:", layout="wide")

from common import get_db, invalidate  # noqa: E402
import theme  # noqa: E402

theme.apply()

P = {
    "accueil": st.Page("views/accueil.py", title="Patrimoine", icon=":material/space_dashboard:", default=True),
    "saisie": st.Page("views/saisie.py", title="Saisir une opération", icon=":material/edit_note:"),
    "investissements": st.Page("views/investissements.py", title="Performance", icon=":material/show_chart:"),
    "allocation": st.Page("views/allocation.py", title="Allocation & exposition", icon=":material/donut_large:"),
    "depenses": st.Page("views/depenses.py", title="Dépenses", icon=":material/receipt_long:"),
    "vacances": st.Page("views/vacances.py", title="Vacances", icon=":material/flight:"),
    "revenus": st.Page("views/revenus.py", title="Revenus & épargne", icon=":material/savings:"),
    "donnees": st.Page("views/donnees.py", title="Données & imports", icon=":material/database:"),
}
pages = {
    "Synthèse": [P["accueil"]],
    "Investissement": [P["investissements"], P["allocation"], P["saisie"]],
    "Analyse des dépenses": [P["depenses"], P["revenus"], P["vacances"]],
    "Données": [P["donnees"]],
}

INTERVALS = {"1 min": 60, "5 min": 300, "15 min": 900}

with st.sidebar:
    st.html("<div class='fm-brand'>fin<span>mon</span></div>")
    st.caption("Moniteur local — vos données restent sur cette machine.")
    choice = st.radio("Profil", ["Mes données", "Démo"], horizontal=True,
                      index=1 if st.session_state.get("profile") == "demo" else 0)
    new = "demo" if choice == "Démo" else "reel"
    if new != st.session_state.get("profile"):
        st.session_state["profile"] = new
        invalidate()
    demo = new == "demo"

    live = st.toggle("Cours en direct", value=not demo, disabled=demo,
                     help="Récupère le dernier cours de vos titres (temps réel pour la crypto, "
                          "différé ~15 min pour la plupart des bourses) et recalcule valeurs et PnL.")
    every = INTERVALS[st.select_slider("Actualisation", list(INTERVALS), value="5 min", disabled=not live or demo)]
    st.session_state["_full_run"] = True

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
                    st.session_state["_live_label"] = f"indisponible ({type(e).__name__})"
            st.caption(f"Derniers cours : {st.session_state.get('_live_label', '—')}")
            full = st.session_state.get("_full_run", False)
            st.session_state["_full_run"] = False
            if changed and not full:
                invalidate()
                st.rerun(scope="app")

        live_prices()

    if st.button("Recalculer", width="stretch"):
        invalidate()
        st.rerun()

st.navigation(pages).run()
