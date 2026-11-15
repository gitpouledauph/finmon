"""Petits utilitaires de lecture de CSV « à la française »."""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from pathlib import Path

import pandas as pd


def read_text(path: Path | str | bytes) -> str:
    raw = path if isinstance(path, bytes) else Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_csv_auto(path: Path | str | bytes) -> pd.DataFrame:
    """Lit un CSV (ou un .xlsx) en devinant séparateur et encodage, tout en texte."""
    if not isinstance(path, bytes) and Path(path).suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        return df
    text = read_text(path)
    first = text.splitlines()[0] if text else ""
    sep = max([";", ",", "\t"], key=first.count)
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    return df


def norm(s: str) -> str:
    """minuscules, sans accents ni ponctuation — pour comparer des noms de colonnes."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def pick(df: pd.DataFrame, *aliases: str) -> str | None:
    """Retourne la colonne de df correspondant au premier alias trouvé."""
    lookup = {norm(c): c for c in df.columns}
    for a in aliases:
        if norm(a) in lookup:
            return lookup[norm(a)]
    return None


def to_number(s) -> float | None:
    """'-1 234,56 €' -> -1234.56 ; '1,234.56' -> 1234.56."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(" ", "").replace(" ", "").replace(" ", "")
    s = re.sub(r"[€$£%A-Za-z]", "", s)
    if s in ("", "-", "+"):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def to_numbers(series: pd.Series) -> pd.Series:
    return series.map(to_number).astype("float64")


def to_dates(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str[:19]
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if iso.any():
        out[iso] = pd.to_datetime(s[iso].str[:10], format="%Y-%m-%d", errors="coerce")
    if (~iso).any():
        out[~iso] = pd.to_datetime(s[~iso], dayfirst=True, errors="coerce")
    return out


def _missing(x) -> bool:
    try:
        return x is None or bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


def stable_ids(df: pd.DataFrame, cols: list[str], prefix: str) -> pd.Series:
    """Identifiant déterministe par ligne, robuste aux ré-imports chevauchants.

    Deux lignes identiques dans le même fichier sont distinguées par leur rang
    d'occurrence, ce qui donne les mêmes ids si on ré-importe un export qui recouvre
    la même période.
    """
    parts = df[cols].apply(lambda col: col.map(lambda x: "" if _missing(x) else str(x)))
    key = parts.agg("|".join, axis=1)
    occ = key.groupby(key).cumcount().astype(str)
    full = prefix + "|" + key + "|" + occ
    return full.map(lambda k: hashlib.sha1(k.encode()).hexdigest()[:16])
