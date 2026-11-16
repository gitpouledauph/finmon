"""Import de l'historique Binance. Deux exports sont reconnus (anglais ou français) :

1. **Historique des transactions** (relevé complet, le plus riche) :
   ``User_ID,UTC_Time,Account,Operation,Coin,Change,Remark`` — une ligne = un mouvement d'une
   crypto (ou de l'EUR) ; contient aussi dépôts, retraits, intérêts Earn, conversions.
2. **Historique des trades Spot** (Ordres › Historique des trades) :
   ``N° de commande,Durée,Paire,Côté,Prix,Exécuté,Montant,Frais`` (en anglais
   ``Date(UTC),Pair,Side,Price,Executed,Amount,Fee``) — uniquement les achats/ventes au comptant.
   Converti en mouvements puis traité comme le format 1.

Les stablecoins (USDC, USDT…) et l'EUR sont des **liquidités** : leur valeur EUR sert de montant
aux achats/ventes ; ils ne forment pas de position.

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
STABLE = {"USD", "USDC", "USDT", "FDUSD", "BUSD", "DAI", "TUSD", "USDP"}
CASH = FIAT | STABLE
QUOTES = sorted(CASH | {"BTC", "ETH", "BNB", "TRY", "BRL", "GBP"}, key=len, reverse=True)

INTERNAL = ("transferbetween", "subscription", "redemption", "savingspurchase", "savingsprincipal",
            "stakingpurchase", "posfee", "transferin", "transferout", "toaccount", "fromaccount",
            "mainandfunding", "fundingaccount", "isolatedmargin", "crossmargin", "locked", "unlock",
            "flexiblesubscription", "flexibleredemption", "autosubscribe")
REWARD = ("interest", "reward", "distribution", "airdrop", "cashback", "launchpool", "launchpad",
          "mining", "rebate", "bonus", "cryptobox", "giftcard", "voucher", "referral", "commission")
TRADE = ("buy", "sell", "transaction", "convert", "exchange", "otc", "autoinvest", "smallassets",
         "largeotc", "fiatpayment", "p2p", "trading")
FEE = ("fee",)


# Colonnes de l'« Historique des transactions » (anglais / français).
LEDGER_COLS = {
    "time": ("UTC_Time", "Durée", "Date", "Time", "Heure"),
    "op": ("Operation", "Opération"),
    "coin": ("Coin", "Jeton", "Monnaie", "Crypto"),
    "change": ("Change", "Changement", "Variation", "Montant"),
    "remark": ("Remark", "Remarque", "Note"),
}


def _col(df: pd.DataFrame, key: str) -> str | None:
    return pick(df, *LEDGER_COLS[key])


def detect(df: pd.DataFrame) -> bool:
    return bool(_col(df, "op") and _col(df, "coin") and pick(df, "Change", "Changement")) or detect_spot(df)


def detect_spot(df: pd.DataFrame) -> bool:
    return bool(pick(df, "Paire", "Pair") and pick(df, "Côté", "Side") and pick(df, "Exécuté", "Executed")
                and pick(df, "Montant", "Amount"))


_QTY_RE = re.compile(r"^\s*([-+]?[\d.,]+(?:[eE][-+]?\d+)?)\s*([A-Z0-9]*)\s*$")


def _qty(s: str) -> tuple[float | None, str]:
    """« 0.00100BTC » -> (0.001, "BTC")."""
    m = _QTY_RE.match(str(s).replace(" ", ""))
    if not m:
        return None, ""
    return float(m.group(1).replace(",", "")), m.group(2)


def spot_to_ledger(df: pd.DataFrame) -> pd.DataFrame:
    """Convertit l'historique des trades Spot en mouvements (format « transaction history »)."""
    c_time = pick(df, "Durée", "Date(UTC)", "Date", "Time", "Heure", "Date (UTC)")
    c_pair, c_side = pick(df, "Paire", "Pair"), pick(df, "Côté", "Side")
    c_exec, c_amt, c_fee = pick(df, "Exécuté", "Executed"), pick(df, "Montant", "Amount"), pick(df, "Frais", "Fee")
    rows = []
    for r in df.to_dict("records"):
        q, base = _qty(r[c_exec])
        a, quote = _qty(r[c_amt])
        if q is None or a is None:
            continue
        pair = str(r[c_pair]).upper()
        if not base:
            base = pair[: len(pair) - len(quote)] if quote and pair.endswith(quote) else pair
        if not quote:
            quote = next((x for x in QUOTES if pair.endswith(x) and pair != x), "")
            base = pair[: len(pair) - len(quote)]
        buy = str(r[c_side]).strip().upper() in ("BUY", "ACHAT", "ACHETER")
        t = r[c_time]
        rows.append([t, "Buy" if buy else "Sell", base, q if buy else -q])
        rows.append([t, "Buy" if buy else "Sell", quote, -a if buy else a])
        if c_fee:
            fq, fcoin = _qty(r[c_fee])
            if fq:
                rows.append([t, "Transaction Fee", fcoin or base, -abs(fq)])
    return pd.DataFrame(rows, columns=["UTC_Time", "Operation", "Coin", "Change"])


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
    spot = detect_spot(df) and not _col(df, "op")
    if spot:
        df = spot_to_ledger(df)
    n, warnings = import_ledger(db, df, source=name, online=online)
    if spot:
        warnings.append("Export « Historique des trades » : il ne contient ni dépôts, ni retraits, ni intérêts Earn. "
                        "Pour un suivi complet, importez aussi l'« Historique des transactions ».")
    db.log("binance", name, n, "ok", "; ".join(warnings[:5]))
    for w in warnings:
        db.log("binance", name, 0, "warning", w)
    return ("binance (trades spot)" if spot else "binance"), n


