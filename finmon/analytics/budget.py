"""Classement des opérations bancaires, budget mensuel/annuel, vacances."""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np
import pandas as pd

from .. import config
from ..parsing import norm


def _compiled_rules() -> list[tuple[re.Pattern, str, str | None]]:
    rules = config.categories().get("rules") or []
    return _compile(tuple((r["pattern"], r["category"], r.get("sign")) for r in rules))


@lru_cache(maxsize=8)
def _compile(rules: tuple) -> list[tuple[re.Pattern, str, str | None]]:
    """Règle = motif sur le libellé, catégorie, et facultativement « sign: debit | credit »."""
    return [(re.compile(p, re.I), c, s) for p, c, s in rules]


_compiled_rules.cache_clear = _compile.cache_clear  # compat : common.invalidate()


def category_types() -> dict[str, str]:
    cats = config.categories().get("categories") or {}
    return {k: (v or {}).get("type", "expense") for k, v in cats.items()}


def _from_bank(parent: str | None, cat: str | None) -> str | None:
    mapping = config.categories().get("bank_mapping") or {}
    text = norm(f"{cat or ''} {parent or ''}")
    # les mots-clés les plus longs d'abord (« frais bancaires » avant « frais »)
    for key in sorted(mapping, key=len, reverse=True):
        if norm(key) and norm(key) in text:
            return mapping[key]
    return None


SAVINGS_TYPES = {"livret", "pea", "cto", "assurance_vie"}
INTEREST_RE = re.compile(r"INTERETS|INTERESTS?|REMUNERATION", re.I)


def classify(tx: pd.DataFrame, overrides: pd.DataFrame | None = None,
             account_types: dict[str, str] | None = None) -> pd.DataFrame:
    """Ajoute category, cat_type, source_cat (override | règle | banque | défaut | compte).

    Sur un livret, tout est mouvement interne sauf les intérêts : le budget
    se lit sur les comptes courants (et la carte Trade Republic).
    """
    df = tx.copy()
    account_types = account_types or {}
    if df.empty:
        for c in ("category", "cat_type", "source_cat", "vacation_tag"):
            df[c] = pd.Series(dtype="object")
        return df
    rules = _compiled_rules()
    cats, srcs = [], []
    for acc, label, merchant, parent, cat, amount in zip(
        df["account_id"], df["label"], df["merchant"].fillna(""), df["bank_category_parent"], df["bank_category"], df["amount"]
    ):
        text = f"{label} {merchant}"
        if account_types.get(acc) == "livret":
            cats.append("Autres revenus" if INTEREST_RE.search(text) and amount > 0 else "Virements internes")
            srcs.append("compte")
            continue
        found = next((c for p, c, sg in rules if p.search(text)
                      and (sg is None or (sg == "debit") == (amount < 0))), None)
        if found:
            cats.append(found)
            srcs.append("règle")
            continue
        found = _from_bank(parent, cat)
        if found:
            cats.append(found)
            srcs.append("banque")
            continue
        cats.append("Autres revenus" if amount > 0 else "Autres dépenses")   # source « défaut » : à vérifier
        srcs.append("défaut")
    df["category"] = cats
    df["source_cat"] = srcs
    df["vacation_tag"] = None
    if overrides is not None and not overrides.empty:
        ov = overrides.set_index("tx_id")
        m = df["id"].isin(ov.index)
        ocat = df.loc[m, "id"].map(ov["category"])
        has = ocat.notna() & (ocat != "")
        df.loc[ocat[has].index, "category"] = ocat[has]
        df.loc[ocat[has].index, "source_cat"] = "manuel"
        df.loc[m, "vacation_tag"] = df.loc[m, "id"].map(ov["vacation"])
        if "factor" in ov.columns:
            fac = pd.to_numeric(df.loc[m, "id"].map(ov["factor"]), errors="coerce")
            fac = fac[fac.notna() & (fac != 1)]
            df["factor"] = 1.0
            df.loc[fac.index, "factor"] = fac
            df["amount_full"] = df["amount"]
            df.loc[fac.index, "amount"] = df.loc[fac.index, "amount"] * fac
    if "factor" not in df.columns:
        df["factor"] = 1.0
        df["amount_full"] = df["amount"]
    types = category_types()
    df["cat_type"] = df["category"].map(types).fillna("expense")
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    # Loyers payés/reçus en fin de mois pour le mois suivant : rattachés au mois couvert.
    cutoff = int(config.settings().get("logement_mois_suivant_apres", 25) or 0)
    if cutoff:
        late = df["category"].str.contains("Logement|Loyer", na=False) & (df["date"].dt.day >= cutoff) \
            & (df["amount"].abs() >= 300)   # loyers, pas les petites charges
        df.loc[late, "month"] = df.loc[late, "month"] + pd.DateOffset(months=1)
    df["year"] = df["date"].dt.year
    return df


