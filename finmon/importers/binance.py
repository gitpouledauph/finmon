"""Import de l'historique Binance (« Transaction History » / relevé complet).

Format : User_ID,UTC_Time,Account,Operation,Coin,Change,Remark
Une ligne = un mouvement d'une crypto (ou de l'EUR) sur un sous-compte.

Règles :
* EUR déposé / retiré           -> versement / retrait (flux du compte)
* crypto déposée / retirée      -> transfert entrant / sortant valorisé au cours du jour
* achats, ventes, conversions   -> regroupés par horodatage : les jambes positives sont des
  achats, les négatives des ventes ; le montant EUR vient de la jambe EUR si elle existe,
  sinon du cours du jour de ce qui est reçu
* intérêts, staking, airdrops   -> « reward » (gain, sans apport)
* mouvements entre sous-comptes -> ignorés
"""
from __future__ import annotations

import re

import pandas as pd

from .. import market
from ..db import DB
from ..parsing import norm, pick, read_csv_auto, stable_ids, to_numbers

ACCOUNT_ID = "binance"
FIAT = {"EUR"}

INTERNAL = ("transferbetween", "subscription", "redemption", "savingspurchase", "savingsprincipal",
            "stakingpurchase", "posfee", "transferin", "transferout", "toaccount", "fromaccount",
            "mainandfunding", "fundingaccount", "isolatedmargin", "crossmargin", "locked", "unlock",
            "flexiblesubscription", "flexibleredemption", "autosubscribe")
REWARD = ("interest", "reward", "distribution", "airdrop", "cashback", "launchpool", "launchpad",
          "mining", "rebate", "bonus", "cryptobox", "giftcard", "voucher", "referral", "commission")
TRADE = ("buy", "sell", "transaction", "convert", "exchange", "otc", "autoinvest", "smallassets",
         "largeotc", "fiatpayment", "p2p", "trading")
FEE = ("fee",)


def detect(df: pd.DataFrame) -> bool:
    return all(pick(df, c) for c in ("UTC_Time", "Operation", "Coin", "Change"))


def _kind(op: str) -> str:
    n = norm(op)
    if n in ("deposit", "fiatdeposit", "cryptodeposit") or (n.startswith("deposit") and "fee" not in n):
        return "deposit"
    if n.startswith("withdraw") or n in ("fiatwithdraw", "cryptowithdraw"):
        return "withdraw"
    if any(k in n for k in INTERNAL):
        return "internal"
    if n.endswith("fee") or n.endswith("fees"):
        return "fee"
    if any(k in n for k in REWARD):
        return "reward"
    if any(k in n for k in FEE) and "transaction" not in n:
        return "fee"
    if any(k in n for k in TRADE):
        return "trade"
    if "fee" in n:
        return "fee"
    return "unknown"


