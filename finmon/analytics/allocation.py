"""Répartition du patrimoine : classe d'actif, zone, devise, secteur, enveloppe."""
from __future__ import annotations

import json

import pandas as pd

ENVELOPE = {"courant": "Comptes courants", "livret": "Livrets", "pea": "PEA", "cto": "Compte-titres",
            "assurance_vie": "Assurance vie", "crypto": "Crypto", "epargne_salariale": "Épargne salariale", "autre": "Autres"}


def _explode(current: pd.DataFrame, col: str, label: str) -> pd.DataFrame:
    rows = []
    for r in current.itertuples():
        weights = json.loads(getattr(r, col) or "{}") if isinstance(getattr(r, col), str) else {}
        if not weights:
            weights = {"Non renseigné": 1.0}
        tot = sum(float(v) for v in weights.values()) or 1.0
        for k, w in weights.items():
            rows.append({label: k, "value": r.value * float(w) / tot})
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[label, "value"])


def allocation(current: pd.DataFrame, cash_now: pd.DataFrame, accounts: pd.DataFrame,
               invest_cash: pd.DataFrame | None = None, include_cash: bool = True) -> dict[str, pd.DataFrame]:
    """cash_now : account_id, balance (comptes courants / livrets) ;
    invest_cash : account_id, cash (liquidités dans les comptes-titres)."""
    cur = current.copy() if current is not None else pd.DataFrame()
    acc_type = accounts.set_index("id")["type"] if not accounts.empty else pd.Series(dtype=str)
    acc_inst = accounts.set_index("id")["institution"] if not accounts.empty else pd.Series(dtype=str)
    lines = []
    if not cur.empty:
        lines.append(cur[["account_id", "name", "value", "asset_class", "exposure", "regions", "sectors"]])
    cash_rows = []
    if include_cash:
        if cash_now is not None and not cash_now.empty:
            for r in cash_now.itertuples():
                t = acc_type.get(r.account_id, "courant")
                name, cls = {"livret": ("Livrets", "Épargne réglementée"),
                             "epargne_salariale": ("Épargne salariale", "Épargne salariale")}.get(
                    t, ("Comptes courants", "Liquidités"))
                cash_rows.append({"account_id": r.account_id, "name": name,
                                  "value": r.balance, "asset_class": cls,
                                  "exposure": '{"EUR": 1}', "regions": '{"Europe": 1}', "sectors": "{}"})
        if invest_cash is not None and not invest_cash.empty:
            for r in invest_cash.itertuples():
                if abs(r.cash) > 0.5:
                    cash_rows.append({"account_id": r.account_id, "name": "Liquidités (courtier)", "value": r.cash,
                                      "asset_class": "Liquidités", "exposure": '{"EUR": 1}',
                                      "regions": '{"Europe": 1}', "sectors": "{}"})
    if cash_rows:
        lines.append(pd.DataFrame(cash_rows))
    if not lines:
        return {}
    df = pd.concat(lines, ignore_index=True)
    df = df[df["value"] > 0]
    df["envelope"] = df["account_id"].map(acc_type).map(ENVELOPE).fillna("Autres")
    df["institution"] = df["account_id"].map(acc_inst).fillna("?")
    df["asset_class"] = df["asset_class"].fillna("Actions")

    out = {
        "Classe d'actif": df.groupby("asset_class")["value"].sum(),
        "Enveloppe": df.groupby("envelope")["value"].sum(),
        "Établissement": df.groupby("institution")["value"].sum(),
        "Zone géographique": _explode(df, "regions", "k").groupby("k")["value"].sum(),
        "Devise (sous-jacent)": _explode(df, "exposure", "k").groupby("k")["value"].sum(),
    }
    eq = df[df["asset_class"].isin(["Actions"])]
    if not eq.empty:
        out["Secteur (actions)"] = _explode(eq, "sectors", "k").groupby("k")["value"].sum()
    res = {}
    for k, s in out.items():
        s = s[s > 0.005].sort_values(ascending=False)
        res[k] = pd.DataFrame({"label": s.index, "value": s.values, "weight": s.values / s.sum()})
    res["_lines"] = df
    return res