def expenses(df: pd.DataFrame) -> pd.DataFrame:
    """Dépenses positives (remboursements déduits)."""
    e = df[df["cat_type"] == "expense"].copy()
    e["spend"] = -e["amount"]
    return e


def monthly_by_category(df: pd.DataFrame) -> pd.DataFrame:
    e = expenses(df)
    return e.pivot_table(index="month", columns="category", values="spend", aggfunc="sum", fill_value=0.0).sort_index()


def monthly_flows(df: pd.DataFrame) -> pd.DataFrame:
    """Revenus, dépenses, épargne et taux d'épargne par mois."""
    if df.empty:
        return pd.DataFrame(columns=["income", "expenses", "savings", "rate"], dtype=float,
                            index=pd.DatetimeIndex([], name="month"))
    inc = df[df["cat_type"] == "income"].groupby("month")["amount"].sum()
    exp = expenses(df).groupby("month")["spend"].sum()
    out = pd.DataFrame({"income": inc, "expenses": exp}).fillna(0.0).sort_index()
    out["savings"] = out["income"] - out["expenses"]
    out["rate"] = np.where(out["income"] > 0, out["savings"] / out["income"], np.nan)
    return out


# --------------------------------------------------------------------------
# Vacances
# --------------------------------------------------------------------------
def vacation_spend(df: pd.DataFrame, vacations: pd.DataFrame) -> pd.DataFrame:
    """Rattache les dépenses aux périodes de vacances.

    Une dépense compte pour un voyage si elle est taguée manuellement, ou si elle
    tombe dans la période (hors catégories fixes : loyer, abonnements...).
    """
    e = expenses(df)
    e["vacation"] = e["vacation_tag"].where(e["vacation_tag"].notna() & (e["vacation_tag"] != ""))
    excluded = set(config.settings().get("vacation_excluded_categories") or [])
    for v in vacations.itertuples():
        start, end = pd.Timestamp(v.start), pd.Timestamp(v.end)
        m = e["vacation"].isna() & e["date"].between(start, end) & ~e["category"].isin(excluded)
        e.loc[m, "vacation"] = v.name
    return e[e["vacation"].notna()]


def suggest_vacations(df: pd.DataFrame, known: pd.DataFrame, gap_days: int = 3, min_ops: int = 3) -> pd.DataFrame:
    """Repère des séjours probables : paiements en devise étrangère ou
    dépenses « Voyages » rapprochées dans le temps."""
    e = expenses(df)
    signal = e[e["foreign_currency"].notna() | e["label"].str.contains(r"HORS ZONE EURO|1 EURO =", case=False, regex=True)]
    signal = signal.sort_values("date")
    if signal.empty:
        return pd.DataFrame(columns=["name", "start", "end", "ops", "total", "devises"])
    grp = (signal["date"].diff().dt.days.fillna(999) > gap_days).cumsum()
    rows = []
    for _, g in signal.groupby(grp):
        if len(g) < min_ops:
            continue
        start, end = g["date"].min(), g["date"].max()
        overlap = any(pd.Timestamp(v.start) <= end and pd.Timestamp(v.end) >= start for v in known.itertuples())
        if overlap:
            continue
        ccys = ", ".join(sorted(set(g["foreign_currency"].dropna()))) or "?"
        rows.append({"name": f"Séjour {start:%b %Y} ({ccys})", "start": start.date(), "end": end.date(),
                     "ops": len(g), "total": float(g["spend"].sum()), "devises": ccys})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Virements vers les comptes d'investissement
# --------------------------------------------------------------------------
INVEST_TYPES = {"pea", "cto", "crypto", "assurance_vie", "epargne_salariale"}
LINKABLE = {"Virements internes", "Épargne & investissement"}


