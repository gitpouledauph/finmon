"""Soldes des comptes bancaires et patrimoine global."""
from __future__ import annotations

from datetime import date

import pandas as pd

CASH_TYPES = {"courant", "livret", "autre"}
BUCKET = {"courant": "Liquidités", "livret": "Épargne réglementée", "autre": "Autres actifs",
          "pea": "Investissements", "cto": "Investissements", "assurance_vie": "Investissements",
          "crypto": "Investissements"}


def cash_balances(accounts: pd.DataFrame, tx: pd.DataFrame, snaps: pd.DataFrame,
                  days: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Solde quotidien des comptes courants/livrets.

    Le solde est ancré sur le dernier solde connu (export Boursorama ou saisie
    manuelle) et reconstitué à rebours avec les opérations.
    """
    acc = accounts[accounts["type"].isin(CASH_TYPES)]
    if acc.empty:
        return pd.DataFrame(columns=["date", "account_id", "balance"])
    tx = tx.assign(date=pd.to_datetime(tx["date"]))
    snaps = snaps.assign(date=pd.to_datetime(snaps["date"]))
    starts = [d.min() for d in (tx[tx["account_id"].isin(acc["id"])]["date"],
                                snaps[snaps["account_id"].isin(acc["id"])]["date"]) if not d.empty]
    if not starts:
        return pd.DataFrame(columns=["date", "account_id", "balance"])
    if days is None:
        days = pd.date_range(min(starts), pd.Timestamp(date.today()), freq="D")
    frames = []
    for a in acc["id"]:
        t = tx[tx["account_id"] == a]
        s = snaps[snaps["account_id"] == a].sort_values("date")
        if t.empty and s.empty:
            continue
        if not t.empty:
            cum = t.groupby(t["date"].dt.normalize())["amount"].sum().reindex(days).fillna(0.0).cumsum()
            if not s.empty:
                anchor = s.iloc[-1]
                offset = anchor["balance"] - cum.asof(anchor["date"])
            else:
                offset = 0.0
            bal = cum + offset
            first = t["date"].min().normalize()
            bal = bal.where(bal.index >= min(first, s["date"].min() if not s.empty else first))
        else:  # livret saisi à la main : soldes en escalier
            bal = s.set_index("date")["balance"]
            bal = bal[~bal.index.duplicated(keep="last")]
            bal = bal.reindex(bal.index.union(days)).ffill().reindex(days)
        frames.append(pd.DataFrame({"date": days, "account_id": a, "balance": bal.values}))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "account_id", "balance"])
    return out.dropna(subset=["balance"])


def networth(accounts: pd.DataFrame, cash: pd.DataFrame, invest: pd.DataFrame) -> pd.DataFrame:
    """Patrimoine quotidien par compte : date, account_id, name, type, bucket, value."""
    parts = []
    if not cash.empty:
        parts.append(cash.rename(columns={"balance": "value"})[["date", "account_id", "value"]])
    if invest is not None and not invest.empty:
        parts.append(invest.rename(columns={"total": "value"})[["date", "account_id", "value"]])
    if not parts:
        return pd.DataFrame(columns=["date", "account_id", "value", "name", "type", "bucket"])
    nw = pd.concat(parts, ignore_index=True)
    nw["date"] = pd.to_datetime(nw["date"])
    # On ne garde que la période où toutes les séries existent pour un cumul honnête.
    nw = nw.merge(accounts.rename(columns={"id": "account_id"})[["account_id", "name", "type", "institution"]],
                  on="account_id", how="left")
    nw["bucket"] = nw["type"].map(BUCKET).fillna("Autres actifs")
    return nw
