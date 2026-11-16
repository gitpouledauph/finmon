"""Fee scanner: fund running costs (TER), broker costs, fee drag and cheaper equivalents.

TERs come from Yahoo Finance (netExpenseRatio) and can be overridden per line (table fee_overrides).
Cheaper equivalents are looked up in a small catalogue of index trackers; their TER is fetched live,
so the comparison stays current. PEA lines are only compared with PEA-eligible trackers.
"""
from __future__ import annotations

import pandas as pd

# index keyword (matched in the line name) -> candidate trackers (ticker, PEA eligible)
CATALOGUE = {
    "S&P 500": [("SXR8.DE", False), ("PSP5.PA", True)],
    "NASDAQ": [("XNAS.DE", False), ("CNDX.AS", False), ("EQQQ.DE", False), ("PUST.PA", True)],
    "MSCI WORLD": [("SWRD.AS", False), ("IWDA.AS", False), ("WPEA.PA", True), ("CW8.PA", True)],
    "EURO STOXX 50": [("C50.PA", True), ("CSX5.AS", False), ("EUN2.DE", False)],
    "STOXX EUROPE 600": [("MEUD.PA", True), ("EXSA.DE", False)],
}
ALIASES = {"MONDE": "MSCI WORLD", "PEA MONDE": "MSCI WORLD", "NASDAQ-100": "NASDAQ", "NASDAQ 100": "NASDAQ",
           "EUROPE 600": "STOXX EUROPE 600"}


def index_of(name: str) -> str | None:
    n = (name or "").upper()
    for k in CATALOGUE:
        if k in n:
            return k
    for a, k in ALIASES.items():
        if a in n:
            return k
    return None


def fetch_ter(tickers: list[str]) -> dict[str, dict]:
    """{ticker: {"ter": fraction or None, "name": str}} from Yahoo."""
    import yfinance as yf

    out = {}
    for t in tickers:
        try:
            i = yf.Ticker(t).info or {}
            ter = i.get("netExpenseRatio") or i.get("annualReportExpenseRatio")
            out[t] = {"ter": float(ter) / 100 if ter is not None else None,   # Yahoo reports percent
                      "name": i.get("longName") or i.get("shortName") or t, "type": i.get("quoteType")}
        except Exception:
            out[t] = {"ter": None, "name": t, "type": None}
    return out


def fee_drag(value: float, ter: float, years: int, gross_return: float = 0.06) -> float:
    """Money lost to running costs after `years`, versus the same investment without fees."""
    return value * ((1 + gross_return) ** years - (1 + gross_return - ter) ** years)


def scan(current: pd.DataFrame, account_types: dict, ters: dict, overrides: dict, gross_return: float = 0.06) -> pd.DataFrame:
    rows = []
    for r in current.itertuples():
        if not r.ticker or str(r.isin).startswith(("CRYPTO-", "MANUAL:")):
            continue
        info = ters.get(r.ticker, {})
        is_fund = info.get("type") in ("ETF", "MUTUALFUND") or r.isin in overrides
        if not is_fund:
            continue
        ter = overrides.get(r.isin, info.get("ter"))
        idx = index_of(r.name) or index_of(info.get("name", ""))
        pea = account_types.get(r.account_id) == "pea"
        best = None
        if idx and ter is not None:
            for t, eligible in CATALOGUE[idx]:
                if t == r.ticker or (pea and not eligible):
                    continue
                at = ters.get(t, {}).get("ter")
                if at is not None and at < ter - 1e-6 and (best is None or at < best[1]):
                    best = (t, at, ters[t]["name"])
        rows.append({
            "account_id": r.account_id, "isin": r.isin, "name": r.name, "ticker": r.ticker, "value": r.value,
            "ter": ter, "annual": r.value * ter if ter is not None else None,
            "drag10": fee_drag(r.value, ter, 10, gross_return) if ter is not None else None,
            "drag20": fee_drag(r.value, ter, 20, gross_return) if ter is not None else None,
            "index": idx, "alt_ticker": best[0] if best else None, "alt_name": best[2] if best else None,
            "alt_ter": best[1] if best else None,
            "saving": r.value * (ter - best[1]) if best else 0.0,
        })
    return pd.DataFrame(rows)


def candidate_tickers(current: pd.DataFrame) -> list[str]:
    out = set(t for t in current["ticker"].dropna() if not str(t).endswith("-USD"))
    for name in current["name"].dropna():
        idx = index_of(name)
        if idx:
            out.update(t for t, _ in CATALOGUE[idx])
    return sorted(out)
