"""Import Trade Republic via pytr (client open source, non officiel).

* ``pytr export_transactions`` -> account_transactions.csv
  (Date;Type;Value;Note;ISIN;Shares;Fees;Taxes;ISIN2;Shares2, en anglais,
  français ou allemand selon --lang)
* ``pytr portfolio -o portfolio.csv`` -> Name;ISIN;quantity;price;avgCost;netValue

``sync()`` lance pytr en local : les identifiants restent dans ~/.pytr.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from ..db import DB
from ..parsing import norm, pick, read_csv_auto, stable_ids, to_dates, to_numbers

ACCOUNT_ID = "tr:compte"

TYPE_MAP = {
    # en / fr / de  (libellés produits par pytr)
    "buy": "buy", "achat": "buy", "kauf": "buy",
    "sell": "sell", "vente": "sell", "verkauf": "sell",
    "dividend": "dividend", "dividendes": "dividend", "dividende": "dividend",
    "interest": "interest", "interets": "interest", "zinsen": "interest",
    "interestcharge": "fee", "fraisdinterets": "fee", "zinsbelastung": "fee",
    "deposit": "deposit", "depot": "deposit", "einlage": "deposit",
    "removal": "withdrawal", "retrait": "withdrawal", "entnahme": "withdrawal",
    "fees": "fee", "frais": "fee", "gebuhren": "fee",
    "feesrefund": "fee", "remboursementdefrais": "fee", "gebuhrenerstattung": "fee",
    "taxes": "tax", "impotstaxes": "tax", "steuern": "tax",
    "taxrefund": "tax", "remboursementimpotstaxes": "tax", "steuerruckerstattung": "tax",
    "transferinbound": "transfer_in", "transfertentrant": "transfer_in", "umbuchungeingang": "transfer_in",
    "transferoutbound": "transfer_out", "transfertsortant": "transfer_out", "umbuchungausgang": "transfer_out",
    "split": "split", "spinoff": "transfer_in", "swap": "split",
}

CARD_HINTS = ("card", "carte", "karte")


def _account(db: DB) -> None:
    db.upsert("accounts", pd.DataFrame([{
        "id": ACCOUNT_ID, "institution": "Trade Republic", "name": "Trade Republic",
        "type": "cto", "currency": "EUR"}]), mode="ignore")


def detect(df: pd.DataFrame) -> str | None:
    if pick(df, "Type", "Typ") and pick(df, "Value", "Valeur", "Wert") and pick(df, "Shares", "Parts", "Stück"):
        return "transactions"
    if pick(df, "netValue") and pick(df, "avgCost"):
        return "portfolio"
    return None


def import_file(db: DB, path: Path | str) -> tuple[str, int]:
    df = read_csv_auto(path)
    kind = detect(df)
    name = Path(path).name
    if kind == "transactions":
        n = import_transactions(db, df, source=name)
    elif kind == "portfolio":
        n = import_portfolio(db, df, source=name, snapshot_date=_file_date(path))
    else:
        raise ValueError(f"Format Trade Republic non reconnu pour {name} : {list(df.columns)}")
    db.log("traderepublic", name, n, "ok", kind)
    return kind, n


def _file_date(path) -> str:
    try:
        return date.fromtimestamp(Path(path).stat().st_mtime).isoformat()
    except OSError:
        return date.today().isoformat()


def import_transactions(db: DB, df: pd.DataFrame, source: str = "") -> int:
    _account(db)
    c = {
        "date": pick(df, "Date", "Datum"),
        "type": pick(df, "Type", "Typ"),
        "value": pick(df, "Value", "Valeur", "Wert"),
        "note": pick(df, "Note", "Notiz"),
        "isin": pick(df, "ISIN"),
        "shares": pick(df, "Shares", "Parts", "Stück"),
        "fees": pick(df, "Fees", "Frais", "Gebühren"),
        "taxes": pick(df, "Taxes", "Impôts / Taxes", "Steuern"),
    }
    out = pd.DataFrame({
        "date": to_dates(df[c["date"]]),
        "raw_type": df[c["type"]],
        "amount": to_numbers(df[c["value"]]),
        "name": df[c["note"]].str.strip() if c["note"] else "",
        "isin": df[c["isin"]].str.strip().replace("", None) if c["isin"] else None,
        "quantity": to_numbers(df[c["shares"]]).abs() if c["shares"] else None,
        "fees": to_numbers(df[c["fees"]]).fillna(0).abs() if c["fees"] else 0.0,
        "taxes": to_numbers(df[c["taxes"]]).fillna(0).abs() if c["taxes"] else 0.0,
    }).dropna(subset=["date"])
    out["kind"] = out["raw_type"].map(lambda t: TYPE_MAP.get(norm(t)))
    unknown = sorted(set(out.loc[out["kind"].isna(), "raw_type"]))
    if unknown:
        db.log("traderepublic", source, 0, "warning", f"Types ignorés : {unknown}")
    out = out.dropna(subset=["kind"]).copy()
    out["account_id"] = ACCOUNT_ID
    out["source"] = source
    out["d"] = out["date"].dt.strftime("%Y-%m-%d")
    out["id"] = stable_ids(
        out.assign(a=out["amount"].round(2), q=out["quantity"].round(6)),
        ["d", "raw_type", "isin", "q", "a", "name"], "tr")
    rows = out[["id", "account_id", "d", "kind", "isin", "name", "quantity", "amount", "fees", "taxes", "source"]]
    n = db.upsert("trades", rows.rename(columns={"d": "date"}))

    # Paiements carte Trade Republic -> budget.
    is_card = out["kind"].isin(["withdrawal", "deposit"]) & out["isin"].isna() & \
        out["name"].str.lower().str.contains("|".join(CARD_HINTS), na=False)
    card = out[is_card]
    if not card.empty:
        merchant = card["name"].str.split(" - ", n=1).str[-1].str.upper().str[:40]
        db.upsert("cash_transactions", pd.DataFrame({
            "id": card["id"], "account_id": ACCOUNT_ID, "date": card["d"], "value_date": card["d"],
            "label": card["name"], "merchant": merchant, "amount": card["amount"],
            "bank_category": None, "bank_category_parent": None, "foreign_currency": None, "source": source,
        }))
    return n


def import_portfolio(db: DB, df: pd.DataFrame, source: str = "", snapshot_date: str | None = None) -> int:
    _account(db)
    d = snapshot_date or date.today().isoformat()
    rows = pd.DataFrame({
        "account_id": ACCOUNT_ID, "date": d,
        "isin": df[pick(df, "ISIN")].str.strip(),
        "name": df[pick(df, "Name")].str.strip(),
        "quantity": to_numbers(df[pick(df, "quantity")]),
        "price": to_numbers(df[pick(df, "price")]),
        "avg_cost": to_numbers(df[pick(df, "avgCost")]),
        "value": to_numbers(df[pick(df, "netValue")]),
    })
    return db.upsert("position_snapshots", rows[rows["isin"] != ""], mode="replace")


# --------------------------------------------------------------------------
# Export historique unique via pytr (une seule connexion)
# --------------------------------------------------------------------------
def export_history(db: DB, outdir: Path) -> list[str]:
    """Se connecte UNE fois à Trade Republic (connexion « v2 » : validation dans l'app),
    exporte l'historique des transactions et la photo du portefeuille, puis importe.

    Rien n'est enregistré dans ~/.pytr (ni PIN, ni cookies) : aucun lien ne subsiste.
    """
    import asyncio

    try:
        from pytr.account import login
        from pytr.event import Event
        from pytr.portfolio import Portfolio
        from pytr.timeline import Timeline
        from pytr.transactions import TransactionExporter
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pytr n'est pas installé : pip install pytr") from e

    outdir.mkdir(parents=True, exist_ok=True)
    tx = outdir / "account_transactions.csv"
    pf = outdir / "portfolio.csv"
    logs = []

    print("Connexion à Trade Republic : saisissez votre numéro (+33…) et votre PIN, "
          "puis CONFIRMEZ la connexion dans l'app Trade Republic sur votre téléphone.")
    tr = login(store_credentials=False, waf_token="default", v2=True)

    print("Téléchargement de l'historique (peut prendre quelques minutes)…")
    tl = Timeline(tr, outdir, store_event_database=False)
    portfolio = Portfolio(tr, output=pf, lang="en", decimal_localization=False)

    async def run_all():
        await tl.tl_loop()
        try:  # même connexion, même boucle : pas de seconde validation
            await asyncio.wait_for(portfolio.portfolio_loop(), timeout=180)
            return None
        except Exception as e:  # la photo du portefeuille est un plus, pas indispensable
            return e

    pf_error = asyncio.run(run_all())
    with open(tx, "w", encoding="utf-8") as f:
        TransactionExporter(lang="en", date_with_time=True, decimal_localization=False).export(
            f, [Event.from_dict(item) for item in tl.events], sort=True, format="csv")
    logs.append(f"Historique exporté : {len(tl.events)} événements")
    if pf_error is None:
        portfolio.write_csv()
        logs.append("Portefeuille exporté")
    else:
        logs.append(f"Photo du portefeuille non récupérée ({type(pf_error).__name__}) — l'historique suffit.")

    for f in (tx, pf):
        if f.exists() and f.stat().st_size > 0:
            kind, n = import_file(db, f)
            logs.append(f"{f.name} : {n} lignes importées ({kind})")
    return logs
