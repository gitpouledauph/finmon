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
    # Les règles de classement du profil comptent aussi : les modifier recalcule le tableau de bord.
    for f in ("regles.yaml", "regles_auto.yaml"):
        p = db.path.parent / f
        if p.exists():
            mtime += p.stat().st_mtime
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


# ------------------------------------------------------------------ détails cliquables
GOOD_TXT, BAD_TXT = "#3ccf7a", "#f0625d"


def signed_style(df: pd.DataFrame, cols: list[str]):
    """Montants en vert (positif) ou rouge (négatif)."""
    def color(v):
        if v is None or v != v:
            return ""
        return f"color: {GOOD_TXT if v > 0 else BAD_TXT if v < 0 else 'inherit'}"
    return df.style.map(color, subset=[c for c in cols if c in df.columns])


def detail_button(col, key: str, label: str = "Voir le détail") -> bool:
    return col.button(label, key=key, type="tertiary", icon=":material/open_in_new:")


@st.dialog("Plus-values réalisées : ventes clôturées", width="large")
def closed_trades_dialog(closed: pd.DataFrame, names: dict) -> None:
    if closed.empty:
        st.write("Aucune vente.")
        return
    c = closed.sort_values("date", ascending=False)
    fees = c[c["fee_only"]]
    t = c[~c["fee_only"]]
    k1, k2, k3 = st.columns(3)
    k1.metric("Total réalisé", eur(c["realized"].sum(), sign=True))
    k2.metric("Ventes gagnantes", f"{(t['realized'] > 0).sum()} · {eur(t.loc[t['realized'] > 0, 'realized'].sum(), sign=True)}")
    k3.metric("Ventes perdantes", f"{(t['realized'] < 0).sum()} · {eur(t.loc[t['realized'] < 0, 'realized'].sum(), sign=True)}")
    df = pd.DataFrame({
        "Date": t["date"].dt.strftime("%d/%m/%Y"), "Titre": t["name"], "Compte": t["account_id"].map(names),
        "Type": t["type"], "Quantité": t["quantity"], "PRU": t["pru"], "Prix de revient": t["cost"],
        "Produit": t["proceeds"], "Plus-value": t["realized"],
        "Perf.": (t["realized"] / t["cost"] * 100).where(t["cost"] > 0)})
    st.dataframe(signed_style(df, ["Plus-value", "Perf."]).format({
        "Quantité": "{:.6g}", "PRU": "{:,.2f} €", "Prix de revient": "{:,.2f} €", "Produit": "{:,.2f} €",
        "Plus-value": "{:+,.2f} €", "Perf.": "{:+.1f} %"}, na_rep="—"), hide_index=True, width="stretch", height=480)
    if len(fees):
        st.caption(f"Non listés : {len(fees)} frais prélevés en crypto (quantité perdue sans produit), "
                   f"{eur(fees['realized'].sum(), sign=True)} au total.")


@st.dialog("Détail des opérations", width="large")
def operations_dialog(title: str, ops: pd.DataFrame, sign_note: str = "") -> None:
    st.markdown(f"**{title}**")
    if ops.empty:
        st.write("Aucune opération.")
        return
    o = ops.sort_values("amount")
    k1, k2 = st.columns(2)
    k1.metric("Total", eur(o["amount"].sum(), 2, sign=True))
    k2.metric("Opérations", len(o))
    if o["category"].nunique() > 1:
        by = o.groupby("category")["amount"].agg(["sum", "size"]).sort_values("sum")
        st.dataframe(signed_style(by.rename(columns={"sum": "Montant", "size": "Opérations"}).reset_index()
                                  .rename(columns={"category": "Catégorie"}), ["Montant"])
                     .format({"Montant": "{:+,.2f} €"}), hide_index=True, width="stretch")
    df = pd.DataFrame({"Date": o["date"].dt.strftime("%d/%m/%Y"), "Marchand": o["merchant"], "Libellé": o["label"],
                       "Catégorie": o["category"], "Montant": o["amount"]})
    st.dataframe(signed_style(df, ["Montant"]).format({"Montant": "{:+,.2f} €"}), hide_index=True,
                 width="stretch", height=420)
    if sign_note:
        st.caption(sign_note)
