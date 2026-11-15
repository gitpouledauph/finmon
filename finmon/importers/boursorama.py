"""Import des exports CSV Boursorama / BoursoBank.

Trois formats sont reconnus automatiquement :

* **Opérations de compte** (compte courant, livrets) — « Mes comptes > compte >
  Exporter » : colonnes dateOp;dateVal;label;category;categoryParent;
  supplierFound;amount;comment;accountNum;accountLabel;accountbalance.
* **Positions** d'un PEA/CTO — colonnes du type libellé / ISIN / quantité /
  cours / prix de revient / valorisation. L'export « positions comptables »
  de BoursoBank (Bourse › Portefeuille › Exporter) a les colonnes
  name;isin;quantity;buyingPrice;lastPrice;intradayVariation;amount;
  amountVariation;variation;lastMovementDate;compensation.
* **Mouvements** d'un PEA/CTO — colonnes du type date / opération / libellé /
  quantité / cours / montant.

Les noms de colonnes sont comparés de façon tolérante (accents, casse,
espaces), pour absorber les variations entre versions de l'export.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from .. import config
from ..db import DB
from ..parsing import pick, read_csv_auto, stable_ids, to_dates, to_numbers

ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
CCY_RE = re.compile(r"\b(\d+[.,]\d{2})\s?(USD|GBP|CHF|JPY|CAD|AUD|SEK|NOK|DKK|PLN|CZK|HUF|THB|MAD|TND|TRY|MXN|BRL|SGD|HKD|CNY|IDR|VND|ZAR|AED|ILS|ISK|NZD|KRW|INR)\b")


# --------------------------------------------------------------------------
# Détection
# --------------------------------------------------------------------------
def detect(df: pd.DataFrame) -> str | None:
    if pick(df, "dateOp", "Date opération", "Date operation") and pick(df, "amount", "montant") and pick(df, "label", "libellé"):
        if not pick(df, "quantité", "quantity", "qté"):
            return "operations"
    if pick(df, "quantité", "quantity", "qté", "nombre"):
        if pick(df, "opération", "operation", "sens", "type") and pick(df, "date", "date opération", "dateOp"):
            return "mouvements"
        return "positions"
    return None


def import_file(db: DB, path: Path | str, account_hint: str | None = None) -> tuple[str, int]:
    df = read_csv_auto(path)
    kind = detect(df)
    name = Path(path).name if not isinstance(path, bytes) else "upload"
    if kind == "operations":
        n = import_operations(db, df, source=name)
    elif kind == "positions":
        n = import_positions(db, df, source=name, account_hint=account_hint)
    elif kind == "mouvements":
        n = import_mouvements(db, df, source=name, account_hint=account_hint)
    else:
        raise ValueError(
            f"Format Boursorama non reconnu pour {name}. Colonnes trouvées : {list(df.columns)}"
        )
    db.log("boursorama", name, n, "ok", kind)
    return kind, n


# --------------------------------------------------------------------------
# Comptes courants / livrets
# --------------------------------------------------------------------------
def guess_account_type(label: str) -> str:
    l = (label or "").lower()
    if any(k in l for k in ("livret", "ldd", "lep", "csl", "epargne", "pel", "cel")):
        return "livret"
    if "pea" in l:
        return "pea"
    if "ordinaire" in l or "cto" in l or "titres" in l:
        return "cto"
    if "vie" in l:
        return "assurance_vie"
    return "courant"


def _account_row(num: str, label: str, inst: str = "Boursorama") -> dict:
    conf = config.settings()["accounts"].get(str(num), {})
    return {
        "id": f"bourso:{num}",
        "institution": inst,
        "name": conf.get("name") or (label.strip() if label else f"Compte {num}"),
        "type": conf.get("type") or guess_account_type(label),
        "currency": conf.get("currency", "EUR"),
    }


def clean_merchant(label: str) -> str:
    s = str(label).upper()
    s = re.sub(r"^(CARTE|CB|PAIEMENT CB|PRLV SEPA|PRLV|VIR(EMENT)? SEPA( INST)?( RECU| EMIS)?|VIR(EMENT)?|AVOIR)\s+", "", s)
    s = re.sub(r"^\d{2}/\d{2}(/\d{2,4})?\s+", "", s)
    s = re.sub(r"\bCB\*\d+.*$", "", s)
    s = CCY_RE.sub("", s)
    s = re.sub(r"1 EURO? ?=.*$", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -*/")
    return s[:40]


def import_operations(db: DB, df: pd.DataFrame, source: str = "") -> int:
    c_date = pick(df, "dateOp", "Date opération", "Date operation", "date")
    c_vdate = pick(df, "dateVal", "Date valeur")
    c_label = pick(df, "label", "libellé", "libelle")
    c_amount = pick(df, "amount", "montant")
    c_cat = pick(df, "category", "catégorie")
    c_parent = pick(df, "categoryParent", "catégorie parente")
    c_supplier = pick(df, "supplierFound", "fournisseur")
    c_num = pick(df, "accountNum", "numéro de compte", "compte")
    c_alabel = pick(df, "accountLabel", "libellé compte")
    c_bal = pick(df, "accountbalance", "solde")

    out = pd.DataFrame(
        {
            "date": to_dates(df[c_date]),
            "value_date": to_dates(df[c_vdate]) if c_vdate else pd.NaT,
            "label": df[c_label].str.strip(),
            "amount": to_numbers(df[c_amount]),
            "bank_category": df[c_cat].str.strip() if c_cat else None,
            "bank_category_parent": df[c_parent].str.strip() if c_parent else None,
            "num": df[c_num].str.strip() if c_num else "inconnu",
            "alabel": df[c_alabel].str.strip() if c_alabel else "",
            "supplier": df[c_supplier].str.strip() if c_supplier else "",
        }
    )
    out = out.dropna(subset=["date", "amount"])
    if out.empty:
        return 0

    accounts = (
        out.groupby("num")["alabel"].first().reset_index().apply(lambda r: _account_row(r["num"], r["alabel"]), axis=1)
    )
    db.upsert("accounts", pd.DataFrame(list(accounts)), mode="replace")

    out["account_id"] = "bourso:" + out["num"]
    out["merchant"] = [
        (s.upper() if s else clean_merchant(l)) for s, l in zip(out["supplier"], out["label"])
    ]
    out["foreign_currency"] = out["label"].str.extract(CCY_RE)[1]
    out["source"] = source
    out["id"] = stable_ids(
        out.assign(d=out["date"].dt.strftime("%Y-%m-%d"), a=out["amount"].round(2)),
        ["account_id", "d", "label", "a"],
        "bourso",
    )
    cols = ["id", "account_id", "date", "value_date", "label", "merchant", "amount",
            "bank_category", "bank_category_parent", "foreign_currency", "source"]
    rows = out[cols].copy()
    rows["date"] = rows["date"].dt.strftime("%Y-%m-%d")
    rows["value_date"] = pd.to_datetime(rows["value_date"]).dt.strftime("%Y-%m-%d")
    n = db.upsert("cash_transactions", rows)

    # Solde : Boursorama répète le solde actuel du compte sur chaque ligne.
    if c_bal:
        out["bal"] = to_numbers(df.loc[out.index, c_bal])
        snaps = (
            out.dropna(subset=["bal"]).groupby("account_id").agg(date=("date", "max"), balance=("bal", "first")).reset_index()
        )
        if not snaps.empty:
            snaps["date"] = snaps["date"].dt.strftime("%Y-%m-%d")
            snaps["source"] = "export:" + source
            db.upsert("balance_snapshots", snaps[["account_id", "date", "balance", "source"]], mode="replace")
    return n


# --------------------------------------------------------------------------
# PEA / CTO
# --------------------------------------------------------------------------
def _resolve_isin(name: str, isin_cell: str | None) -> str | None:
    for s in (isin_cell, name):
        if s:
            m = ISIN_RE.search(str(s).upper())
            if m:
                return m.group(1)
    aliases = {k.upper(): v for k, v in (config.instruments_config().get("aliases") or {}).items()}
    key = str(name or "").upper().strip()
    if key in aliases:
        return aliases[key]
    for alias, isin in aliases.items():
        if alias in key:
            return isin
    return None


def _envelope_account(db: DB, hint: str | None, df_name: str) -> str:
    hint = (hint or "pea").lower()
    kind = "pea" if "pea" in hint else "cto"
    acc_id = f"bourso:{kind}"
    db.upsert(
        "accounts",
        pd.DataFrame([{"id": acc_id, "institution": "Boursorama", "name": f"{kind.upper()} Boursorama",
                       "type": kind, "currency": "EUR"}]),
        mode="ignore",
    )
    return acc_id


def import_positions(db: DB, df: pd.DataFrame, source: str = "", account_hint: str | None = None,
                     snapshot_date: str | None = None) -> int:
    c_name = pick(df, "libellé", "libelle", "name", "valeur", "nom", "titre")
    c_isin = pick(df, "isin", "code isin", "code")
    c_qty = pick(df, "quantité", "quantity", "qté", "nombre")
    c_price = pick(df, "cours", "lastPrice", "dernier cours", "cours actuel", "prix")
    c_cost = pick(df, "prix de revient", "PRU", "buyingPrice", "prix revient unitaire", "pru unitaire")
    c_value = pick(df, "valorisation", "montant", "amount", "valeur totale", "evaluation")
    hint = account_hint or source
    acc = _envelope_account(db, hint, source)
    # « export-positions-comptables-01-02-2026_10-00-00.csv » : la date de l'export est dans le nom.
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", source or "")
    d = snapshot_date or (f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else date.today().isoformat())

    rows = []
    unresolved = []
    for _, r in df.iterrows():
        name = r[c_name] if c_name else ""
        isin = _resolve_isin(name, r[c_isin] if c_isin else None)
        if not isin:
            if name:
                unresolved.append(name)
            continue
        qty = to_numbers(pd.Series([r[c_qty]]))[0] if c_qty else None
        price = to_numbers(pd.Series([r[c_price]]))[0] if c_price else None
        cost = to_numbers(pd.Series([r[c_cost]]))[0] if c_cost else None
        val = to_numbers(pd.Series([r[c_value]]))[0] if c_value else None
        if val is None and qty is not None and price is not None:
            val = qty * price
        rows.append({"account_id": acc, "date": d, "isin": isin, "name": str(name).strip(),
                     "quantity": qty, "price": price, "avg_cost": cost, "value": val})
    if unresolved:
        db.log("boursorama", source, 0, "warning",
               "ISIN introuvable pour : " + ", ".join(unresolved) + " — ajoutez-les dans config/instruments.yaml > aliases")
    n = db.upsert("position_snapshots", pd.DataFrame(rows), mode="replace")
    c_last = pick(df, "lastMovementDate", "dernier mouvement", "date dernier mouvement", "dernier mvt")
    if c_last and rows:
        _entries_from_positions(db, acc, pd.DataFrame(rows), df[c_last], source)
    return n


def _entries_from_positions(db: DB, acc: str, snap: pd.DataFrame, last_moves: pd.Series, source: str) -> None:
    """Sans historique d'opérations, chaque ligne entre en portefeuille à sa date de « dernier mouvement »,
    pour son prix de revient : la plus-value latente est exacte, la courbe de valeur est approchée.
    Ces entrées (source « positions:… ») sont remplacées dès qu'un historique de mouvements est importé."""
    real = db.read("SELECT COUNT(*) n FROM trades WHERE account_id = ? AND source NOT LIKE 'positions:%'", [acc])
    if real["n"].iloc[0]:
        return
    db.execute("DELETE FROM trades WHERE account_id = ? AND source LIKE 'positions:%'", [acc])
    d = to_dates(last_moves.reset_index(drop=True))
    snap = snap.reset_index(drop=True).assign(d=d)
    snap = snap.dropna(subset=["d", "quantity", "avg_cost"])
    if snap.empty:
        return
    out = pd.DataFrame({
        "account_id": acc, "date": snap["d"].dt.strftime("%Y-%m-%d"), "kind": "buy",
        "isin": snap["isin"], "name": snap["name"], "quantity": snap["quantity"],
        "amount": -(snap["quantity"] * snap["avg_cost"]), "fees": 0.0, "taxes": 0.0,
        "source": "positions:" + source,
    })
    out["id"] = stable_ids(out, ["account_id", "isin", "source"], "bourso-pos")
    db.upsert("trades", out[["id", "account_id", "date", "kind", "isin", "name", "quantity", "amount", "fees",
                             "taxes", "source"]])