def _trade_groups(tr: pd.DataFrame) -> pd.Series:
    """Identifiant d'opération pour chaque ligne d'échange.

    - « Transaction Buy/Spend/Fee… » (ordres Spot) : les lignes d'une même seconde ;
    - « Buy Crypto With Fiat » : la référence en remarque (débit EUR et crédit crypto ont
      quelques secondes d'écart) ;
    - « Binance Convert » : les jambes à moins de 5 s d'intervalle (crypto et USDC peuvent
      être horodatées à une seconde d'écart).
    """
    op = tr["op"].map(norm)
    grp = pd.Series("t:" + tr["ts"].dt.floor("s").astype(str), index=tr.index)
    fiat = op.str.contains("withfiat") & (tr["remark"] != "")
    grp[fiat] = "f:" + tr.loc[fiat, "remark"]
    conv = op.str.contains("convert") & ~fiat
    if conv.any():
        t = tr.loc[conv, "ts"].sort_values()
        cluster = (t.diff() > pd.Timedelta(seconds=5)).cumsum()
        grp[t.index] = "c:" + cluster.astype(str)
    return grp


def _instrument(coin: str) -> str:
    return f"CRYPTO-{coin}"


def import_ledger(db: DB, df: pd.DataFrame, source: str = "", online: bool = True) -> tuple[int, list[str]]:
    db.upsert("accounts", pd.DataFrame([{"id": ACCOUNT_ID, "institution": "Binance", "name": "Binance",
                                         "type": "crypto", "currency": "EUR"}]), mode="ignore")
    c_rem = _col(df, "remark")
    led = pd.DataFrame({
        "ts": _dates(df[_col(df, "time")]),
        "op": df[_col(df, "op")].astype(str).str.strip(),
        "coin": df[_col(df, "coin")].astype(str).str.strip().str.upper(),
        "change": to_numbers(df[pick(df, "Change", "Changement", "Variation")]),
        "remark": df[c_rem].fillna("").astype(str).str.strip() if c_rem else "",
    }).dropna(subset=["ts", "change"])
    led = led[led["change"] != 0]
    led["kind"] = led["op"].map(_kind)
    warnings = []
    unk = sorted(set(led.loc[led["kind"] == "unknown", "op"]))
    if unk:
        warnings.append(f"Opérations Binance non reconnues (ignorées) : {unk}")

    coins = sorted(set(led["coin"]) - CASH)
    start = led["ts"].min().date()
    market.ensure_history(db, [f"{c}-USD" for c in coins], start, online)
    market.ensure_history(db, ["USD"], start, online, fx=True)

    def value(coin, qty, ts):
        if coin in FIAT:
            return abs(qty)
        if coin in STABLE:  # 1 stablecoin ≈ 1 USD
            r = market.fx_on(db, "USD", ts.normalize(), online=False)
            return abs(qty) / r if r else None
        return market.eur_value(db, f"{coin}-USD", "USD", abs(qty), ts.normalize(), online=False)

    def cash_eur(coin, qty, ts):
        v = value(coin, qty, ts)
        return None if v is None else (v if qty > 0 else -v)

    rows = []

    def add(ts, kind, coin, qty, amount, note):
        is_cash = coin in CASH
        rows.append({"date": ts, "kind": kind, "isin": None if is_cash else _instrument(coin),
                     "name": note if is_cash else coin, "quantity": None if is_cash else abs(qty),
                     "amount": amount, "note": note})

    for r in led[led["kind"].isin(["deposit", "withdraw", "reward"])].itertuples():
        if r.kind == "reward":
            if r.coin in CASH:
                add(r.ts, "interest", r.coin, 0, cash_eur(r.coin, r.change, r.ts), r.op)
            elif r.change > 0:
                add(r.ts, "reward", r.coin, r.change, 0.0, r.op)
            continue
        if r.coin in CASH:
            add(r.ts, "deposit" if r.change > 0 else "withdrawal", r.coin, 0, cash_eur(r.coin, r.change, r.ts), r.op)
        else:
            add(r.ts, "transfer_in" if r.change > 0 else "transfer_out", r.coin, r.change, None, r.op)

    # Opérations d'échange, regroupées par seconde.
    tr = led[led["kind"].isin(["trade", "fee"])].copy()
    for _, g in tr.groupby(_trade_groups(tr)):
        ts = g["ts"].min().floor("s")
        legs = g[g["kind"] == "trade"].groupby("coin")["change"].sum()
        legs = legs[legs.abs() > 1e-12]
        fees = g[g["kind"] == "fee"].groupby("coin")["change"].sum()
        cash_legs = legs[legs.index.isin(CASH)]
        cash_vals = [value(c, q, ts) for c, q in cash_legs.items()]
        eur = sum(v if q > 0 else -v for v, q in zip(cash_vals, cash_legs.values) if v is not None) \
            if cash_vals and all(v is not None for v in cash_vals) else 0.0
        pos = legs[(legs > 0) & ~legs.index.isin(CASH)]
        neg = legs[(legs < 0) & ~legs.index.isin(CASH)]
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
            pass  # échange entre liquidités (EUR <-> USDC) : sans effet sur le portefeuille
        for c, q in fees.items():
            if c in CASH:
                add(ts, "fee", c, 0, cash_eur(c, q, ts), "Frais Binance")
            elif q < 0:
                add(ts, "sell", c, q, 0.0, "Frais Binance")   # quantité perdue, sans produit

    if not rows:
        return 0, warnings
    out = pd.DataFrame(rows)
    for c in ("quantity", "amount"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["account_id"] = ACCOUNT_ID
    out["fees"], out["taxes"], out["source"] = 0.0, 0.0, source
    out["d"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["id"] = stable_ids(out.assign(ts=out["date"].astype(str), q=out["quantity"].round(10)),
                           ["ts", "kind", "isin", "q", "note"], "binance")
    n = db.upsert("trades", out[["id", "account_id", "d", "kind", "isin", "name", "quantity", "amount", "fees",
                                 "taxes", "source"]].rename(columns={"d": "date"}))
    # Ventes supérieures aux quantités connues : historique incomplet.
    sign = out["kind"].map({"buy": 1, "transfer_in": 1, "reward": 1, "sell": -1, "transfer_out": -1}).fillna(0)
    held = (out.assign(q=out["quantity"].fillna(0) * sign).sort_values("date")
            .groupby("isin")["q"].cumsum())
    short = out.loc[held[held < -1e-9].index].groupby("name")["date"].min()
    for coin, d in short.items():
        warnings.append(f"{coin} : vente supérieure aux achats connus le {pd.Timestamp(d):%d/%m/%Y} — "
                        f"il manque des achats ou dépôts plus anciens (importez un historique plus long, "
                        f"ou saisissez un « Transfert entrant » / un achat initial).")
    missing = out[out["amount"].isna() & out["kind"].isin(["buy", "sell"])]
    if not missing.empty:
        warnings.append(f"{len(missing)} échanges sans valeur EUR (cours introuvable) : prix de revient estimé au cours du marché.")
    return n, warnings
