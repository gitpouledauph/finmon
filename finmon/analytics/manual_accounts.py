"""Investment accounts valued by hand (employee savings plan, etc.).

The user enters two things: contributions (amount invested, dated) and the current value
(dated snapshots, kept until overridden). These accounts are merged into the portfolio result so
they appear in performance, allocation and net worth like any broker account:
- value(t) = last entered value, or cumulative contributions before the first valuation;
- flow(t) = contributions of the day; gain = value − contributions.
"""
from __future__ import annotations

import pandas as pd

MANUAL_TYPES = {"epargne_salariale"}


def build(accounts: pd.DataFrame, snaps: pd.DataFrame, contribs: pd.DataFrame, days: pd.DatetimeIndex,
          today: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (account frames, position frames, current rows) for manually valued accounts."""
    acc = accounts[accounts["type"].isin(MANUAL_TYPES)]
    empty = pd.DataFrame()
    if acc.empty:
        return empty, empty, empty
    snaps = snaps.assign(date=pd.to_datetime(snaps["date"])) if not snaps.empty else snaps
    contribs = contribs.assign(date=pd.to_datetime(contribs["date"])) if not contribs.empty else contribs
    frames, pos, cur = [], [], []
    for a in acc.itertuples():
        s = snaps[snaps["account_id"] == a.id].sort_values("date") if not snaps.empty else snaps
        c = contribs[contribs["account_id"] == a.id] if not contribs.empty else contribs
        if s.empty and c.empty:
            continue
        if c.empty:   # no contribution entered yet: the first value counts as paid in (gain 0 until known)
            c = pd.DataFrame({"account_id": [a.id], "date": [s["date"].iloc[0]], "amount": [float(s["balance"].iloc[0])]})
        starts = [x for x in (s["date"].min() if not s.empty else None, c["date"].min() if not c.empty else None) if x is not None]
        rng = pd.date_range(min(min(starts).normalize(), days.min() if len(days) else min(starts)), today.normalize(), freq="D")
        flow = (c.groupby(c["date"].dt.normalize())["amount"].sum().reindex(rng).fillna(0.0)
                if not c.empty else pd.Series(0.0, index=rng))
        invested = flow.cumsum()
        val = pd.Series(float("nan"), index=rng)
        if not s.empty:
            v = s.groupby(s["date"].dt.normalize())["balance"].last()
            val.loc[v.index.intersection(rng)] = v
        # Before the first valuation the account is worth what was paid in; afterwards the last value
        # holds, shifted by later contributions until a new value is entered.
        out, last_v, last_inv = [], None, 0.0
        for d in rng:
            if val[d] == val[d]:
                last_v, last_inv = float(val[d]), float(invested[d])
            out.append(float(invested[d]) if last_v is None else last_v + (float(invested[d]) - last_inv))
        value = pd.Series(out, index=rng)
        live = (value.abs() > 0) | (invested.abs() > 0)
        frames.append(pd.DataFrame({"date": rng, "account_id": a.id, "securities": value.values, "cash": 0.0,
                                    "total": value.values, "flow": flow.values})[live.values])
        isin = f"MANUAL:{a.id}"
        pos.append(pd.DataFrame({"date": rng, "account_id": a.id, "isin": isin, "qty": 1.0, "cost": invested.values,
                                 "value": value.values, "latent": (value - invested).values,
                                 "local": (value - invested).values, "fx": 0.0, "cross": 0.0, "adj_flow": 0.0})[live.values])
        v_now, i_now = float(value.iloc[-1]), float(invested.iloc[-1])
        cur.append({"date": rng[-1], "account_id": a.id, "isin": isin, "name": a.name, "qty": 1.0, "cost": i_now,
                    "price": v_now, "value": v_now, "latent": v_now - i_now, "local": v_now - i_now, "fx": 0.0,
                    "cross": 0.0, "adj_flow": 0.0, "ticker": None, "currency": "EUR",
                    "asset_class": "Épargne salariale", "region": "Non renseigné",
                    "exposure": '{"EUR": 1}', "regions": '{"Non renseigné": 1}', "sectors": "{}",
                    "perf": (v_now / i_now - 1) if i_now > 0 else None, "pru": i_now})
    if not frames:
        return empty, empty, empty
    return pd.concat(frames, ignore_index=True), pd.concat(pos, ignore_index=True), pd.DataFrame(cur)
