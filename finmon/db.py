"""Base SQLite locale : schéma et helpers d'écriture/lecture."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    institution TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,          -- courant | livret | pea | cto | assurance_vie | crypto | epargne_salariale | autre
    currency TEXT NOT NULL DEFAULT 'EUR',
    rate REAL                    -- taux annuel en % (livrets), facultatif
);

-- Opérations des comptes bancaires (courant, livrets, cash Trade Republic)
CREATE TABLE IF NOT EXISTS cash_transactions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value_date TEXT,
    label TEXT NOT NULL,
    merchant TEXT,
    amount REAL NOT NULL,
    bank_category TEXT,
    bank_category_parent TEXT,
    foreign_currency TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS ix_cash_date ON cash_transactions(date);

-- Opérations sur titres : achats, ventes, dividendes, frais...
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    date TEXT NOT NULL,
    kind TEXT NOT NULL,          -- buy | sell | dividend | interest | fee | tax | deposit | withdrawal | transfer_in | transfer_out | split
    isin TEXT,
    name TEXT,
    quantity REAL,
    amount REAL,                 -- effet cash en EUR (négatif = sortie)
    fees REAL DEFAULT 0,
    taxes REAL DEFAULT 0,
    source TEXT
);
CREATE INDEX IF NOT EXISTS ix_trades_date ON trades(date);

-- Photos de portefeuille (pytr portfolio, export positions Boursorama)
CREATE TABLE IF NOT EXISTS position_snapshots (
    account_id TEXT NOT NULL,
    date TEXT NOT NULL,
    isin TEXT NOT NULL,
    name TEXT,
    quantity REAL,
    price REAL,
    avg_cost REAL,
    value REAL,
    PRIMARY KEY (account_id, date, isin)
);

-- Soldes connus à une date (export banque ou saisie manuelle)
CREATE TABLE IF NOT EXISTS balance_snapshots (
    account_id TEXT NOT NULL,
    date TEXT NOT NULL,
    balance REAL NOT NULL,
    source TEXT,
    PRIMARY KEY (account_id, date)
);

CREATE TABLE IF NOT EXISTS instruments (
    isin TEXT PRIMARY KEY,
    name TEXT,
    ticker TEXT,
    currency TEXT,
    asset_class TEXT,
    region TEXT,
    sector TEXT,
    exposure TEXT,               -- JSON {"USD": 0.7, ...}
    regions TEXT,                -- JSON {"Amérique du Nord": 0.7, ...}
    sectors TEXT,                -- JSON
    resolved_by TEXT
);

CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    close REAL NOT NULL,
    PRIMARY KEY (symbol, date)
);

-- Taux de change : unités de devise pour 1 EUR
CREATE TABLE IF NOT EXISTS fx_rates (
    currency TEXT NOT NULL,
    date TEXT NOT NULL,
    rate REAL NOT NULL,
    PRIMARY KEY (currency, date)
);

CREATE TABLE IF NOT EXISTS category_overrides (
    tx_id TEXT PRIMARY KEY,
    category TEXT,
    vacation TEXT
);

CREATE TABLE IF NOT EXISTS vacations (
    name TEXT PRIMARY KEY,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS manual_contributions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,       -- compte valorisé à la main (ex. plan d'épargne entreprise)
    date TEXT NOT NULL,
    amount REAL NOT NULL,           -- versé (+) ou retiré (−), en EUR
    label TEXT                      -- intéressement, participation, abondement, versement personnel…
);

CREATE TABLE IF NOT EXISTS manual_adjustments (
    id TEXT PRIMARY KEY,
    month TEXT NOT NULL,            -- AAAA-MM
    target TEXT NOT NULL,           -- depenses | revenus
    amount REAL NOT NULL,           -- signé : + augmente, − réduit
    label TEXT
);

CREATE TABLE IF NOT EXISTS import_log (
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    file TEXT,
    rows INTEGER,
    status TEXT,
    message TEXT
);
"""


class DB:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)
            # Migrations légères des bases créées par une version antérieure.
            cols = {r[1] for r in con.execute("PRAGMA table_info(accounts)")}
            if "rate" not in cols:
                con.execute("ALTER TABLE accounts ADD COLUMN rate REAL")
            ov = {r[1] for r in con.execute("PRAGMA table_info(category_overrides)")}
            if ov and "factor" not in ov:
                # Part d'une dépense attribuée à soi (ex. 0,5 pour une dépense partagée en deux).
                con.execute("ALTER TABLE category_overrides ADD COLUMN factor REAL")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ---------- écriture ----------
    def upsert(self, table: str, df: pd.DataFrame, mode: str = "ignore") -> int:
        """Insère les lignes ; mode 'ignore' (dédoublonnage) ou 'replace'."""
        if df is None or df.empty:
            return 0
        cols = list(df.columns)
        sql = (
            f"INSERT OR {mode.upper()} INTO {table} ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})"
        )
        rows = [tuple(_py(v) for v in r) for r in df.itertuples(index=False, name=None)]
        with self.connect() as con:
            before = con.total_changes
            con.executemany(sql, rows)
            return con.total_changes - before

    def execute(self, sql: str, params: Iterable = ()) -> None:
        with self.connect() as con:
            con.execute(sql, tuple(params))

    # ---------- lecture ----------
    def read(self, sql: str, params: Iterable = ()) -> pd.DataFrame:
        with self.connect() as con:
            return pd.read_sql_query(sql, con, params=tuple(params))

    def table(self, name: str) -> pd.DataFrame:
        return self.read(f"SELECT * FROM {name}")

    def log(self, source: str, file: str | None, rows: int, status: str, message: str = "") -> None:
        self.execute(
            "INSERT INTO import_log VALUES (datetime('now','localtime'),?,?,?,?,?)",
            (source, file, rows, status, message),
        )


def _py(v):
    """Convertit les types numpy/pandas en types natifs pour sqlite3."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        return v.item()
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    return v


def set_override(db: "DB", tx_id: str, **fields) -> None:
    """Met à jour une correction d'opération champ par champ (category, vacation, factor)
    sans effacer les autres champs déjà corrigés."""
    allowed = {k: v for k, v in fields.items() if k in ("category", "vacation", "factor")}
    if not allowed:
        return
    cols = ", ".join(["tx_id", *allowed])
    marks = ", ".join("?" * (len(allowed) + 1))
    upd = ", ".join(f"{k} = excluded.{k}" for k in allowed)
    db.execute(f"INSERT INTO category_overrides ({cols}) VALUES ({marks}) "
               f"ON CONFLICT(tx_id) DO UPDATE SET {upd}", [tx_id, *[_py(v) for v in allowed.values()]])
