"""Wealth projection by asset class, financial independence and savings goals."""
from __future__ import annotations

import math

import pandas as pd

DEFAULT_RETURNS = {  # nominal annual expected returns — editable in the UI
    "Equities": 0.07, "Bonds": 0.03, "Money market": 0.025, "Cash": 0.0, "Regulated savings": 0.017,
    "Employee savings": 0.05, "Crypto": 0.08, "Commodities": 0.03, "Real estate": 0.04, "Multi-asset": 0.045,
    "Other": 0.02,
}


def project(start: dict[str, float], returns: dict[str, float], monthly: float, split: dict[str, float],
            years: int, inflation: float = 0.0, monthly_growth: float = 0.0) -> pd.DataFrame:
    """Monthly simulation, reported yearly. `split` = share of each new monthly saving per class.
    `monthly_growth` = yearly increase of the monthly saving (e.g. 0.02 for +2 %/yr)."""
    bal = {k: float(v) for k, v in start.items()}
    for k in split:
        bal.setdefault(k, 0.0)
    tot_split = sum(split.values()) or 1.0
    contributed = 0.0
    rows = [{"year": 0, "total": sum(bal.values()), "contributed": 0.0, **bal}]
    m = monthly
    for month in range(1, years * 12 + 1):
        for k in bal:
            r = returns.get(k, 0.0)
            bal[k] *= (1 + r) ** (1 / 12)
            bal[k] += m * split.get(k, 0.0) / tot_split
        contributed += m
        if month % 12 == 0:
            m *= 1 + monthly_growth
            y = month // 12
            rows.append({"year": y, "total": sum(bal.values()), "contributed": contributed, **bal})
    df = pd.DataFrame(rows).set_index("year")
    df["start"] = rows[0]["total"]
    df["growth"] = df["total"] - df["start"] - df["contributed"]
    df["real"] = df["total"] / (1 + inflation) ** df.index
    return df


def years_to_target(df: pd.DataFrame, target: float, col: str = "real") -> float | None:
    hit = df[df[col] >= target]
    return float(hit.index[0]) if not hit.empty else None


def required_monthly(current: float, target: float, months: int, annual_return: float) -> float:
    """Monthly saving needed to grow `current` to `target` in `months` at `annual_return`."""
    if months <= 0:
        return max(0.0, target - current)
    rm = (1 + annual_return) ** (1 / 12) - 1
    fv_current = current * (1 + rm) ** months
    gap = target - fv_current
    if gap <= 0:
        return 0.0
    return gap * rm / ((1 + rm) ** months - 1) if rm else gap / months
