"""Saisie manuelle des opérations (formulaire du dashboard) et modèle CSV générique.

Une opération = compte, type, date, ticker Yahoo (et/ou ISIN), quantité, prix unitaire
dans la devise du titre, frais. Le montant EUR est calculé au taux de change du jour.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

import pandas as pd

from . import market
from .db import DB
from .parsing import norm, pick, read_csv_auto, to_number, to_dates

KINDS = {
    "Achat": "buy", "Vente": "sell", "Dividende": "dividend", "Versement": "deposit",
    "Retrait": "withdrawal", "Frais": "fee", "Intérêts": "interest", "Récompense (staking…)": "reward",
}
ACCOUNT_TYPES = {"PEA": "pea", "Compte-titres": "cto", "Crypto": "crypto", "Assurance vie": "assurance_vie"}
TEMPLATE_COLUMNS = ["date", "compte", "type", "ticker", "isin", "nom", "quantite", "prix", "devise", "frais", "note"]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def ensure_account(db: DB, name: str, kind: str = "cto", institution: str | None = None) -> str:
    """Retourne l'id d'un compte existant (par id ou nom) ou le crée."""
    acc = db.table("accounts")
    n = name.strip().lower()
    hit = acc[(acc["id"].str.lower() == n) | (acc["name"].str.lower() == n)]
    if hit.empty:
        hit = acc[acc["institution"].str.lower() == n]
    if not hit.empty:
        return hit["id"].iloc[0]
    acc_id = "manuel-inv:" + slug(name)
    db.upsert("accounts", pd.DataFrame([{"id": acc_id, "institution": institution or name, "name": name,
                                         "type": kind, "currency": "EUR"}]), mode="ignore")
    return acc_id


def instrument_key(ticker: str | None, isin: str | None) -> str | None:
    isin = (isin or "").strip().upper()
    if re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", isin):
        return isin
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return None
    m = re.match(r"^([A-Z0-9]+)-(USD|EUR|USDT)$", ticker)
    if m and m.group(1) not in ("BRK",):  # BTC-USD, ETH-EUR… -> même ligne que l'import Binance
        return f"CRYPTO-{m.group(1)}"
    return f"TICKER:{ticker}"


def register_instrument(db: DB, key: str, ticker: str | None, name: str | None, currency: str | None,
                        online: bool = True) -> None:
    known = db.read("SELECT isin, ticker FROM instruments WHERE isin = ?", [key])
    if not known.empty and known["ticker"].iloc[0]:
        return
    row = market.resolve_instrument(key, name or ticker or key, online=online)
    if ticker:
        row["ticker"] = ticker.strip().upper() if not key.startswith("CRYPTO-") else row["ticker"]
        row["resolved_by"] = "saisie"
    if currency and not key.startswith("CRYPTO-"):
        row["currency"] = currency
    if name and not row.get("name"):
        row["name"] = name
    db.upsert("instruments", pd.DataFrame([row]), mode="replace")


def add_operation(db: DB, *, account_id: str, kind: str, d: date, ticker: str | None = None,
                  isin: str | None = None, name: str | None = None, quantity: float | None = None,
                  price: float | None = None, currency: str = "EUR", fees: float = 0.0,
                  amount: float | None = None, note: str = "", fund_with_deposit: bool = False,
                  online: bool = True, op_id: str | None = None) -> dict:
    """Enregistre une opération. Retourne la ligne insérée (montants en EUR).

    * achat/vente : quantité × prix (devise du titre) ± frais, converti en EUR à la date ;
    * dividende/versement/retrait/frais/intérêts : `amount` en devise (positif).
    * fund_with_deposit : ajoute un versement du même montant (l'achat est financé par de l'argent frais).
    """
    key = instrument_key(ticker, isin) if kind in ("buy", "sell", "dividend", "reward") else None
    if key and kind in ("buy", "sell", "reward"):
        register_instrument(db, key, ticker, name, currency, online)
    rate = market.fx_on(db, currency, d, online) or 1.0
    fees_eur = abs(fees or 0.0) / rate
    if kind in ("buy", "sell"):
        if not quantity or price is None:
            raise ValueError("Quantité et prix sont nécessaires pour un achat ou une vente.")
        gross = abs(quantity) * price / rate
        amt = -(gross + fees_eur) if kind == "buy" else gross - fees_eur
    elif kind == "reward":
        amt = 0.0
    else:
        if amount is None:
            raise ValueError("Montant nécessaire.")
        a = abs(amount) / rate
        amt = -a if kind in ("withdrawal", "fee") else a
    row = {"id": op_id or "manuel-" + uuid.uuid4().hex[:12], "account_id": account_id, "date": d.isoformat(),
           "kind": kind, "isin": key, "name": name or ticker or note or kind,
           "quantity": abs(quantity) if quantity else None, "amount": round(amt, 6),
           "fees": round(fees_eur, 6), "taxes": 0.0, "source": "manuel" + (f" · {note}" if note else "")}
    db.upsert("trades", pd.DataFrame([row]), mode="replace")
    if fund_with_deposit and kind == "buy":
        db.upsert("trades", pd.DataFrame([{**row, "id": row["id"] + "-v", "kind": "deposit", "isin": None,
                                           "quantity": None, "amount": -amt, "fees": 0.0,
                                           "name": f"Versement pour {row['name']}"}]), mode="replace")
    return row


def delete_operations(db: DB, ids: list[str]) -> None:
    for i in ids:
        db.execute("DELETE FROM trades WHERE id = ? OR id = ?", (i, i + "-v"))


# --------------------------------------------------------------------------
# Modèle CSV générique (n'importe quel courtier)
# --------------------------------------------------------------------------
def detect(df: pd.DataFrame) -> bool:
    return bool(pick(df, "compte") and pick(df, "type") and pick(df, "date") and (pick(df, "ticker") or pick(df, "isin")))


def template_csv() -> str:
    ex = [
        ["2024-03-15", "PEA Boursorama", "Achat", "CW8.PA", "LU1681043599", "Amundi MSCI World", "3", "452,10", "EUR", "1,99", ""],
        ["2024-04-02", "IBKR", "Achat", "AAPL", "US0378331005", "Apple", "5", "169,20", "USD", "1", ""],
        ["2024-06-10", "PEA Boursorama", "Dividende", "TTE.PA", "FR0000120271", "TotalEnergies", "", "34", "EUR", "", "montant dans la colonne prix"],
        ["2024-07-01", "PEA Boursorama", "Versement", "", "", "", "", "500", "EUR", "", "montant dans la colonne prix"],
    ]
    return "\n".join([";".join(TEMPLATE_COLUMNS)] + [";".join(r) for r in ex]) + "\n"


def import_template(db: DB, path, online: bool = True) -> tuple[str, int]:
    df = read_csv_auto(path)
    c = {k: pick(df, k, *({"quantite": ["quantité", "qty"], "prix": ["price", "cours", "montant"],
                             "nom": ["name", "libellé"], "devise": ["currency"]}.get(k, []))) for k in TEMPLATE_COLUMNS}
    dates = to_dates(df[c["date"]])
    rev = {norm(k): v for k, v in KINDS.items()} | {norm(v): v for v in KINDS.values()} | {"buy": "buy", "sell": "sell"}
    n, errors = 0, []
    for i, r in df.iterrows():
        try:
            kind = rev.get(norm(r[c["type"]]))
            if not kind:
                raise ValueError(f"type inconnu « {r[c['type']]} »")
            acc_name = str(r[c["compte"]]).strip()
            acc = ensure_account(db, acc_name, "pea" if "pea" in acc_name.lower() else
                                 "crypto" if any(k in acc_name.lower() for k in ("binance", "crypto", "kraken", "coinbase")) else "cto")
            val = to_number(r[c["prix"]]) if c["prix"] else None
            g = lambda k: (str(r[c[k]]).strip() if c[k] and str(r[c[k]]).strip() else None)  # noqa: E731
            add_operation(db, account_id=acc, kind=kind, d=dates[i].date(), ticker=g("ticker"), isin=g("isin"),
                          name=g("nom"), quantity=to_number(g("quantite")), price=val,
                          currency=(g("devise") or "EUR").upper(), fees=to_number(g("frais")) or 0.0,
                          amount=val, note=g("note") or "", online=online,
                          op_id=f"modele-{slug(acc_name)}-{dates[i]:%Y%m%d}-{kind}-{g('ticker') or g('isin') or ''}-{g('quantite') or val}")
            n += 1
        except Exception as e:
            errors.append(f"ligne {i + 2} : {e}")
    if errors:
        db.log("modele", getattr(path, "name", str(path)), 0, "warning", " | ".join(errors[:10]))
    db.log("modele", getattr(path, "name", str(path)), n, "ok", "")
    if errors and not n:
        raise ValueError("; ".join(errors[:5]))
    return "modèle finmon", n


def save_holdings(db: DB, account_id: str, d: date, lines: pd.DataFrame, crypto: bool = False,
                  online: bool = True) -> int:
    """Enregistre un relevé COMPLET des positions d'un compte à une date.

    `lines` : colonnes ticker, isin (facultatif), name (facultatif), quantity.
    Le portefeuille est recalé sur ce relevé : une ligne absente est considérée comme sortie,
    une ligne en plus (dépôt, conversion, Earn non importés) est ajoutée comme apport au cours du jour.
    Sur un compte crypto, « SOL » est compris comme SOL-USD.
    """
    rows = []
    for r in lines.fillna("").itertuples(index=False):
        ticker = str(getattr(r, "ticker", "") or "").strip().upper()
        isin = str(getattr(r, "isin", "") or "").strip().upper()
        qty = pd.to_numeric(getattr(r, "quantity", None), errors="coerce")
        if not (ticker or isin) or pd.isna(qty) or qty <= 0:
            continue
        if crypto and ticker and "-" not in ticker and not isin:
            ticker = f"{ticker}-USD"
        key = isin if isin and not ticker else instrument_key(ticker, isin)
        if key is None:
            continue
        name = str(getattr(r, "name", "") or "").strip() or None
        register_instrument(db, key, ticker or None, name, None, online=online)
        rows.append({"account_id": account_id, "date": d.isoformat(), "isin": key,
                     "name": name or (ticker.split("-")[0] if key.startswith("CRYPTO-") else ticker or key),
                     "quantity": float(qty), "price": None, "avg_cost": None, "value": None})
    db.execute("DELETE FROM position_snapshots WHERE account_id = ? AND date = ?", [account_id, d.isoformat()])
    return db.upsert("position_snapshots", pd.DataFrame(rows), mode="replace")