def link_investments(tx: pd.DataFrame, trades: pd.DataFrame, accounts: pd.DataFrame,
                     max_days: int = 7, early_days: int = 3) -> pd.DataFrame:
    """Rapproche les virements bancaires des versements/retraits connus sur les courtiers.

    Un débit bancaire de X € suivi (jusqu'à `max_days` jours après, ou `early_days` avant : le courtier
    date parfois la réception avant l'écriture bancaire) d'un versement de X € (±1 %)
    sur un compte d'investissement devient « Épargne & investissement », avec le compte destinataire
    dans `linked_account`. Même logique pour un retrait du courtier crédité sur la banque.
    Les corrections manuelles ne sont jamais modifiées.
    """
    df = tx.copy()
    df["linked_account"] = None
    if df.empty or trades.empty:
        return df
    inv = set(accounts.loc[accounts["type"].isin(INVEST_TYPES), "id"])
    moves = trades[trades["account_id"].isin(inv) & trades["kind"].isin(["deposit", "withdrawal"])].copy()
    if moves.empty:
        return df
    moves["date"] = pd.to_datetime(moves["date"])
    names = accounts.set_index("id")["name"].to_dict()
    used: set = set()
    cand = df[(df["category"].isin(LINKABLE) | (df["source_cat"] == "défaut"))
              & (df["source_cat"] != "manuel")].sort_values("date")
    for i, r in cand.iterrows():
        want = "deposit" if r["amount"] < 0 else "withdrawal"
        m = moves[(moves["kind"] == want) & ~moves["id"].isin(used)]
        delta = (m["date"] - r["date"]).dt.days if want == "deposit" else (r["date"] - m["date"]).dt.days
        tol = max(1.5, abs(r["amount"]) * 0.01)
        hit = m[(delta >= -early_days) & (delta <= max_days) & ((m["amount"].abs() - abs(r["amount"])).abs() <= tol)]
        if hit.empty:
            continue
        # Priorité au courtier nommé dans le libellé (« VIR INST IBKR »), puis au plus proche dans le temps.
        label = norm(f"{r['label']} {r.get('merchant', '')}")
        named = hit["account_id"].map(lambda a: any(norm(w) in label for w in _aliases(a, names, accounts)))
        gap = (hit["date"] - r["date"]).dt.days.abs()
        best = hit.loc[(gap - named.astype(int) * 100).idxmin()]
        used.add(best["id"])
        df.at[i, "category"] = "Épargne & investissement"
        df.at[i, "cat_type"] = "transfer"
        df.at[i, "source_cat"] = "rapprochement"
        df.at[i, "linked_account"] = names.get(best["account_id"], best["account_id"])
    return df


ALIASES = {"interactive brokers": ["ibkr", "interactive"], "trade republic": ["trade republic", "traderepublic"],
           "binance": ["binance"], "boursorama": ["boursorama", "boursobank"]}


def _aliases(account_id: str, names: dict, accounts: pd.DataFrame) -> list[str]:
    inst = accounts.set_index("id")["institution"].get(account_id, "") or ""
    base = [w for w in (names.get(account_id, ""), inst) if w and len(w) > 3]
    return base + ALIASES.get(str(inst).lower(), [])


# --------------------------------------------------------------------------
# Loyer fixe (colocation)
# --------------------------------------------------------------------------
def add_fixed_rent(tx: pd.DataFrame, accounts: pd.DataFrame, until=None) -> pd.DataFrame:
    """Ajoute « ma part du loyer » le 1er de chaque mois, selon `loyer_fixe` des règles du profil.

    Les flux réels (loyer versé, parts reçues des colocataires) sont classés hors budget ; cette ligne
    les remplace dans les dépenses. Barème : liste de {depuis: "AAAA-MM", montant: X}."""
    plan = config.categories().get("loyer_fixe") or []
    if not plan or tx.empty:
        return tx
    plan = sorted(({"start": pd.Timestamp(str(p["depuis"]) + "-01" if len(str(p["depuis"])) == 7 else str(p["depuis"])),
                    "amount": float(p["montant"])} for p in plan), key=lambda p: p["start"])
    end = pd.Timestamp(until) if until is not None else tx["date"].max()
    courant = accounts.loc[accounts["type"] == "courant", "id"]
    acc = (tx[tx["account_id"].isin(courant)]["account_id"].mode().iloc[0]
           if tx["account_id"].isin(courant).any() else tx["account_id"].iloc[0])
    rows = []
    for m in pd.date_range(plan[0]["start"], end, freq="MS"):
        amount = [p["amount"] for p in plan if p["start"] <= m][-1]
        rows.append({"id": f"loyer-fixe-{m:%Y-%m}", "account_id": acc, "date": m, "value_date": m,
                     "label": "Loyer — ma part (colocation)", "merchant": "LOYER (MA PART)", "amount": -amount,
                     "bank_category": None, "bank_category_parent": None, "foreign_currency": None,
                     "source": "loyer_fixe", "category": "Loyer", "source_cat": "loyer fixe",
                     "vacation_tag": None, "cat_type": "expense", "month": m, "year": m.year,
                     "linked_account": None})
    extra = pd.DataFrame(rows)
    return pd.concat([tx, extra[[c for c in extra.columns if c in tx.columns]]], ignore_index=True)


