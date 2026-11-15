"""Point d'entrée unique : charge la base et calcule tout ce que le dashboard affiche."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .analytics import allocation as alloc_mod
from .analytics import budget, networth, portfolio
from .db import DB


@dataclass
class Bundle:
    accounts: pd.DataFrame
    tx: pd.DataFrame                    # opérations classées
    vacations: pd.DataFrame
    portfolio: portfolio.PortfolioResult
    cash: pd.DataFrame                  # soldes quotidiens comptes courants / livrets
    networth: pd.DataFrame
    allocation: dict
    instruments: pd.DataFrame
    snapshots: pd.DataFrame
    balance_snapshots: pd.DataFrame
    import_log: pd.DataFrame
    benchmark: pd.Series
    warnings: list[str] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return not (self.accounts.empty)


def load(db: DB, today: date | None = None) -> Bundle:
    from . import config

    accounts = db.table("accounts")
    raw_tx = db.table("cash_transactions")
    overrides = db.table("category_overrides")
    tx = budget.classify(raw_tx, overrides, dict(zip(accounts["id"], accounts["type"])))
    vacations = db.read("SELECT * FROM vacations ORDER BY start")
    trades = db.table("trades")
    snaps = db.table("position_snapshots")
    instruments = db.table("instruments")
    prices = db.table("prices")
    fx = db.table("fx_rates")
    bsnaps = db.table("balance_snapshots")

    pf = portfolio.build(trades, snaps, instruments, prices, fx, today=today)
    days = None
    starts = [s for s in (pf.days.min() if len(pf.days) else None,
                          pd.to_datetime(raw_tx["date"]).min() if not raw_tx.empty else None,
                          pd.to_datetime(bsnaps["date"]).min() if not bsnaps.empty else None) if s is not None]
    if starts:
        days = pd.date_range(min(starts), pd.Timestamp(today or date.today()), freq="D")
    cash = networth.cash_balances(accounts, raw_tx, bsnaps, days)
    nw = networth.networth(accounts, cash, pf.accounts)

    cash_now = cash.sort_values("date").groupby("account_id").tail(1)[["account_id", "balance"]] if not cash.empty else cash
    inv_cash = pf.accounts.sort_values("date").groupby("account_id").tail(1)[["account_id", "cash"]] if not pf.accounts.empty else None
    allocation = alloc_mod.allocation(pf.current, cash_now, accounts, inv_cash)

    bench_t = config.settings()["benchmark"]["ticker"]
    b = prices[prices["symbol"] == bench_t]
    bench = b.assign(date=pd.to_datetime(b["date"])).set_index("date")["close"].sort_index() if not b.empty else pd.Series(dtype=float)

    return Bundle(accounts, tx, vacations, pf, cash, nw, allocation, instruments, snaps, bsnaps,
                  db.read("SELECT * FROM import_log ORDER BY ts DESC LIMIT 200"), bench, list(pf.warnings))


def export_excel(bundle: Bundle, path) -> None:
    with pd.ExcelWriter(path) as xw:
        if not bundle.portfolio.current.empty:
            bundle.portfolio.current.drop(columns=["exposure", "regions", "sectors"], errors="ignore").to_excel(
                xw, sheet_name="Positions", index=False)
        if not bundle.tx.empty:
            bundle.tx.drop(columns=["month"], errors="ignore").to_excel(xw, sheet_name="Opérations", index=False)
            budget.monthly_by_category(bundle.tx).to_excel(xw, sheet_name="Dépenses par mois")
            budget.monthly_flows(bundle.tx).to_excel(xw, sheet_name="Revenus et épargne")
        if not bundle.networth.empty:
            bundle.networth.pivot_table(index="date", columns="name", values="value", aggfunc="sum").to_excel(
                xw, sheet_name="Patrimoine")
        if not bundle.portfolio.realized.empty:
            bundle.portfolio.realized.to_excel(xw, sheet_name="PnL réalisé", index=False)
        for k, v in bundle.allocation.items():
            if not k.startswith("_"):
                v.to_excel(xw, sheet_name=k[:31].replace("/", "-"), index=False)