MOUV_KIND = [
    (r"achat|souscription|buy", "buy"),
    (r"vente|cession|sell", "sell"),
    (r"dividende|coupon|distribution", "dividend"),
    (r"frais|droits de garde|commission", "fee"),
    (r"prelevement|impot|taxe|csg|ttf", "tax"),
    (r"versement|depot|virement recu|apport", "deposit"),
    (r"retrait|virement emis", "withdrawal"),
    (r"division|split|regroupement", "split"),
]


def _mouv_kind(s: str) -> str | None:
    from ..parsing import norm

    n = norm(s)
    for pat, k in MOUV_KIND:
        if re.search(pat.replace(" ", ""), n):
            return k
    return None


def import_mouvements(db: DB, df: pd.DataFrame, source: str = "", account_hint: str | None = None) -> int:
    acc0 = _envelope_account(db, account_hint or source, source)
    db.execute("DELETE FROM trades WHERE account_id = ? AND source LIKE 'positions:%'", [acc0])
    c_date = pick(df, "date", "date opération", "dateOp", "date d'exécution", "date execution")
    c_op = pick(df, "opération", "operation", "sens", "type")
    c_name = pick(df, "libellé", "libelle", "valeur", "nom", "titre", "name")
    c_isin = pick(df, "isin", "code isin", "code")
    c_qty = pick(df, "quantité", "quantity", "qté", "nombre")
    c_amount = pick(df, "montant net", "montant", "amount", "net")
    c_fees = pick(df, "frais", "commission", "courtage")
    c_price = pick(df, "cours", "prix", "cours d'exécution")
    acc = _envelope_account(db, account_hint or source, source)

    out = pd.DataFrame({
        "date": to_dates(df[c_date]),
        "op": df[c_op],
        "name": df[c_name] if c_name else "",
        "isin_cell": df[c_isin] if c_isin else "",
        "quantity": to_numbers(df[c_qty]).abs(),
        "amount": to_numbers(df[c_amount]) if c_amount else None,
        "fees": to_numbers(df[c_fees]).abs() if c_fees else 0.0,
        "price": to_numbers(df[c_price]) if c_price else None,
    }).dropna(subset=["date"])
    out["kind"] = out["op"].map(_mouv_kind)
    out["isin"] = [_resolve_isin(n, i) for n, i in zip(out["name"], out["isin_cell"])]
    out = out.dropna(subset=["kind"])
    # Montant manquant : quantité x cours.
    if out["amount"].isna().any() and "price" in out:
        est = out["quantity"] * out["price"]
        out["amount"] = out["amount"].fillna(est)
    # Convention : achat = sortie de cash (négatif).
    sign = out["kind"].map({"buy": -1, "fee": -1, "tax": -1, "withdrawal": -1}).fillna(1)
    out["amount"] = out["amount"].abs() * sign
    out["account_id"] = acc
    out["taxes"] = 0.0
    out["source"] = source
    out["d"] = out["date"].dt.strftime("%Y-%m-%d")
    out["id"] = stable_ids(out, ["account_id", "d", "kind", "name", "quantity", "amount"], "bourso-titres")
    rows = out.rename(columns={"d": "date_s"})[
        ["id", "account_id", "date_s", "kind", "isin", "name", "quantity", "amount", "fees", "taxes", "source"]
    ].rename(columns={"date_s": "date"})
    return db.upsert("trades", rows)
