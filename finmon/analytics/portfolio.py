"""Moteur de portefeuille.

Pour chaque ligne (compte, ISIN) on suit jour par jour :

* ``qty``   — quantité détenue
* ``cost``  — prix de revient en EUR (méthode PMP, comme en France)
* ``units`` — prix de revient exprimé en « panier de devises » du sous-jacent
  (coût / F(date d'achat)), où F(t) est la valeur en EUR du panier défini
  par l'exposition devise du titre (ex. MSCI World ≈ 72 % USD).

Décomposition, exacte par construction :

    valeur / coût = (1 + r_sous_jacent) × (1 + r_change)
    r_change       = F(t) / (coût / units) − 1
    r_sous_jacent  = (valeur / F(t)) / units − 1

PnL sous-jacent = coût × r_sj, PnL change = coût × r_fx, effet croisé = le reste.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

BUY_LIKE = {"buy", "transfer_in", "reward"}
SELL_LIKE = {"sell", "transfer_out"}
FLOW_IN = {"deposit"}
FLOW_OUT = {"withdrawal"}


@dataclass
class PortfolioResult:
    days: pd.DatetimeIndex
    positions: pd.DataFrame          # long : date, account_id, isin, qty, cost, value, latent, local, fx, cross
    accounts: pd.DataFrame           # long : date, account_id, securities, cash, total, flow
    current: pd.DataFrame            # dernière photo des positions + métadonnées
    realized: pd.DataFrame           # par position : realized, r_local, r_fx, r_cross
    income: pd.DataFrame             # dividendes / intérêts / frais / impôts par date
    warnings: list[str] = field(default_factory=list)
    closed: pd.DataFrame = field(default_factory=pd.DataFrame)  # une ligne par vente / sortie : d'où vient le réalisé

    @property
    def empty(self) -> bool:
        return self.positions.empty and self.accounts.empty


# --------------------------------------------------------------------------
# Séries de marché
# --------------------------------------------------------------------------
def fx_matrix(fx: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """Unités de devise pour 1 EUR, une colonne par devise, jours calendaires."""
    if fx.empty:
        return pd.DataFrame(index=days)
    m = fx.assign(date=pd.to_datetime(fx["date"])).pivot_table(index="date", columns="currency", values="rate")
    return m.reindex(m.index.union(days)).sort_index().ffill().bfill().reindex(days)


def basket_index(exposure: dict, fxm: pd.DataFrame) -> pd.Series:
    """Valeur en EUR (base 1) du panier de devises du sous-jacent."""
    idx = pd.Series(0.0, index=fxm.index)
    total = 0.0
    for ccy, w in (exposure or {}).items():
        w = float(w)
        total += w
        ccy = ccy.upper()
        if ccy in fxm.columns and fxm[ccy].notna().any():
            r = fxm[ccy]
            idx += w * (r.iloc[0] / r)
        else:  # EUR, « AUTRE » ou devise sans données : pas d'effet change
            idx += w
    return idx / total if total else pd.Series(1.0, index=fxm.index)


def price_eur(inst: pd.Series | None, prices: pd.DataFrame, fxm: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    if inst is None or not isinstance(inst.get("ticker"), str):
        return pd.Series(np.nan, index=days)
    p = prices[prices["symbol"] == inst["ticker"]]
    if p.empty:
        return pd.Series(np.nan, index=days)
    s = p.assign(date=pd.to_datetime(p["date"])).set_index("date")["close"].sort_index()
    s = s[~s.index.duplicated()]
    s = s.reindex(s.index.union(days)).ffill().reindex(days)
    ccy = (inst.get("currency") or "EUR")
    if ccy in ("GBp", "GBX"):
        s, ccy = s / 100, "GBP"
    ccy = ccy.upper()
    if ccy != "EUR":
        if ccy not in fxm.columns:
            return pd.Series(np.nan, index=days)
        s = s / fxm[ccy]
    return s


# --------------------------------------------------------------------------
# Moteur
# --------------------------------------------------------------------------
def build(trades: pd.DataFrame, snapshots: pd.DataFrame, instruments: pd.DataFrame,
          prices: pd.DataFrame, fx: pd.DataFrame, today: date | None = None) -> PortfolioResult:
    warnings: list[str] = []
    today = pd.Timestamp(today or date.today())
    tr = trades.copy()
    tr["date"] = pd.to_datetime(tr["date"])
    sn = snapshots.copy()
    sn["date"] = pd.to_datetime(sn["date"])
    starts = [d.min() for d in (tr["date"], sn["date"]) if not d.empty]
    if not starts:
        empty = pd.DataFrame()
        return PortfolioResult(pd.DatetimeIndex([]), empty, empty, empty, empty, empty, warnings)
    days = pd.date_range(min(starts).normalize(), today.normalize(), freq="D")
    fxm = fx_matrix(fx, days)
    inst = instruments.set_index("isin") if not instruments.empty else pd.DataFrame()

    pos_frames, realized_rows, current_rows, closed_rows = [], [], [], []
    keys = pd.concat([tr.loc[tr["isin"].notna() & (tr["isin"] != ""), ["account_id", "isin"]],
                      sn[["account_id", "isin"]]]).drop_duplicates()

    for account_id, isin in keys.itertuples(index=False):
        meta = inst.loc[isin] if isin in inst.index else None
        exposure = json.loads(meta["exposure"]) if meta is not None and meta["exposure"] else {"EUR": 1.0}
        F = basket_index(exposure, fxm)
        ev = tr[(tr["account_id"] == account_id) & (tr["isin"] == isin)].sort_values("date")
        snap = sn[(sn["account_id"] == account_id) & (sn["isin"] == isin)].sort_values("date")
        name = (meta["name"] if meta is not None and meta["name"] else None) or \
            (ev["name"].dropna().iloc[-1] if not ev["name"].dropna().empty else (snap["name"].iloc[-1] if not snap.empty else isin))

        px = price_eur(meta, prices, fxm, days)
        px = _calibrate(px, ev, snap, name, warnings)

        # Événements + rapprochement avec les photos de portefeuille.
        events = [(r.date, r.kind, r.quantity or 0.0, r.amount) for r in ev.itertuples()]
        # Relevé complet du compte où la ligne n'apparaît plus : sortie (expirée, désactivée…).
        acc_snap_dates = set(sn.loc[sn["account_id"] == account_id, "date"].dt.normalize())
        own = set(snap["date"].dt.normalize())
        for d in sorted(acc_snap_dates - own):
            events.append((d, "gone", 0.0, None))
        qty_series = _apply(events, F, px, days, snap, warnings, name)
        q, C, L, realized = qty_series
        adj_flow = realized.pop("adj_flow")
        for c in realized.pop("closed"):
            closed_rows.append({"account_id": account_id, "isin": isin, "name": name, **c})
        V = q * px
        Fd = F.reindex(days)
        with np.errstate(divide="ignore", invalid="ignore"):
            r_tot = np.where(C > 0, V / C - 1, 0.0)
            r_fx = np.where(L > 0, Fd / (C / L) - 1, 0.0)
            r_loc = np.where(L > 0, (V / Fd) / L - 1, 0.0)
        frame = pd.DataFrame({
            "date": days, "account_id": account_id, "isin": isin, "name": name,
            "qty": q, "cost": C, "price": px.values, "value": V,
            "latent": V - C,
            "local": C * r_loc, "fx": C * r_fx, "adj_flow": adj_flow,
        })
        frame["cross"] = frame["latent"] - frame["local"] - frame["fx"]
        frame[["value", "latent", "local", "fx", "cross"]] = frame[["value", "latent", "local", "fx", "cross"]].fillna(0.0)
        frame = frame[(frame["qty"].abs() > 1e-9) | (frame["adj_flow"] != 0) | (frame["date"].isin(ev["date"].dt.normalize()))]
        pos_frames.append(frame)
        realized_rows.append({"account_id": account_id, "isin": isin, "name": name, **realized})

    positions = pd.concat(pos_frames, ignore_index=True) if pos_frames else pd.DataFrame()
    realized = pd.DataFrame(realized_rows)

    # ---------------- comptes : cash, flux, valeur totale ----------------
    accounts = _accounts(tr, positions, days)

    # ---------------- revenus / frais ----------------
    cols = ["date", "account_id", "kind", "isin", "name", "amount"]
    inc = tr[tr["kind"].isin(["dividend", "interest", "fee", "tax"])][cols]
    # Frais de courtage / impôts portés sur les ordres eux-mêmes (déjà dans le prix de revient).
    on_orders = []
    for col, kind in (("fees", "fee"), ("taxes", "tax")):
        if col in tr:
            o = tr[tr[col].fillna(0).abs() > 0]
            if not o.empty:
                on_orders.append(o.assign(kind=kind, amount=-o[col].abs())[cols])
    income = pd.concat([inc] + on_orders, ignore_index=True) if (not inc.empty or on_orders) else pd.DataFrame(columns=cols)

    # ---------------- photo courante ----------------
    if not positions.empty:
        last = positions[positions["date"] == days[-1]].copy()
        last = last[last["qty"].abs() > 1e-9]
        if not inst.empty:
            last = last.join(inst[["ticker", "currency", "asset_class", "region", "exposure", "regions", "sectors"]], on="isin")
        tot = last["value"].sum()
        last["weight"] = last["value"] / tot if tot else 0.0
        last["perf"] = np.where(last["cost"] > 0, last["latent"] / last["cost"], np.nan)
        last["pru"] = last["cost"] / last["qty"]
        current = last.sort_values("value", ascending=False).reset_index(drop=True)
    else:
        current = pd.DataFrame()
    return PortfolioResult(days, positions, accounts, current, realized, income, warnings, pd.DataFrame(closed_rows))


def _calibrate(px: pd.Series, ev: pd.DataFrame, snap: pd.DataFrame, name: str, warnings: list) -> pd.Series:
    """Complète/ajuste la série de prix avec les prix observés (ordres, photos)."""
    obs = []
    for r in ev.itertuples():
        if r.kind in ("buy", "sell") and r.quantity and r.amount:
            obs.append((r.date, abs(r.amount) / r.quantity))
    for r in snap.itertuples():
        if r.price and r.price == r.price:
            obs.append((r.date, r.price))
        elif r.value and r.quantity:
            obs.append((r.date, r.value / r.quantity))
    if not obs:
        return px
    o = pd.Series(dict(obs)).sort_index()
    o = o[~o.index.duplicated(keep="last")]
    if px.notna().sum() == 0:
        warnings.append(f"Pas de cours de marché pour « {name} » : valorisation avec les derniers prix connus (ordres/relevés).")
        s = o.reindex(o.index.union(px.index)).ffill().reindex(px.index)
        return s.bfill()
    m = px.reindex(o.index.normalize(), method="ffill")
    ratio = (o.values / m.values)
    ratio = ratio[np.isfinite(ratio)]
    if len(ratio):
        k = float(np.median(ratio))
        if k < 0.3 or k > 3.0:
            # Erreur d'unité manifeste (pence/livres, mauvaise cotation) : on recale la série.
            warnings.append(
                f"Le cours Yahoo de « {name} » est ×{k:.2f} vos prix d'exécution : série recalée. "
                f"Vérifiez le ticker (Données › Titres).")
            px = px * k
        elif not 0.85 <= k <= 1.15:
            warnings.append(
                f"« {name} » : vos prix d'exécution s'écartent de {abs(k - 1) * 100:.0f} % du cours Yahoo à ces dates. "
                f"Vérifiez le prix saisi ou le ticker (la valorisation utilise le cours Yahoo).")
    return px.bfill()


def _apply(events, F: pd.Series, px: pd.Series, days: pd.DatetimeIndex, snap: pd.DataFrame,
           warnings: list, name: str):
    """Rejoue les opérations jour par jour. Retourne q, C, L (arrays) et le réalisé."""
    snaps = {pd.Timestamp(r.date).normalize(): r for r in snap.itertuples()}
    by_day: dict = {}
    for d, kind, qty, amount in events:
        by_day.setdefault(pd.Timestamp(d).normalize(), []).append((kind, qty, amount))
    n = len(days)
    q_a, C_a, L_a, adj = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    q = C = L = 0.0
    real = {"realized": 0.0, "r_local": 0.0, "r_fx": 0.0, "r_cross": 0.0}
    closed: list[dict] = []
    Fv = F.reindex(days).values
    pxv = px.values
    reconciled = False
    oversold: list = []
    gone: list = []
    for i, d in enumerate(days):
        f = Fv[i] if np.isfinite(Fv[i]) and Fv[i] > 0 else 1.0
        for kind, qty, amount in by_day.get(d, []):
            if kind in BUY_LIKE and qty:
                cost = -amount if (amount is not None and amount == amount and amount < 0) else (
                    qty * pxv[i] if np.isfinite(pxv[i]) else 0.0)
                q, C, L = q + qty, C + cost, L + cost / f
            elif kind in SELL_LIKE and qty and q > 1e-12:
                frac = min(qty / q, 1.0)
                Cr, Lr = C * frac, L * frac
                if kind == "sell" and amount is not None and amount == amount:
                    proceeds = abs(amount)
                    if qty > q * (1 + 1e-9):  # vente > détention connue (historique incomplet)
                        proceeds *= q / qty
                        oversold.append(d)
                    real["realized"] += proceeds - Cr
                    rl = rf = 0.0
                    if Lr > 0:
                        rl = (proceeds / f) / Lr - 1
                        rf = f / (Cr / Lr) - 1
                        real["r_local"] += Cr * rl
                        real["r_fx"] += Cr * rf
                        real["r_cross"] += (proceeds - Cr) - Cr * rl - Cr * rf
                    closed.append({"date": d, "type": "Vente", "quantity": min(qty, q), "proceeds": proceeds,
                                   "cost": Cr, "pru": Cr / min(qty, q) if qty else None, "realized": proceeds - Cr,
                                   "r_local": Cr * rl, "r_fx": Cr * rf, "fee_only": proceeds == 0})
                if frac >= 1:
                    q, C, L = 0.0, 0.0, 0.0
                else:
                    q, C, L = q - qty, C - Cr, L - Lr
            if kind == "gone" and q > 1e-12:
                closed.append({"date": d, "type": "Sortie (absent du relevé)", "quantity": q, "proceeds": 0.0,
                               "cost": C, "pru": C / q, "realized": -C, "r_local": -C, "r_fx": 0.0, "fee_only": False})
                real["realized"] -= C
                real["r_local"] -= C
                gone.append(d)
                q, C, L = 0.0, 0.0, 0.0
        s = snaps.get(d)
        if s is not None and s.quantity is not None and s.quantity == s.quantity:
            diff = s.quantity - q
            if abs(diff) > 1e-6 * max(1.0, abs(s.quantity)):
                if diff > 0:
                    unit = s.avg_cost if (s.avg_cost and s.avg_cost == s.avg_cost) else (
                        pxv[i] if np.isfinite(pxv[i]) else (s.price or 0.0))
                    add = diff * unit
                    q, C, L = q + diff, C + add, L + add / f
                    adj[i] += add
                elif q > 0:
                    frac = min(-diff / q, 1.0)
                    adj[i] -= q * frac * (pxv[i] if np.isfinite(pxv[i]) else C / q)
                    q, C, L = q * (1 - frac), C * (1 - frac), L * (1 - frac)
                reconciled = True
            # Le PRU du relevé fait foi s'il est connu.
            if s.avg_cost and s.avg_cost == s.avg_cost and q > 0:
                newC = s.avg_cost * q
                if C > 0:
                    L *= newC / C
                else:
                    L = newC / f
                C = newC
        q_a[i], C_a[i], L_a[i] = q, C, L
    if reconciled:
        warnings.append(f"« {name} » : quantité recalée sur le relevé de portefeuille (opérations manquantes ou split).")
    if gone:
        warnings.append(f"« {name} » absent du relevé de portefeuille du {gone[0]:%d/%m/%Y} : considéré comme sorti "
                        f"(expiré, désactivé ou vendu hors historique) — perte comptée dans le réalisé.")
    if oversold:
        warnings.append(f"« {name} » : vente le {oversold[0]:%d/%m/%Y} supérieure à la quantité connue — il manque des "
                        f"achats/dépôts antérieurs ; seule la part connue est comptée dans la plus-value réalisée.")
    real["adj_flow"] = adj
    real["closed"] = closed
    return q_a, C_a, L_a, real


def _accounts(tr: pd.DataFrame, positions: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    frames = []
    acc_ids = sorted(set(tr["account_id"]) | (set(positions["account_id"]) if not positions.empty else set()))
    for acc in acc_ids:
        t = tr[tr["account_id"] == acc]
        sec = positions[positions["account_id"] == acc].groupby("date")["value"].sum() if not positions.empty else pd.Series(dtype=float)
        sec = sec.reindex(days).fillna(0.0)
        tracks_cash = t["kind"].isin(FLOW_IN).any()
        daily = t.assign(d=t["date"].dt.normalize())
        if tracks_cash:
            cash = daily.groupby("d")["amount"].sum().reindex(days).fillna(0.0).cumsum()
            flow = daily[daily["kind"].isin(FLOW_IN | FLOW_OUT)].groupby("d")["amount"].sum()
        else:
            cash = pd.Series(0.0, index=days)
            # Sans versements connus : l'argent investi = achats − ventes (+ frais).
            flow = -daily[daily["kind"].isin(BUY_LIKE | SELL_LIKE | {"fee", "tax"})].groupby("d")["amount"].sum()
        # Transferts de titres : flux à la valeur de marché.
        if not positions.empty:
            p = positions[positions["account_id"] == acc]
            for kind, sign in (("transfer_in", 1), ("transfer_out", -1)):
                for r in t[t["kind"] == kind].itertuples():
                    pr = p[(p["isin"] == r.isin) & (p["date"] == r.date.normalize())]["price"]
                    if not pr.empty and r.quantity:
                        flow = flow.add(pd.Series({r.date.normalize(): sign * r.quantity * float(pr.iloc[0])}), fill_value=0)
        flow = flow.reindex(days).fillna(0.0)
        if not positions.empty:
            # Quantités apparues/disparues au rapprochement avec un relevé : apport/retrait implicite.
            adj = positions[positions["account_id"] == acc].groupby("date")["adj_flow"].sum()
            flow = flow.add(adj.reindex(days).fillna(0.0), fill_value=0.0)
        frames.append(pd.DataFrame({"date": days, "account_id": acc, "securities": sec.values,
                                    "cash": cash.values, "flow": flow.values}))
    if not frames:
        return pd.DataFrame(columns=["date", "account_id", "securities", "cash", "flow", "total"])
    out = pd.concat(frames, ignore_index=True)
    out["total"] = out["securities"] + out["cash"]
    return out


# --------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------
def twr(total: pd.Series, flow: pd.Series) -> pd.Series:
    """Performance pondérée par le temps, base 100.

    Convention : les apports arrivent en début de journée, les retraits en fin
    de journée. Les jours où la base est nulle/négative (données incomplètes)
    ou le rendement aberrant (> ±50 %/jour) sont neutralisés.
    """
    prev = total.shift(1).fillna(0.0)
    base = prev + flow.clip(lower=0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(base > 1.0, (total - prev - flow) / base, 0.0)
    r = np.where(np.abs(r) > 0.5, 0.0, r)
    return 100 * pd.Series(1 + r, index=total.index).cumprod()


def xirr(flows: pd.Series, final_value: float, final_date: pd.Timestamp) -> float | None:
    """Taux de rendement interne annualisé (flux du point de vue de l'investisseur)."""
    f = flows[flows.abs() > 1e-9]
    if f.empty or final_value <= 0:
        return None
    cf = pd.concat([-f, pd.Series({final_date: final_value})])
    t = (cf.index - cf.index[0]).days / 365.25
    v = cf.values.astype(float)
    if t[-1] < 0.05:
        return None

    def npv(r):
        return np.sum(v / (1 + r) ** t)

    lo, hi = -0.99, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def summary(res: PortfolioResult, accounts: list[str] | None = None) -> dict:
    acc = res.accounts
    pos = res.positions
    if accounts is not None:
        acc = acc[acc["account_id"].isin(accounts)]
        pos = pos[pos["account_id"].isin(accounts)] if not pos.empty else pos
    if acc.empty:
        return {}
    g = acc.groupby("date")[["securities", "cash", "flow", "total"]].sum()
    last = g.index[-1]
    cur = pos[pos["date"] == last] if not pos.empty else pos
    real = res.realized
    if accounts is not None and not real.empty:
        real = real[real["account_id"].isin(accounts)]
    inc = res.income
    if accounts is not None and not inc.empty:
        inc = inc[inc["account_id"].isin(accounts)]
    tw = twr(g["total"], g["flow"])
    return {
        "value": float(g["total"].iloc[-1]),
        "securities": float(g["securities"].iloc[-1]),
        "cash": float(g["cash"].iloc[-1]),
        "net_invested": float(g["flow"].sum()),
        "cost": float(cur["cost"].sum()) if not cur.empty else 0.0,
        "latent": float(cur["latent"].sum()) if not cur.empty else 0.0,
        "latent_local": float(cur["local"].sum()) if not cur.empty else 0.0,
        "latent_fx": float(cur["fx"].sum()) if not cur.empty else 0.0,
        "latent_cross": float(cur["cross"].sum()) if not cur.empty else 0.0,
        "realized": float(real["realized"].sum()) if not real.empty else 0.0,
        "realized_local": float(real["r_local"].sum()) if not real.empty else 0.0,
        "realized_fx": float(real["r_fx"].sum()) if not real.empty else 0.0,
        "dividends": float(inc.loc[inc["kind"] == "dividend", "amount"].sum()) if not inc.empty else 0.0,
        "interest": float(inc.loc[inc["kind"] == "interest", "amount"].sum()) if not inc.empty else 0.0,
        "fees": float(inc.loc[inc["kind"].isin(["fee", "tax"]), "amount"].sum()) if not inc.empty else 0.0,
        "pnl_total": float(g["total"].iloc[-1] - g["flow"].sum()),
        "twr": float(tw.iloc[-1] / 100 - 1),
        "xirr": xirr(g["flow"], float(g["total"].iloc[-1]), last),
        "series": g.assign(twr=tw, invested=g["flow"].cumsum()),
    }
