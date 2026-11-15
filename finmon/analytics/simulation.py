"""Projections à partir des rendements historiques (jusqu'à 10 ans) de chaque ligne.

Méthode, volontairement simple et transparente :
- rendement annuel moyen = taux de croissance annualisé (CAGR) du cours en euros sur l'historique
  disponible, plafonné à 10 ans ;
- volatilité = écart-type annualisé des rendements mensuels ;
- projection centrale : valeur × (1 + r)^n, plus les versements mensuels éventuels ;
- fourchette : quantiles 10 % / 90 % d'un modèle log-normal de même moyenne et volatilité.
Ce sont des extrapolations du passé, pas des prévisions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

Z90 = 1.2816  # quantile 90 % d'une loi normale


@dataclass
class Stats:
    ticker: str
    years: float          # historique réellement utilisé
    cagr: float | None    # rendement annuel moyen (en EUR)
    vol: float | None     # volatilité annualisée


def monthly_history(tickers: list[str], currencies: dict[str, str], years: int = 10) -> pd.DataFrame:
    """Cours mensuels en EUR (colonnes = tickers), via Yahoo Finance."""
    import yfinance as yf

    if not tickers:
        return pd.DataFrame()
    raw = yf.download(tickers, period=f"{years}y", interval="1mo", auto_adjust=True, progress=False,
                      group_by="column", threads=True)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": tickers[0]})
    close = close.dropna(how="all")
    fx_needed = sorted({c for t, c in currencies.items() if t in close.columns and c and c not in ("EUR",)})
    pairs = {c: f"EUR{'GBP' if c in ('GBp', 'GBX') else c}=X" for c in fx_needed}
    if pairs:
        fx = yf.download(list(pairs.values()), period=f"{years}y", interval="1mo", progress=False)["Close"]
        if isinstance(fx, pd.Series):
            fx = fx.to_frame(list(pairs.values())[0])
        fx = fx.reindex(close.index).ffill().bfill()
        for t in close.columns:
            c = currencies.get(t)
            if c in pairs and pairs[c] in fx.columns:
                div = fx[pairs[c]] * (100 if c in ("GBp", "GBX") else 1)
                close[t] = close[t] / div
    return close


def stats_from_history(close: pd.DataFrame, max_years: int = 10) -> dict[str, Stats]:
    out = {}
    for t in close.columns:
        s = close[t].dropna()
        s = s[s > 0]
        if len(s) < 13:
            out[t] = Stats(t, len(s) / 12, None, None)
            continue
        s = s[s.index >= s.index[-1] - pd.DateOffset(years=max_years)]
        yrs = (s.index[-1] - s.index[0]).days / 365.25
        cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else None
        vol = float(np.log(s).diff().dropna().std() * math.sqrt(12))
        out[t] = Stats(t, yrs, float(cagr) if cagr is not None else None, vol)
    return out


def project(value: float, r: float, vol: float | None, years: int, monthly: float = 0.0) -> dict:
    """Valeur projetée (centrale, basse, haute) après `years` ans, avec versements mensuels."""
    if r is None:
        return {"central": None, "low": None, "high": None, "invested": value + monthly * 12 * years}
    n = years * 12
    rm = (1 + r) ** (1 / 12) - 1
    central = value * (1 + r) ** years + (monthly * (((1 + rm) ** n - 1) / rm) if rm else monthly * n)
    if vol:
        mu = math.log(1 + r) - vol ** 2 / 2          # moyenne log telle que E[croissance] = (1+r)
        spread = vol * math.sqrt(years)
        g = math.exp(mu * years)
        low_f, high_f = g * math.exp(-Z90 * spread), g * math.exp(Z90 * spread)
        # Versements : même facteur appliqué à mi-parcours (approximation lisible).
        contrib = monthly * n
        mid = years / 2
        cl = contrib * math.exp(mu * mid - Z90 * vol * math.sqrt(mid))
        ch = contrib * math.exp(mu * mid + Z90 * vol * math.sqrt(mid))
        low, high = value * low_f + cl, value * high_f + ch
    else:
        low = high = central
    return {"central": central, "low": low, "high": high, "invested": value + monthly * n}


def path(value: float, r: float, vol: float | None, years: int, monthly: float = 0.0) -> pd.DataFrame:
    rows = [{"année": y, **project(value, r, vol, y, monthly)} for y in range(0, years + 1)]
    return pd.DataFrame(rows).set_index("année")