def _dates(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.where(~s.str.match(r"^\d{2}-\d{2}-\d{2}"), "20" + s)   # format court « 23-01-15 10:00:00 »
    return pd.to_datetime(s, errors="coerce")


def import_file(db: DB, path, online: bool = True) -> tuple[str, int]:
    df = read_csv_auto(path)
    name = getattr(path, "name", str(path))
    n, warnings = import_ledger(db, df, source=name, online=online)
    db.log("binance", name, n, "ok", "; ".join(warnings[:5]))
    for w in warnings:
        db.log("binance", name, 0, "warning", w)
    return "binance", n


def _instrument(coin: str) -> str:
    return f"CRYPTO-{coin}"


def import_ledger(db: DB, df: pd.DataFrame, source: str = "", online: bool = True) -> tuple[int, list[str]]:
    db.upsert("accounts", pd.DataFrame([{"id": ACCOUNT_ID, "institution": "Binance", "name": "Binance",
                                         "type": "crypto", "currency": "EUR"}]), mode="ignore")
    led = pd.DataFrame({
        "ts": _dates(df[pick(df, "UTC_Time")]),
        "op": df[pick(df, "Operation")].astype(str).str.strip(),
        "coin": df[pick(df, "Coin")].astype(str).str.strip().str.upper(),
        "change": to_numbers(df[pick(df, "Change")]),
    }).dropna(subset=["ts", "change"])
    led = led[led["change"] != 0]
    led["kind"] = led["op"].map(_kind)
    warnings = []
    unk = sorted(set(led.loc[led["kind"] == "unknown", "op"]))
    if unk:
        warnings.append(f"Opérations Binance non reconnues (ignorées) : {unk}")

    coins = sorted(set(led["coin"]) - FIAT)
    start = led["ts"].min().date()
    market.ensure_history(db, [f"{c}-USD" for c in coins], start, online)
    market.ensure_history(db, ["USD"], start, online, fx=True)

    def value(coin, qty, ts):
        if coin in FIAT:
            return abs(qty)
        return market.eur_value(db, f"{coin}-USD", "USD", abs(qty), ts.normalize(), online=False)

    rows = []

    def add(ts, kind, coin, qty, amount, note):
        rows.append({"date": ts, "kind": kind, "isin": None if coin in FIAT else _instrument(coin),
                     "name": coin if coin not in FIAT else note, "quantity": abs(qty) if coin not in FIAT else None,
                     "amount": amount, "note": note})

    for r in led[led["kind"].isin(["deposit", "withdraw", "reward"])].itertuples():
        if r.kind == "reward":
            if r.coin in FIAT:
                add(r.ts, "interest", r.coin, 0, r.change, r.op)
            elif r.change > 0:
                add(r.ts, "reward", r.coin, r.change, 0.0, r.op)
            continue
        if r.coin in FIAT:
            add(r.ts, "deposit" if r.kind == "deposit" else "withdrawal", r.coin, 0, r.change, r.op)
        else:
            add(r.ts, "transfer_in" if r.change > 0 else "transfer_out", r.coin, r.change, None, r.op)

    # Opérations d'échange, regroupées par seconde.
    tr = led[led["kind"].isin(["trade", "fee"])].copy()
    for ts, g in tr.groupby(tr["ts"].dt.floor("s")):
        legs = g[g["kind"] == "trade"].groupby("coin")["change"].sum()
        legs = legs[legs.abs() > 1e-12]
        fees = g[g["kind"] == "fee"].groupby("coin")["change"].sum()
        eur = float(legs.get("EUR", 0.0))
        pos = legs[(legs > 0) & ~legs.index.isin(FIAT)]
        neg = legs[(legs < 0) & ~legs.index.isin(FIAT)]
        if abs(eur) > 0:
            total = abs(eur)
        else:
            vals = [value(c, q, ts) for c, q in pos.items()] or [value(c, q, ts) for c, q in neg.items()]
            total = sum(v for v in vals if v is not None) if vals and all(v is not None for v in vals) else None
        for side, legs_, sign in (("buy", pos, -1), ("sell", neg, 1)):
            if legs_.empty:
                continue
            vals = {c: value(c, q, ts) for c, q in legs_.items()}
            known = sum(v for v in vals.values() if v) or None
            for c, q in legs_.items():
                share = (vals[c] / known) if (known and vals[c]) else 1 / len(legs_)
                amt = sign * total * share if total is not None else None
                add(ts, side, c, q, amt, "Binance " + ", ".join(sorted(set(g["op"]))))
        if pos.empty and neg.empty and abs(eur) > 0:
            warnings.append(f"{ts} : mouvement EUR isolé {eur:+.2f} (opération {sorted(set(g['op']))})")
        for c, q in fees.items():
            if c in FIAT:
                add(ts, "fee", c, 0, q, "Frais Binance")
            elif q < 0:
                add(ts, "sell", c, q, 0.0, "Frais Binance")   # quantité perdue, sans produit

    if not rows:
        return 0, warnings
    out = pd.DataFrame(rows)
    out["account_id"] = ACCOUNT_ID
    out["fees"], out["taxes"], out["source"] = 0.0, 0.0, source
    out["d"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["id"] = stable_ids(out.assign(ts=out["date"].astype(str), q=out["quantity"].round(10)),
                           ["ts", "kind", "isin", "q", "note"], "binance")
    n = db.upsert("trades", out[["id", "account_id", "d", "kind", "isin", "name", "quantity", "amount", "fees",
                                 "taxes", "source"]].rename(columns={"d": "date"}))
    missing = out[out["amount"].isna() & out["kind"].isin(["buy", "sell"])]
    if not missing.empty:
        warnings.append(f"{len(missing)} échanges sans valeur EUR (cours introuvable) : prix de revient estimé au cours du marché.")
    return n, warnings