# --------------------------------------------------------------------------
# Vue globale : salaire, loyer, dépenses, économisé
# --------------------------------------------------------------------------
INCOME_MAIN = "Salaire"
RENT = "Loyer"
ADJ_INCOME = "Ajustements manuels (revenus)"
ADJ_EXPENSE = "Ajustements manuels (dépenses)"
SPREAD = "Remboursement d'impôts (étalé)"
BONUS = "Primes & CE"
HEALTH_REFUND = "Remboursements santé"
EXTRA_INCOME = {BONUS, SPREAD, ADJ_INCOME}           # comptés dans les revenus en plus du salaire
EXPENSE_OFFSETS = {ADJ_EXPENSE, HEALTH_REFUND}        # comptés (en ±) dans les dépenses, hors critère « carte »


def global_monthly(df: pd.DataFrame, deduct_refunds: bool = False) -> pd.DataFrame:
    """Par mois : salaire, loyer, autres dépenses, économisé, taux, et où l'épargne est allée.

    - revenus = salaire + primes / CE + remboursement d'impôts étalé + ajustements manuels (revenus) ;
      toutes les autres entrées d'argent sont ignorées ;
    - dépenses : aussi les remboursements santé (mutuelle, CPAM, rattachés au mois de la dépense) et
      les ajustements manuels (dépenses), en plus ou en moins ;
    - dépenses = paiements par carte, prélèvements et retraits d'espèces, hors loyer : aucun virement
      (émis ou reçu) n'est compté. `deduct_refunds` déduit les avoirs / annulations carte ;
    - économisé = salaire − loyer − dépenses ;
    - investi = virements nets vers les courtiers ; livrets = versements − retraits des livrets (net).
    """
    cols = ["salaire", "exceptionnel", "loyer", "depenses", "economise", "taux", "investi", "livrets"]
    if df.empty:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="month"), dtype=float)
    sal = df[df["category"] == INCOME_MAIN].groupby("month")["amount"].sum()
    rent = -df[df["category"] == RENT].groupby("month")["amount"].sum()
    spend = -global_ops(df, "depenses", deduct_refunds).groupby("month")["amount"].sum()
    inv = -df[df["category"] == "Épargne & investissement"].groupby("month")["amount"].sum()
    liv = -df[df["category"] == "Épargne livrets"].groupby("month")["amount"].sum()
    exc = df[df["category"].isin(EXTRA_INCOME)].groupby("month")["amount"].sum()
    out = pd.DataFrame({"salaire": sal, "exceptionnel": exc, "loyer": rent, "depenses": spend,
                        "investi": inv, "livrets": liv}).fillna(0.0)
    out = out.sort_index()
    out["economise"] = out["salaire"] + out["exceptionnel"] - out["loyer"] - out["depenses"]
    rev = out["salaire"] + out["exceptionnel"]
    out["taux"] = np.where(rev > 0, out["economise"] / rev, np.nan)
    out.index.name = "month"
    return out[cols]


def global_ops(df: pd.DataFrame, part: str, deduct_refunds: bool = False) -> pd.DataFrame:
    """Les opérations exactes derrière un chiffre de `global_monthly` (mêmes filtres).

    part : salaire | loyer | depenses | investi | livrets."""
    if df.empty:
        return df
    if part == "salaire":
        return df[df["category"] == INCOME_MAIN]
    if part == "loyer":
        return df[df["category"] == RENT]
    if part == "depenses":
        lab = df["label"].fillna("").str.upper().str.strip()
        # Carte bancaire, prélèvements (Navigo, abonnements…) et retraits d'espèces ; jamais de virement.
        card = lab.str.match(r"^(CARTE\s|PRLV\b|PRELEVEMENT|RETRAIT\s|RET\s?DAB)") & (df["amount"] < 0)
        refund = lab.str.match(r"^(AVOIR|ANNUL(ATION)? CARTE)\b") & (df["amount"] > 0)
        keep = card | (refund if deduct_refunds else False)
        offset = df["category"].isin(EXPENSE_OFFSETS)
        return df[(keep & (df["cat_type"] == "expense") & (df["category"] != RENT) & ~offset) | offset]
    if part == "exceptionnel":
        return df[df["category"].isin(EXTRA_INCOME)]
    if part == "investi":
        return df[df["category"] == "Épargne & investissement"]
    if part == "livrets":
        return df[df["category"] == "Épargne livrets"]
    raise ValueError(part)


