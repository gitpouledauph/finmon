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
        f"Pas encore de {what}. Importez vos exports dans **Données & imports**, "
        "ou passez sur le profil **Démo** dans la barre latérale pour voir le dashboard rempli."
    )


# ------------------------------------------------------------------ alertes
# Les alertes masquées sont gardées dans data/<profil>/alertes_masquees.json (pas dans la base :
# masquer une alerte ne doit pas relancer le calcul du portefeuille).
def alert_key(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _alerts_path() -> Path:
    return config.get_profile(profile_name()).data_dir / "alertes_masquees.json"


def dismissed_alerts() -> dict[str, dict]:
    import json

    try:
        return json.loads(_alerts_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_dismissed(texts: list[str], hide: bool = True) -> None:
    import json

    cur = dismissed_alerts()
    now = pd.Timestamp.now().isoformat(timespec="seconds")
    for t in texts:
        if hide:
            cur[alert_key(t)] = {"text": t, "ts": now}
        else:
            cur.pop(alert_key(t), None)
    _alerts_path().write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")


def show_warnings(b: Bundle, where: str = "page") -> None:
    """Points d'attention sur les données, chacun masquable."""
    if not b.warnings:
        return
    hidden = dismissed_alerts()
    active = [w for w in dict.fromkeys(b.warnings) if alert_key(w) not in hidden]
    if not active:
        return
    n = len(active)
    with st.expander(f"{n} point{'s' if n > 1 else ''} d'attention sur les données"):
        for w in active:
            c1, c2 = st.columns([12, 2], vertical_alignment="center")
            c1.markdown(w)
            if c2.button("Masquer", key=f"dismiss-{where}-{alert_key(w)}", width="stretch"):
                set_dismissed([w])
                st.rerun()
        if n > 1 and st.button("Tout masquer", key=f"dismiss-all-{where}", type="tertiary"):
            set_dismissed(active)
            st.rerun()
        st.caption("Les alertes masquées se réaffichent dans Données & imports › État des données.")


def kpi(col, label: str, value: str, delta: str | None = None, help: str | None = None, delta_color: str = "normal"):
    col.metric(label, value, delta, help=help, delta_color=delta_color)


def plot(fig, key: str | None = None):
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "locale": "fr"}, key=key)


def download_df(df: pd.DataFrame, name: str, label: str = "Exporter (CSV)"):
    st.download_button(label, df.to_csv(index=True, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=f"{name}.csv", mime="text/csv", key=f"dl-{name}")
