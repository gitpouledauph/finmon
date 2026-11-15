"""Import des relevés d'activité Interactive Brokers (Activity Statement, CSV), en anglais ou en français.

Le CSV IBKR empile des sections : chaque ligne commence par le nom de section puis
« Header » / « Data ». Les noms de sections et de colonnes dépendent de la langue du
portail ; on les reconnaît par mots-clés :

| Contenu                     | Anglais                            | Français                                   |
|-----------------------------|------------------------------------|--------------------------------------------|
| achats / ventes             | Trades                             | Transactions                               |
| versements / retraits       | Deposits & Withdrawals             | Dépôts et retraits                         |
| dividendes                  | Dividends                          | Dividendes                                 |
| retenue à la source         | Withholding Tax                    | Retenue à la source / Impôt retenu…        |
| intérêts, frais             | Interest, Fees                     | Intérêts, Frais                            |
| ISIN des titres             | Financial Instrument Information   | Informations sur l'instrument financier    |
| positions de fin de période | Open Positions                     | Positions ouvertes                         |

Les montants en devise sont convertis en EUR au taux du jour de l'opération. Les opérations
de change (EUR.USD…) sont ignorées : seule compte la valeur en euros.
"""
from __future__ import annotations

import csv
import io
import re

import pandas as pd

from .. import market
from ..db import DB
from ..parsing import norm, read_text, stable_ids, to_number

ACCOUNT_ID = "ibkr"
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")

MONTHS_FR = {"janvier": "January", "fevrier": "February", "février": "February", "mars": "March",
             "avril": "April", "mai": "May", "juin": "June", "juillet": "July", "aout": "August",
             "août": "August", "septembre": "September", "octobre": "October", "novembre": "November",
             "decembre": "December", "décembre": "December"}


# --------------------------------------------------------------------------
# Reconnaissance des sections et colonnes (multilingue)
# --------------------------------------------------------------------------
def section_kind(name: str) -> str | None:
    n = norm(name)
    if n in ("statement", "releve"):
        return "statement"
    if n in ("trades", "transactions", "operations", "negociations", "executions"):
        return "trades"
    if ("deposit" in n and "withdraw" in n) or ("depot" in n and "retrait" in n):
        return "cash"
    if "withholding" in n or "retenue" in n or "impotretenu" in n:
        return "withholding"
    if "paymentinlieu" in n or "paiementtenantlieu" in n or "paiementenlieu" in n:
        return "dividends"
    if n.startswith(("dividend", "dividende")) and "accru" not in n and "courus" not in n:
        return "dividends"
    if n.startswith(("interest", "interet")) and "accru" not in n and "courus" not in n:
        return "interest"
    if n in ("fees", "frais", "autresfrais", "otherfees"):
        return "fees"
    if n in ("openpositions", "positionsouvertes"):
        return "positions"
    if "instrument" in n and ("information" in n or "financ" in n):
        return "instruments"
    return None


COLS = {
    "currency": ("currency", "devise"),
    "date": ("settledate", "datedereglement", "date"),
    "datetime": ("datetime", "dateheure", "date"),
    "description": ("description", "libelle"),
    "amount": ("amount", "montant"),
    "symbol": ("symbol", "symbole"),
    "quantity": ("quantity", "quantite"),
    "proceeds": ("proceeds", "produit", "produits", "recettes", "montantbrut"),
    "fee": ("commfee", "commtarif", "commfrais", "commissionfrais", "commission", "frais"),
    "category": ("assetcategory", "categoriedactifs", "categoriedactif", "classedactif", "classedactifs"),
    "discriminator": ("datadiscriminator", "discriminateurdedonnees", "discriminateur"),
    "security_id": ("securityid", "iddutitre", "identifiantdutitre", "identifiantdetitre", "idtitre",
                    "identifiantdesecurite", "isin"),
    "field": ("fieldname", "nomchamp", "nomduchamp"),
    "value": ("fieldvalue", "valeurchamp", "valeurduchamp"),
}


def _get(rec: dict, key: str) -> str:
    lookup = {norm(k): v for k, v in rec.items()}
    for c in COLS[key]:
        if c in lookup and str(lookup[c]).strip() != "":
            return str(lookup[c]).strip()
    return ""


def detect_text(text: str) -> bool:
    head = text[:5000].lstrip("﻿")
    return head.startswith("Statement,Header") or "Trades,Header,DataDiscriminator" in head


def parse_sections(text: str) -> dict[str, list[dict]]:
    """Regroupe les lignes « Data » par type de section, avec l'en-tête courant."""
    out: dict[str, list[dict]] = {}
    headers: dict[str, list[str]] = {}
    for row in csv.reader(io.StringIO(text.lstrip("﻿"))):
        if len(row) < 2:
            continue
        sec, typ = row[0].strip(), row[1].strip()
        if typ == "Header":
            headers[sec] = [c.strip() for c in row[2:]]
        elif typ == "Data" and sec in headers:
            kind = section_kind(sec)
            if kind:
                vals = row[2:] + [""] * (len(headers[sec]) - len(row[2:]))
                out.setdefault(kind, []).append(dict(zip(headers[sec], vals)))
    return out


