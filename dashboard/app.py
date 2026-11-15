"""Point d'entrée du dashboard : streamlit run dashboard/app.py"""
import streamlit as st

st.set_page_config(page_title="finmon", page_icon="📊", layout="wide")

from common import invalidate  # noqa: E402

pages = [
    st.Page("views/accueil.py", title="Vue d'ensemble", icon="🏠", default=True),
    st.Page("views/investissements.py", title="Investissements", icon="📈"),
    st.Page("views/allocation.py", title="Allocation & exposition", icon="🧭"),
    st.Page("views/depenses.py", title="Dépenses", icon="💸"),
    st.Page("views/vacances.py", title="Vacances", icon="🏖️"),
    st.Page("views/revenus.py", title="Revenus & épargne", icon="💰"),
    st.Page("views/donnees.py", title="Données & imports", icon="📥"),
]

with st.sidebar:
    st.markdown("### 📊 finmon")
    st.caption("Moniteur local — vos données restent sur cette machine.")
    choice = st.radio("Profil", ["Mes données", "Démo"], horizontal=True,
                      index=1 if st.session_state.get("profile") == "demo" else 0)
    new = "demo" if choice == "Démo" else "reel"
    if new != st.session_state.get("profile"):
        st.session_state["profile"] = new
        invalidate()
    if st.button("↻ Recalculer", width="stretch"):
        invalidate()
        st.rerun()

st.navigation(pages).run()
