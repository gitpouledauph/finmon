"""Cours, taux de change et métadonnées des titres (Yahoo Finance via yfinance).

Seuls des identifiants publics (ISIN, tickers, paires de devises) quittent la
machine — aucune donnée de compte.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

import pandas as pd

from . import config
from .db import DB

log = logging.getLogger(__name__)

EUR_SUFFIXES = (".DE", ".PA", ".AS", ".MI", ".F", ".MC", ".BR", ".VI", ".LS", ".IR")
STABLES = {"USDT", "USDC", "FDUSD", "BUSD", "DAI", "TUSD", "USDP"}
CORE_FX = ["USD", "GBP", "JPY", "CHF", "CAD", "AUD", "CNY", "INR", "TWD", "KRW", "HKD", "SEK", "DKK", "NOK"]

# --------------------------------------------------------------------------
# Profils types : exposition devise / région du sous-jacent, d'après le nom.
# Approximations (poids indicatifs d'indices larges) — corrigez dans
# config/instruments.yaml si besoin.
# --------------------------------------------------------------------------
PROFILES = [
    (("all country", "acwi", "all-world", "all world"), {
        "asset_class": "Actions",
        "exposure": {"USD": 0.65, "EUR": 0.07, "JPY": 0.05, "GBP": 0.03, "CNY": 0.03, "CHF": 0.02, "INR": 0.02, "TWD": 0.02, "CAD": 0.03, "AUTRE": 0.08},
        "regions": {"Amérique du Nord": 0.66, "Europe": 0.13, "Japon": 0.05, "Émergents": 0.11, "Asie-Pacifique": 0.05}}),
    (("emerging", "emergent", "em imi", "msci em"), {
        "asset_class": "Actions",
        "exposure": {"CNY": 0.26, "TWD": 0.19, "INR": 0.18, "KRW": 0.10, "AUTRE": 0.27},
        "regions": {"Émergents": 1.0}}),
    (("world", "monde", "developed"), {
        "asset_class": "Actions",
        "exposure": {"USD": 0.72, "EUR": 0.08, "JPY": 0.05, "GBP": 0.035, "CAD": 0.03, "CHF": 0.025, "AUD": 0.02, "AUTRE": 0.04},
        "regions": {"Amérique du Nord": 0.75, "Europe": 0.15, "Japon": 0.05, "Asie-Pacifique": 0.05}}),
    (("s&p 500", "s&p500", "sp 500", "sp500", "nasdaq", "usa", "u.s.", "us equity", "dow jones", "russell"), {
        "asset_class": "Actions", "exposure": {"USD": 1.0}, "regions": {"Amérique du Nord": 1.0}}),
    (("stoxx 600", "europe", "euro stoxx", "eurostoxx", "msci emu"), {
        "asset_class": "Actions", "exposure": {"EUR": 0.55, "GBP": 0.22, "CHF": 0.14, "AUTRE": 0.09},
        "regions": {"Europe": 1.0}}),
    (("cac 40", "cac40", "france", "sbf"), {
        "asset_class": "Actions", "exposure": {"EUR": 1.0}, "regions": {"Europe": 1.0}}),
    (("japan", "japon", "topix", "nikkei"), {
        "asset_class": "Actions", "exposure": {"JPY": 1.0}, "regions": {"Japon": 1.0}}),
    (("bitcoin", "ethereum", "crypto", "solana"), {
        "asset_class": "Crypto", "exposure": {"USD": 1.0}, "regions": {"Monde": 1.0}}),
    (("gold", "or physique", "silver", "commodit"), {
        "asset_class": "Matières premières", "exposure": {"USD": 1.0}, "regions": {"Monde": 1.0}}),
    (("overnight", "€str", "estr", "monetaire", "money market", "cash"), {
        "asset_class": "Monétaire", "exposure": {"EUR": 1.0}, "regions": {"Europe": 1.0}}),
    (("bond", "obligat", "treasury", "aggregate", "govt", "corp"), {
        "asset_class": "Obligations", "exposure": {"EUR": 1.0}, "regions": {"Monde": 1.0}}),
]

COUNTRY_REGION = {
    "United States": ("Amérique du Nord", "USD"), "Canada": ("Amérique du Nord", "CAD"),
    "France": ("Europe", "EUR"), "Germany": ("Europe", "EUR"), "Netherlands": ("Europe", "EUR"),
    "Italy": ("Europe", "EUR"), "Spain": ("Europe", "EUR"), "Ireland": ("Europe", "EUR"),
    "Belgium": ("Europe", "EUR"), "Finland": ("Europe", "EUR"), "Portugal": ("Europe", "EUR"),
    "Austria": ("Europe", "EUR"), "Luxembourg": ("Europe", "EUR"),
    "United Kingdom": ("Europe", "GBP"), "Switzerland": ("Europe", "CHF"), "Sweden": ("Europe", "SEK"),
    "Denmark": ("Europe", "DKK"), "Norway": ("Europe", "NOK"), "Japan": ("Japon", "JPY"),
    "China": ("Émergents", "CNY"), "Taiwan": ("Émergents", "TWD"), "India": ("Émergents", "INR"),
    "South Korea": ("Émergents", "KRW"), "Hong Kong": ("Asie-Pacifique", "HKD"), "Australia": ("Asie-Pacifique", "AUD"),
}

SECTOR_FR = {
    "technology": "Technologie", "realestate": "Immobilier", "real_estate": "Immobilier",
    "consumer_cyclical": "Conso. cyclique", "consumer cyclical": "Conso. cyclique",
    "consumer_defensive": "Conso. de base", "consumer defensive": "Conso. de base",
    "basic_materials": "Matériaux", "basic materials": "Matériaux",
    "communication_services": "Communication", "communication services": "Communication",
    "financial_services": "Finance", "financial services": "Finance",
    "healthcare": "Santé", "utilities": "Services publics", "industrials": "Industrie", "energy": "Énergie",
}


def profile_for(name: str) -> dict:
    n = (name or "").lower()
    for keys, prof in PROFILES:
        if any(k in n for k in keys):
            return json.loads(json.dumps(prof))
    return {}


# --------------------------------------------------------------------------
# Résolution des instruments
# --------------------------------------------------------------------------
def known_isins(db: DB) -> pd.DataFrame:
    return db.read(
        """SELECT isin, MAX(name) AS name FROM (
               SELECT isin, name FROM trades WHERE isin IS NOT NULL AND isin != ''
               UNION ALL SELECT isin, name FROM position_snapshots)
           GROUP BY isin"""
    )


def _search_ticker(isin: str) -> tuple[str | None, dict]:
    import yfinance as yf

    try:
        quotes = yf.Search(isin, max_results=10, news_count=0).quotes or []
    except Exception as e:  # réseau, quota...
        log.warning("Recherche %s impossible : %s", isin, e)
        return None, {}
    if not quotes:
        return None, {}
    quotes.sort(key=lambda q: (not str(q.get("symbol", "")).endswith(EUR_SUFFIXES),
                               str(q.get("symbol", "")).endswith(".F")))
    return quotes[0].get("symbol"), quotes[0]


def resolve_instrument(isin: str, name: str, online: bool = True) -> dict:
    conf = (config.instruments_config() or {}).get(isin, {}) or {}
    row = {"isin": isin, "name": conf.get("name") or name, "ticker": conf.get("ticker"),
           "currency": conf.get("currency"), "asset_class": conf.get("asset_class"),
           "region": None, "sector": conf.get("sector"),
           "exposure": conf.get("exposure"), "regions": conf.get("regions"), "sectors": conf.get("sectors"),
           "resolved_by": "config" if conf else None}
    quote: dict = {}
    # Identifiants internes : CRYPTO-BTC (Binance), TICKER:AAPL (saisie sans ISIN), IBKR:XYZ
    if isin.startswith("CRYPTO-"):
        coin = isin.split("-", 1)[1]
        row.update(ticker=row["ticker"] or f"{coin}-USD", currency=row["currency"] or "USD",
                   asset_class=row["asset_class"] or ("Monétaire" if coin in STABLES else "Crypto"),
                   name=row["name"] or coin, resolved_by=row["resolved_by"] or "crypto")
        row["exposure"] = row["exposure"] or {"USD": 1.0}
        row["regions"] = row["regions"] or {"Monde": 1.0}
        online_info = False
    else:
        online_info = online
    if isin.startswith(("TICKER:", "IBKR:")) and not row["ticker"]:
        row["ticker"] = isin.split(":", 1)[1]
        row["resolved_by"] = row["resolved_by"] or "ticker"
    if online and not row["ticker"]:
        row["ticker"], quote = _search_ticker(isin)
        row["resolved_by"] = row["resolved_by"] or ("yahoo" if row["ticker"] else None)

    prof = profile_for(f"{name} {quote.get('longname', '')} {quote.get('shortname', '')}")
    info = {}
    if online_info and row["ticker"]:
        import yfinance as yf

        t = yf.Ticker(row["ticker"])
        try:
            info = t.info or {}
        except Exception:
            info = {}
        row["currency"] = row["currency"] or info.get("currency")
        qtype = (info.get("quoteType") or quote.get("quoteType") or "").upper()
        if qtype == "EQUITY" and not prof:
            region, ccy = COUNTRY_REGION.get(info.get("country", ""), ("Autre", info.get("financialCurrency") or row["currency"]))
            prof = {"asset_class": "Actions", "exposure": {ccy or "EUR": 1.0}, "regions": {region: 1.0}}
            if info.get("sector"):
                row["sector"] = row["sector"] or SECTOR_FR.get(info["sector"].lower(), info["sector"])
        elif qtype == "CRYPTOCURRENCY":
            prof = {"asset_class": "Crypto", "exposure": {"USD": 1.0}, "regions": {"Monde": 1.0}}
        if qtype in ("ETF", "MUTUALFUND") and not row["sectors"]:
            try:
                sw = t.funds_data.sector_weightings or {}
                if sw:
                    row["sectors"] = {SECTOR_FR.get(k.lower(), k): float(v) for k, v in sw.items() if v}
            except Exception:
                pass
        if not row["name"]:
            row["name"] = info.get("longName") or info.get("shortName")

    row["asset_class"] = row["asset_class"] or prof.get("asset_class") or "Actions"
    row["exposure"] = row["exposure"] or prof.get("exposure") or {(row["currency"] or "EUR"): 1.0}
    row["regions"] = row["regions"] or prof.get("regions") or {"Autre": 1.0}
    if not row["sectors"] and row["sector"]:
        row["sectors"] = {row["sector"]: 1.0}
    row["region"] = max(row["regions"], key=row["regions"].get)
    row["currency"] = row["currency"] or "EUR"
    for k in ("exposure", "regions", "sectors"):
        row[k] = json.dumps(row[k] or {}, ensure_ascii=False)
    return row


def resolve_all(db: DB, online: bool = True, force: bool = False) -> list[str]:
    isins = known_isins(db)
    have = db.read("SELECT isin FROM instruments WHERE ticker IS NOT NULL OR resolved_by = 'manuel'")["isin"].tolist()
    manual = set(db.read("SELECT isin FROM instruments WHERE resolved_by = 'manuel'")["isin"])
    confs = set((config.instruments_config() or {}).keys())
    rows, logs = [], []
    for isin, name in isins.itertuples(index=False):
        if isin in manual or (not force and isin in have and isin not in confs):
            continue
        r = resolve_instrument(isin, name, online=online)
        rows.append(r)
        logs.append(f"{isin} → {r['ticker'] or '❓ ticker introuvable'} ({r['asset_class']})")
    if rows:
        db.upsert("instruments", pd.DataFrame(rows), mode="replace")
    return logs


# --------------------------------------------------------------------------
# Historique de cours et de change
# --------------------------------------------------------------------------
def _download(symbols: list[str], start: date) -> pd.DataFrame:
    import yfinance as yf

    if not symbols:
        return pd.DataFrame()
    data = yf.download(symbols, start=start.isoformat(), progress=False, auto_adjust=False, threads=True,
                       group_by="column")
    if data is None or data.empty:
        return pd.DataFrame()
    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(symbols[0])
    long = close.reset_index().melt(id_vars=close.index.name or "Date", var_name="symbol", value_name="close")
    long = long.rename(columns={close.index.name or "Date": "date"}).dropna()
    long["date"] = pd.to_datetime(long["date"]).dt.strftime("%Y-%m-%d")
    return long[["symbol", "date", "close"]]


def _start_for(db: DB, table: str, key: str, keys: list[str], first: date) -> dict[str, date]:
    if not keys:
        return {}
    q = f"SELECT {key} AS k, MAX(date) AS d FROM {table} WHERE {key} IN ({','.join('?' * len(keys))}) GROUP BY {key}"
    last = dict(db.read(q, keys).itertuples(index=False))
    return {k: (date.fromisoformat(last[k]) - timedelta(days=5)) if k in last else first for k in keys}


def first_date(db: DB) -> date:
    d = db.read("SELECT MIN(date) AS d FROM (SELECT date FROM trades UNION ALL SELECT date FROM cash_transactions)")["d"][0]
    return date.fromisoformat(d) - timedelta(days=7) if d else date.today() - timedelta(days=365)


def update_prices(db: DB) -> list[str]:
    tickers = db.read("SELECT DISTINCT ticker FROM instruments WHERE ticker IS NOT NULL")["ticker"].tolist()
    bench = config.settings()["benchmark"]["ticker"]
    tickers = sorted(set(tickers + [bench]))
    starts = _start_for(db, "prices", "symbol", tickers, first_date(db))
    n = 0
    for start in sorted(set(starts.values())):
        group = [t for t, s in starts.items() if s == start]
        try:
            df = _download(group, start)
        except Exception as e:
            return [f"❌ Cours : {e}"]
        n += db.upsert("prices", df, mode="replace")
    return [f"Cours mis à jour : {len(tickers)} tickers, {n} lignes"]


def needed_currencies(db: DB) -> list[str]:
    inst = db.read("SELECT currency, exposure FROM instruments")
    ccys = set(CORE_FX[:5])
    for c, e in inst.itertuples(index=False):
        if c:
            ccys.add(c.upper())
        for k in json.loads(e or "{}"):
            ccys.add(k.upper())
    ccys.update(db.read("SELECT DISTINCT foreign_currency AS c FROM cash_transactions WHERE foreign_currency IS NOT NULL")["c"])
    return sorted(c for c in ccys if c and c not in ("EUR", "AUTRE", "GBX", "GBP_P"))


def update_fx(db: DB) -> list[str]:
    ccys = needed_currencies(db)
    starts = _start_for(db, "fx_rates", "currency", ccys, first_date(db))
    n = 0
    for start in sorted(set(starts.values())):
        group = [c for c, s in starts.items() if s == start]
        try:
            df = _download([f"EUR{c}=X" for c in group], start)
        except Exception as e:
            return [f"❌ Change : {e}"]
        if df.empty:
            continue
        df["currency"] = df["symbol"].str[3:6]
        n += db.upsert("fx_rates", df.rename(columns={"close": "rate"})[["currency", "date", "rate"]], mode="replace")
    return [f"Taux de change mis à jour : {len(ccys)} devises, {n} lignes"]


def update_all(db: DB) -> list[str]:
    logs = resolve_all(db)
    logs += update_fx(db)
    logs += update_prices(db)
    return logs


# --------------------------------------------------------------------------
# Valeurs ponctuelles (imports, saisie manuelle) et cours en direct
# --------------------------------------------------------------------------
def _series(db: DB, table: str, key_col: str, key: str, val: str) -> pd.Series:
    df = db.read(f"SELECT date, {val} AS v FROM {table} WHERE {key_col} = ? ORDER BY date", [key])
    if df.empty:
        return pd.Series(dtype=float)
    return df.assign(date=pd.to_datetime(df["date"])).set_index("date")["v"]


def ensure_history(db: DB, symbols: list[str], start: date, online: bool = True, fx: bool = False) -> None:
    """Télécharge l'historique manquant (cours, ou change si fx=True) depuis start."""
    if not online or not symbols:
        return
    table, col = ("fx_rates", "currency") if fx else ("prices", "symbol")
    missing = []
    for s in set(symbols):
        first = db.read(f"SELECT MIN(date) AS d, MAX(date) AS m FROM {table} WHERE {col} = ?", [s])
        d, m = first["d"][0], first["m"][0]
        if d is None or date.fromisoformat(d) > start + timedelta(days=4) or date.fromisoformat(m) < date.today() - timedelta(days=4):
            missing.append(s)
    if not missing:
        return
    try:
        df = _download([f"EUR{c}=X" for c in missing] if fx else missing, start - timedelta(days=7))
    except Exception as e:
        log.warning("Téléchargement impossible : %s", e)
        return
    if df.empty:
        return
    if fx:
        df["currency"] = df["symbol"].str[3:6]
        db.upsert("fx_rates", df.rename(columns={"close": "rate"})[["currency", "date", "rate"]], mode="replace")
    else:
        db.upsert("prices", df, mode="replace")


