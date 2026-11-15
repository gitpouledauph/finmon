"""Import des relevés d'activité Interactive Brokers (Activity Statement, format CSV).

Le CSV IBKR empile des sections : chaque ligne commence par le nom de section
puis « Header » / « Data » / « Total »... On lit :

* Trades                          -> achats / ventes (actions, ETF ; le Forex est ignoré)
* Deposits & Withdrawals          -> versements / retraits
* Dividends, Withholding Tax      -> dividendes (nets de retenue)
* Interest, Fees                  -> intérêts, frais
* Financial Instrument Information-> ISIN de chaque symbole
* Open Positions                  -> photo des quantités en fin de relevé (rapprochement)

Les montants en devise sont convertis en EUR au taux du jour de l'opération.
"""
from __future__ import annotations

import csv
import io
import re

import pandas as pd

from .. import market
from ..db import DB
from ..parsing import read_text, stable_ids, to_number

ACCOUNT_ID = "ibkr"


def detect_text(text: str) -> bool:
    head = text[:4000]
    return head.startswith(("Statement,Header", "﻿Statement,Header")) or "Trades,Header,DataDiscriminator" in head


def parse_sections(text: str) -> dict[str, pd.DataFrame]:
    sections: dict[str, list[dict]] = {}
    headers: dict[str, list[str]] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        sec, typ = row[0].strip().lstrip("﻿"), row[1].strip()
        if typ == "Header":
            headers[sec] = [c.strip() for c in row[2:]]
        elif typ == "Data" and sec in headers:
            vals = row[2:] + [""] * (len(headers[sec]) - len(row[2:]))
            sections.setdefault(sec, []).append(dict(zip(headers[sec], vals)))
    return {k: pd.DataFrame(v) for k, v in sections.items()}


def _date(s: str):
    s = str(s).split(",")[0].strip().split(";")[0]
    return pd.to_datetime(s, errors="coerce")


def import_file(db: DB, path, online: bool = True) -> tuple[str, int]:
    text = read_text(path)
    name = getattr(path, "name", str(path))
    n, warnings = import_statement(db, text, source=name, online=online)
    db.log("ibkr", name, n, "ok", "")
    for w in warnings:
        db.log("ibkr", name, 0, "warning", w)
    return "ibkr", n


