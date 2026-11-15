"""Classement des opérations bancaires, budget mensuel/annuel, vacances."""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np
import pandas as pd

from .. import config
from ..parsing import norm


@lru_cache(maxsize=None)
def _compiled_rules() -> list[tuple[re.Pattern, str]]:
    rules = config.categories().get("rules") or []
    return [(re.compile(r["pattern"], re.I), r["category"]) for r in rules]


def category_types() -> dict[str, str]:
    cats = config.categories().get("categories") or {}
    return {k: (v or {}).get("type", "expense") for k, v in cats.items()}


def _from_bank(parent: str | None, cat: str | None) -> str | None:
    mapping = config.categories().get("bank_mapping") or {}
    text = norm(f"{cat or ''} {parent or ''}")
    # les mots-clés les plus longs d'abord (« frais bancaires » avant « frais »)
    for key in sorted(mapping, key=len, reverse=True):
        if norm(key) and norm(key) in text:
            return mapping[key]
    return None


SAVINGS_TYPES = {"livret", "pea", "cto", "assurance_vie"}
INTEREST_RE = re.compile(r"INTERETS|INTERESTS?|REMUNERATION", re.I)


def classify(tx: pd.DataFrame, overrides: pd.DataFrame | None = None,
             account_types: dict[str, str] | None = None) -> pd.DataFrame:
    """Ajoute category, cat_type, source_cat (override | règle | banque | défaut | compte).

    Sur un livret, tout est mouvement interne sauf les intérêts : le budget
    se lit sur les comptes courants (et la carte Trade Republic).
    """
    df = tx.copy()
    account_types = account_types or {}
    if df.empty:
        for c in ("category", "cat_type", "source_cat", "vacation_tag"):
            df[c] = pd.Series(dtype="object")
        return df
    rules = _compiled_rules()
    cats, srcs = [], []
    for acc, label, merchant, parent, cat, amount in zip(
        df["account_id"], df["label"], df["merchant"].fillna(""), df["bank_category_parent"], df["bank_category"], df["amount"]
    ):
        text = f"{label} {merchant}"
        if account_types.get(acc) == "livret":
            cats.append("Autres revenus" if INTEREST_RE.search(text) and amount > 0 else "Virements internes")
            srcs.append("compte")
            continue
        found = next((c for p, c in rules if p.search(text)), None)
        if found:
            cats.append(found)
            srcs.append("règle")
            continue
        found = _from_bank(parent, cat)
        if found:
            cats.append(found)
            srcs.append("banque")
            continue
        cats.append("Autres revenus" if amount > 0 else "À classer")
        srcs.append("défaut")
    df["category"] = cats
    df["source_cat"] = srcs
    df["vacation_tag"] = None
    if overrides is not None and not overrides.empty:
        ov = overrides.set_index("tx_id")
        m = df["id"].isin(ov.index)
        ocat = df.loc[m, "id"].map(ov["category"])
        has = ocat.notna() & (ocat != "")
        df.loc[ocat[has].index, "category"] = ocat[has]
        df.loc[ocat[has].index, "source_cat"] = "manuel"
        df.loc[m, "vacation_tag"] = df.loc[m, "id"].map(ov["vacation"])
    types = category_types()
    df["cat_type"] = df["category"].map(types).fillna("expense")
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["year"] = df["date"].dt.year
    return df


def expenses(df: pd.DataFrame) -> pd.DataFrame:
    """Dépenses positives (remboursements déduits)."""
    e = df[df["cat_type"] == "expense"].copy()
    e["spend"] = -e["amount"]
    return e


def monthly_by_category(df: pd.DataFrame) -> pd.DataFrame:
    e = expenses(df)
    return e.pivot_table(index="month", columns="category", values="spend", aggfunc="sum", fill_value=0.0).sort_index()


def monthly_flows(df: pd.DataFrame) -> pd.DataFrame:
    """Revenus, dépenses, épargne et taux d'épargne par mois."""
    if df.empty:
        return pd.DataFrame(columns=["income", "expenses", "savings", "rate"])
    inc = df[df["cat_type"] == "income"].groupby("month")["amount"].sum()
    exp = expenses(df).groupby("month")["spend"].sum()
    out = pd.DataFrame({"income": inc, "expenses": exp}).fillna(0.0).sort_index()
    out["savings"] = out["income"] - out["expenses"]
    out["rate"] = np.where(out["income"] > 0, out["savings"] / out["income"], np.nan)
    return out


# --------------------------------------------------------------------------
# Vacances
# --------------------------------------------------------------------------
def vacation_spend(df: pd.DataFrame, vacations: pd.DataFrame) -> pd.DataFrame:
    """Rattache les dépenses aux périodes de vacances.

    Une dépense compte pour un voyage si elle est taguée manuellement, ou si elle
    tombe dans la période (hors catégories fixes : loyer, abonnements...).
    """
    e = expenses(df)
    e["vacation"] = e["vacation_tag"].where(e["vacation_tag"].notna() & (e["vacation_tag"] != ""))
    excluded = set(config.settings().get("vacation_excluded_categories") or [])
    for v in vacations.itertuples():
        start, end = pd.Timestamp(v.start), pd.Timestamp(v.end)
        m = e["vacation"].isna() & e["date"].between(start, end) & ~e["category"].isin(excluded)
        e.loc[m, "vacation"] = v.name
    return e[e["vacation"].notna()]


def suggest_vacations(df: pd.DataFrame, known: pd.DataFrame, gap_days: int = 3, min_ops: int = 3) -> pd.DataFrame:
    """Repère des séjours probables : paiements en devise étrangère ou
    dépenses « Voyages » rapprochées dans le temps."""
    e = expenses(df)
    signal = e[e["foreign_currency"].notna() | e["label"].str.contains(r"HORS ZONE EURO|1 EURO =", case=False, regex=True)]
    signal = signal.sort_values("date")
    if signal.empty:
        return pd.DataFrame(columns=["name", "start", "end", "ops", "total", "devises"])
    grp = (signal["date"].diff().dt.days.fillna(999) > gap_days).cumsum()
    rows = []
    for _, g in signal.groupby(grp):
        if len(g) < min_ops:
            continue
        start, end = g["date"].min(), g["date"].max()
        overlap = any(pd.Timestamp(v.start) <= end and pd.Timestamp(v.end) >= start for v in known.itertuples())
        if overlap:
            continue
        ccys = ", ".join(sorted(set(g["foreign_currency"].dropna()))) or "?"
        rows.append({"name": f"Séjour {start:%b %Y} ({ccys})", "start": start.date(), "end": end.date(),
                     "ops": len(g), "total": float(g["spend"].sum()), "devises": ccys})
    return pd.DataFrame(rows)