def fx_on(db: DB, ccy: str, d, online: bool = True) -> float | None:
    """Unités de devise pour 1 EUR à la date d (dernier connu)."""
    ccy = (ccy or "EUR").upper()
    if ccy == "EUR":
        return 1.0
    d = pd.Timestamp(d)
    s = _series(db, "fx_rates", "currency", ccy, "rate")
    if (s.empty or s.index[0] > d + pd.Timedelta(days=4) or s.index[-1] < d - pd.Timedelta(days=4)) and online:
        ensure_history(db, [ccy], min(d.date(), date.today()), online, fx=True)
        s = _series(db, "fx_rates", "currency", ccy, "rate")
    if s.empty:
        return None
    v = s.asof(d)
    return float(v) if v == v else float(s.iloc[0])


def price_on(db: DB, ticker: str, d, online: bool = True) -> float | None:
    """Cours de clôture du ticker (dans sa devise) à la date d."""
    d = pd.Timestamp(d)
    s = _series(db, "prices", "symbol", ticker, "close")
    if (s.empty or s.index[0] > d + pd.Timedelta(days=4)) and online:
        ensure_history(db, [ticker], min(d.date(), date.today()), online)
        s = _series(db, "prices", "symbol", ticker, "close")
    if s.empty:
        return None
    v = s.asof(d)
    return float(v) if v == v else float(s.iloc[0])


