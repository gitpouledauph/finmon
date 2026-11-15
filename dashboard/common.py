"""Éléments partagés par les pages du dashboard."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finmon import config  # noqa: E402
from finmon.charts import eur, pct  # noqa: E402,F401
from finmon.data import Bundle, load  # noqa: E402
from finmon.db import DB  # noqa: E402

PERIODS = {"1M": 30, "3M": 91, "6M": 182, "YTD": None, "1A": 365, "3A": 1095, "Tout": 0}


def profile_name() -> str:
    return st.session_state.get("profile", "reel")


def get_db() -> DB:
    return DB(config.get_profile(profile_name()).db_path)


@st.cache_data(show_spinner="Calcul du portefeuille…")
def _load(db_path: str, mtime: float, today: str):
    return load(DB(db_path), today=date.fromisoformat(today))


def bundle() -> Bundle:
    db = get_db()
    mtime = db.path.stat().st_mtime if db.path.exists() else 0.0
    return _load(str(db.path), mtime, date.today().isoformat())


def invalidate() -> None:
    _load.clear()
    config.reload()
    from finmon.analytics import budget

    budget._compiled_rules.cache_clear()


def period_start(key: str, last: pd.Timestamp, first: pd.Timestamp) -> pd.Timestamp:
    if key == "YTD":
        return pd.Timestamp(last.year, 1, 1)
    days = PERIODS[key]
    return first if not days else max(first, last - pd.Timedelta(days=days))


def period_picker(key: str = "period", default: str = "1A") -> str:
    return st.segmented_control("Période", list(PERIODS), default=default, key=key,
                                label_visibility="collapsed") or default


def empty_state(what: str = "données") -> None:
    st.info(
        f"Pas encore de {what}. Déposez vos exports dans la page **Données**, "
        "ou passez sur le profil **Démo** dans la barre latérale pour voir le dashboard rempli.",
        icon="📭",
    )


def show_warnings(b: Bundle) -> None:
    if b.warnings:
        with st.expander(f"⚠️ {len(b.warnings)} point(s) d'attention sur les données"):
            for w in b.warnings:
                st.write("• " + w)


def kpi(col, label: str, value: str, delta: str | None = None, help: str | None = None, delta_color: str = "normal"):
    col.metric(label, value, delta, help=help, delta_color=delta_color)


def plot(fig, key: str | None = None):
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "locale": "fr"}, key=key)


def download_df(df: pd.DataFrame, name: str, label: str = "Exporter (CSV)"):
    st.download_button(label, df.to_csv(index=True, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=f"{name}.csv", mime="text/csv", key=f"dl-{name}")