def _date(s: str):
    s = str(s).split(",")[0].strip().split(";")[0]
    return pd.to_datetime(s, errors="coerce")


def _period_end(stmt: list[dict]):
    for r in stmt:
        if norm(_get(r, "field")) in ("period", "periode"):
            end = _get(r, "value").split("-")[-1].strip()
            for fr, en in MONTHS_FR.items():
                end = re.sub(fr, en, end, flags=re.I)
            d = pd.to_datetime(end, errors="coerce")
            return None if pd.isna(d) else d
    return None


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------
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
    for r in secs.get("instruments", []):
        sym, sid = _get(r, "symbol"), _get(r, "security_id")
        if sym:
            isin_of[sym] = sid if ISIN_RE.match(sid) else f"IBKR:{sym}"

    rows: list[dict] = []

    def eur(amount: float, ccy: str, d) -> float | None:
        r = market.fx_on(db, ccy, d, online)
        return None if r is None else amount / r

    # ---------------- achats / ventes ----------------
    for r in secs.get("trades", []):
        disc = _get(r, "discriminator")
        if disc and norm(disc) not in ("order", "trade", "ordre", "transaction"):
            continue
        cat = norm(_get(r, "category"))
        if "forex" in cat or "change" in cat:
            continue
        if not any(k in cat for k in ("stock", "action", "fund", "fonds", "etf", "bond", "obligation", "crypto")):
            warnings.append(f"Ignoré (catégorie « {_get(r, 'category')} ») : {_get(r, 'symbol')}")
            continue
        d = _date(_get(r, "datetime"))
        qty = to_number(_get(r, "quantity"))
        proceeds = to_number(_get(r, "proceeds")) or 0.0
        fee = to_number(_get(r, "fee")) or 0.0
        ccy = _get(r, "currency") or "EUR"
        if pd.isna(d) or not qty:
            continue
        sym = _get(r, "symbol")
        rows.append({"date": d, "kind": "buy" if qty > 0 else "sell", "isin": isin_of.get(sym, f"IBKR:{sym}"),
                     "name": sym, "quantity": abs(qty), "amount": eur(proceeds + fee, ccy, d),
                     "fees": abs(eur(fee, ccy, d) or 0.0), "symbol": sym})

    # ---------------- mouvements d'espèces ----------------
    for kind, default in (("cash", None), ("dividends", "dividend"), ("withholding", "tax"),
                          ("interest", "interest"), ("fees", "fee")):
        for r in secs.get(kind, []):
            ccy = _get(r, "currency")
            if not ccy or ccy.lower().startswith("total") or len(ccy) != 3:
                continue
            d = _date(_get(r, "date"))
            a = to_number(_get(r, "amount"))
            if pd.isna(d) or not a:
                continue
            k = default or ("deposit" if a > 0 else "withdrawal")
            desc = _get(r, "description")
            m = re.match(r"^([A-Z0-9.\-]+)\s*\(([A-Z]{2}[A-Z0-9]{9}\d)\)", desc)
            rows.append({"date": d, "kind": k, "isin": m.group(2) if m else None,
                         "name": (desc or kind)[:80], "quantity": None, "amount": eur(a, ccy, d),
                         "fees": 0.0, "symbol": None})

    # ---------------- positions de fin de période ----------------
    end = _period_end(secs.get("statement", []))
    if end is not None:
        snaps = []
        for r in secs.get("positions", []):
            disc = _get(r, "discriminator")
            if disc and norm(disc) not in ("summary", "synthese", "resume", "recapitulatif"):
                continue
            if "forex" in norm(_get(r, "category")):
                continue
            sym, q = _get(r, "symbol"), to_number(_get(r, "quantity"))
            if sym and q:
                snaps.append({"account_id": ACCOUNT_ID, "date": end.strftime("%Y-%m-%d"),
                              "isin": isin_of.get(sym, f"IBKR:{sym}"), "name": sym, "quantity": q,
                              "price": None, "avg_cost": None, "value": None})
        db.upsert("position_snapshots", pd.DataFrame(snaps), mode="replace")

    if not rows:
        return 0, warnings + ["Aucune opération dans ce relevé (ni achat, ni versement, ni dividende)."]
    out = pd.DataFrame(rows)
    if out["amount"].isna().any():
        warnings.append("Taux de change introuvable pour certaines opérations (hors ligne ?) : relancez l'import connecté.")
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
    for c in ("quantity", "amount"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["account_id"] = ACCOUNT_ID
    out["taxes"] = 0.0
    out["source"] = source
    out["d"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["id"] = stable_ids(out.assign(ts=out["date"].astype(str), q=out["quantity"].round(8)),
                           ["ts", "kind", "isin", "q", "name"], "ibkr")
    n = db.upsert("trades", out[["id", "account_id", "d", "kind", "isin", "name", "quantity", "amount", "fees",
                                 "taxes", "source"]].rename(columns={"d": "date"}))
    return n, warnings