def import_statement(db: DB, text: str, source: str = "", online: bool = True) -> tuple[int, list[str]]:
    secs = parse_sections(text)
    warnings: list[str] = []
    db.upsert("accounts", pd.DataFrame([{"id": ACCOUNT_ID, "institution": "Interactive Brokers",
                                         "name": "Interactive Brokers", "type": "cto", "currency": "EUR"}]),
              mode="ignore")

    isin_of: dict[str, str] = {}
    fii = secs.get("Financial Instrument Information")
    if fii is not None and not fii.empty:
        for r in fii.to_dict("records"):
            sid = (r.get("Security ID") or "").strip()
            if r.get("Symbol"):
                isin_of[r["Symbol"].strip()] = sid if re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", sid) else f"IBKR:{r['Symbol'].strip()}"

    rows: list[dict] = []
    all_dates = []

    def eur(amount: float, ccy: str, d) -> float | None:
        r = market.fx_on(db, ccy, d, online)
        return None if r is None else amount / r

    # ---------------- trades ----------------
    t = secs.get("Trades")
    if t is not None and not t.empty:
        t = t[(t.get("DataDiscriminator", "Order").isin(["Order", "Trade", ""]))]
        for r in t.to_dict("records"):
            cat = (r.get("Asset Category") or "").lower()
            if "forex" in cat:
                continue
            if not any(k in cat for k in ("stock", "fund", "etf", "bond", "crypto")):
                warnings.append(f"Ignoré (catégorie {r.get('Asset Category')}) : {r.get('Symbol')}")
                continue
            d = _date(r.get("Date/Time", ""))
            qty = to_number(r.get("Quantity"))
            proceeds = to_number(r.get("Proceeds")) or 0.0
            fee = to_number(r.get("Comm/Fee")) or 0.0
            ccy = (r.get("Currency") or "EUR").strip()
            if pd.isna(d) or not qty:
                continue
            all_dates.append(d)
            sym = (r.get("Symbol") or "").strip()
            amt = eur(proceeds + fee, ccy, d)
            rows.append({"date": d, "kind": "buy" if qty > 0 else "sell", "isin": isin_of.get(sym, f"IBKR:{sym}"),
                         "name": sym, "quantity": abs(qty), "amount": amt,
                         "fees": abs(eur(fee, ccy, d) or 0.0), "ccy": ccy, "symbol": sym})

    # ---------------- cash ----------------
    def cash_section(name, kind, sign_kind=None):
        df = secs.get(name)
        if df is None or df.empty:
            return
        dcol = "Settle Date" if "Settle Date" in df.columns else "Date"
        for r in df.to_dict("records"):
            ccy = (r.get("Currency") or "").strip()
            if not ccy or ccy.lower().startswith("total"):
                continue
            d = _date(r.get(dcol, ""))
            a = to_number(r.get("Amount"))
            if pd.isna(d) or not a:
                continue
            all_dates.append(d)
            k = kind if sign_kind is None else (sign_kind[0] if a > 0 else sign_kind[1])
            desc = r.get("Description", "")
            m = re.match(r"^([A-Z0-9.\-]+)\s*\(([A-Z]{2}[A-Z0-9]{9}\d)\)", desc or "")
            rows.append({"date": d, "kind": k, "isin": m.group(2) if m else None, "name": (desc or name)[:80],
                         "quantity": None, "amount": eur(a, ccy, d), "fees": 0.0, "ccy": ccy, "symbol": None})

    cash_section("Deposits & Withdrawals", None, ("deposit", "withdrawal"))
    cash_section("Dividends", "dividend")
    cash_section("Payment In Lieu Of Dividends", "dividend")
    cash_section("Withholding Tax", "tax")
    cash_section("Interest", "interest")
    cash_section("Fees", "fee")

    # ---------------- positions de fin de relevé ----------------
    op = secs.get("Open Positions")
    period_end = None
    st = secs.get("Statement")
    if st is not None and "Field Name" in st.columns:
        per = st.loc[st["Field Name"] == "Period", "Field Value"]
        if not per.empty:
            period_end = pd.to_datetime(per.iloc[0].split("-")[-1].strip(), errors="coerce")
    if op is not None and not op.empty and period_end is not None and not pd.isna(period_end):
        op = op[op.get("DataDiscriminator", "Summary").isin(["Summary", ""])]
        snaps = []
        for r in op.to_dict("records"):
            if "forex" in (r.get("Asset Category") or "").lower():
                continue
            sym = (r.get("Symbol") or "").strip()
            q = to_number(r.get("Quantity"))
            if sym and q:
                snaps.append({"account_id": ACCOUNT_ID, "date": period_end.strftime("%Y-%m-%d"),
                              "isin": isin_of.get(sym, f"IBKR:{sym}"), "name": sym, "quantity": q,
                              "price": None, "avg_cost": None, "value": None})
        db.upsert("position_snapshots", pd.DataFrame(snaps), mode="replace")

    if not rows:
        return 0, warnings + ["Aucune opération trouvée — est-ce bien un « Activity Statement » au format CSV ?"]
    out = pd.DataFrame(rows)
    if out["amount"].isna().any():
        warnings.append("Taux de change introuvable pour certaines opérations (hors ligne ?) : relancez l'import connecté.")
    # Instruments : ticker IBKR comme point de départ (devise du titre connue).
    inst = out.dropna(subset=["symbol"]).drop_duplicates("isin")
    if not inst.empty:
        known = set(db.read("SELECT isin FROM instruments")["isin"])
        new = []
        for r in inst.itertuples():
            if r.isin not in known:
                row = market.resolve_instrument(r.isin, r.symbol, online=online)
                if not row.get("ticker") or r.isin.startswith("IBKR:"):
                    row["ticker"] = row.get("ticker") or r.symbol
                new.append(row)
        if new:
            db.upsert("instruments", pd.DataFrame(new), mode="replace")
    out["account_id"] = ACCOUNT_ID
    out["taxes"] = 0.0
    out["source"] = source
    out["d"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["id"] = stable_ids(out.assign(ts=out["date"].astype(str), q=out["quantity"].round(8), a=out["amount"].round(2)),
                           ["ts", "kind", "isin", "q", "name"], "ibkr")
    n = db.upsert("trades", out[["id", "account_id", "d", "kind", "isin", "name", "quantity", "amount", "fees",
                                 "taxes", "source"]].rename(columns={"d": "date"}))
    return n, warnings