def eur_value(db: DB, ticker: str, ccy: str, qty: float, d, online: bool = True) -> float | None:
    p = price_on(db, ticker, d, online)
    r = fx_on(db, ccy, d, online)
    if p is None or r is None:
        return None
    if ccy in ("GBp", "GBX"):
        p, r = p / 100, fx_on(db, "GBP", d, online)
    return qty * p / r


def lookup(ticker: str) -> dict:
    """Infos d'un ticker Yahoo pour le formulaire de saisie."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    out = {"ticker": ticker}
    try:
        fi = t.fast_info
        out["last"] = float(fi.last_price)
        out["currency"] = fi.currency
    except Exception:
        return {}
    try:
        info = t.info or {}
        out["name"] = info.get("longName") or info.get("shortName") or ticker
        out["isin"] = getattr(t, "isin", None) if hasattr(t, "isin") else None
        out["quoteType"] = info.get("quoteType")
    except Exception:
        out["name"] = ticker
    if out.get("isin") in ("-", ""):
        out["isin"] = None
    return out


def held_tickers(db: DB) -> list[str]:
    q = """SELECT DISTINCT i.ticker FROM instruments i
           JOIN (SELECT isin FROM trades GROUP BY isin, account_id
                 HAVING SUM(CASE WHEN kind IN ('buy','transfer_in','reward') THEN quantity
                                 WHEN kind IN ('sell','transfer_out') THEN -quantity ELSE 0 END) > 1e-9
                 UNION SELECT isin FROM position_snapshots) h ON h.isin = i.isin
           WHERE i.ticker IS NOT NULL"""
    return db.read(q)["ticker"].tolist()


def live_update(db: DB) -> tuple[int, str]:
    """Écrit le dernier cours (temps réel / différé 15 min selon la place) à la date du jour."""
    import yfinance as yf

    tickers = sorted(set(held_tickers(db) + [config.settings()["benchmark"]["ticker"]]))
    fx_syms = [f"EUR{c}=X" for c in needed_currencies(db)]
    rows, fx_rows = [], []
    today = date.today().isoformat()
    if tickers or fx_syms:
        tk = yf.Tickers(" ".join(tickers + fx_syms))
        for sym in tickers + fx_syms:
            try:
                v = float(tk.tickers[sym].fast_info.last_price)
            except Exception:
                continue
            if v != v or v <= 0:
                continue
            if sym in fx_syms:
                fx_rows.append({"currency": sym[3:6], "date": today, "rate": v})
            else:
                rows.append({"symbol": sym, "date": today, "close": v})
    n = db.upsert("prices", pd.DataFrame(rows), mode="replace") + db.upsert("fx_rates", pd.DataFrame(fx_rows), mode="replace")
    from datetime import datetime

    return n, datetime.now().strftime("%H:%M:%S")