def _main_account(tx: pd.DataFrame, accounts: pd.DataFrame) -> str:
    courant = accounts.loc[accounts["type"] == "courant", "id"]
    return (tx[tx["account_id"].isin(courant)]["account_id"].mode().iloc[0]
            if tx["account_id"].isin(courant).any() else tx["account_id"].iloc[0])


def _synthetic(tx: pd.DataFrame, rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return tx
    extra = pd.DataFrame(rows)
    extra["date"] = pd.to_datetime(extra["date"])
    extra["value_date"] = extra["date"]
    extra["month"] = extra["date"].dt.to_period("M").dt.to_timestamp()
    extra["year"] = extra["date"].dt.year
    extra["factor"] = 1.0
    extra["amount_full"] = extra["amount"]
    types = category_types()
    extra["cat_type"] = extra["category"].map(types).fillna("expense")
    return pd.concat([tx, extra[[c for c in extra.columns if c in tx.columns]]], ignore_index=True)


def add_adjustments(tx: pd.DataFrame, adj: pd.DataFrame, accounts: pd.DataFrame) -> pd.DataFrame:
    """Ajustements manuels (table manual_adjustments) : un mois, une cible (dépenses / revenus),
    un montant signé et une explication. Dépenses : +X les augmente, −X les réduit."""
    if adj is None or adj.empty or tx.empty:
        return tx
    acc = _main_account(tx, accounts)
    rows = []
    for r in adj.itertuples():
        exp = r.target == "depenses"
        rows.append({"id": f"adj-{r.id}", "account_id": acc, "date": f"{r.month}-01", "label": r.label or "Ajustement",
                     "merchant": "AJUSTEMENT MANUEL", "amount": -float(r.amount) if exp else float(r.amount),
                     "category": ADJ_EXPENSE if exp else ADJ_INCOME, "source": "ajustement", "source_cat": "ajustement"})
    return _synthetic(tx, rows)


def spread_income(tx: pd.DataFrame, accounts: pd.DataFrame) -> pd.DataFrame:
    """Étale certaines entrées sur plusieurs mois (règles du profil : etalement: [{pattern, mois}]).
    L'entrée d'origine est mise hors budget ; N lignes de montant/N sont ajoutées à partir de son mois."""
    plan = config.categories().get("etalement") or []
    if not plan or tx.empty:
        return tx
    df = tx.copy()
    rows = []
    for p in plan:
        rx = re.compile(p["pattern"], re.I)
        n = int(p.get("mois", 1))
        hit = df[(df["amount"] > 0) & df["label"].fillna("").str.contains(rx) & (df["source_cat"] != "manuel")]
        for i, r in hit.iterrows():
            df.at[i, "category"], df.at[i, "cat_type"], df.at[i, "source_cat"] = "Virements internes", "transfer", "étalé"
            for k in range(n):
                m = r["month"] + pd.DateOffset(months=k)
                rows.append({"id": f"spread-{r['id']}-{k}", "account_id": r["account_id"], "date": m,
                             "label": f"{p.get('libelle', SPREAD)} ({k + 1}/{n})", "merchant": "ÉTALEMENT",
                             "amount": r["amount"] / n, "category": SPREAD, "source": "etalement",
                             "source_cat": "étalé"})
    return _synthetic(df, rows)


def match_health_refunds(tx: pd.DataFrame, days: int = 62) -> pd.DataFrame:
    """Remboursements santé (mutuelle, CPAM) : rattachés au mois de la dépense santé correspondante —
    la plus proche en montant (≥ remboursement), dans les `days` jours qui précèdent ; sinon même mois."""
    df = tx.copy()
    ref = df[df["category"] == HEALTH_REFUND]
    if ref.empty:
        return df
    health = df[(df["category"] == "Santé") & (df["amount"] < 0)]
    used: set = set()
    df["matched_with"] = None if "matched_with" not in df.columns else df["matched_with"]
    for i, r in ref.sort_values("date").iterrows():
        c = health[(health["date"] <= r["date"]) & (health["date"] >= r["date"] - pd.Timedelta(days=days))
                   & (-health["amount"] >= r["amount"] - 0.01) & ~health.index.isin(used)]
        if c.empty:
            continue
        j = (-c["amount"] - r["amount"]).idxmin()
        used.add(j)
        df.at[i, "month"] = df.at[j, "month"]
        df.at[i, "matched_with"] = f"{df.at[j, 'date']:%d/%m/%Y} {df.at[j, 'merchant']} ({-df.at[j, 'amount']:.2f} €)"
    return df
