"""Chemins et chargement de la configuration YAML."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


@dataclass(frozen=True)
class Profile:
    """Un profil = un dossier de données isolé (réel ou démo)."""

    name: str
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / "finmon.db"

    @property
    def inbox(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def archive(self) -> Path:
        return self.data_dir / "archive"

    @property
    def exports(self) -> Path:
        return self.data_dir / "exports"

    def ensure(self) -> "Profile":
        for p in (
            self.data_dir,
            self.inbox / "boursorama",
            self.inbox / "traderepublic",
            self.inbox / "binance",
            self.inbox / "ibkr",
            self.inbox / "manuel",
            self.archive,
            self.exports,
        ):
            p.mkdir(parents=True, exist_ok=True)
        return self


def get_profile(name: str | None = None) -> Profile:
    name = name or os.environ.get("FINMON_PROFILE", "reel")
    base = Path(os.environ.get("FINMON_DATA_DIR", ROOT / "data"))
    sub = "demo" if name == "demo" else "reel"
    prof = Profile(name=sub, data_dir=base / sub).ensure()
    set_active(prof.data_dir)
    return prof


# Profil actif : ses règles de classement personnelles (data/<profil>/regles.yaml) complètent
# config/categories.yaml. Ce fichier reste local (noms de personnes, comptes) et n'est pas versionné.
_ACTIVE_DIR: Path | None = None


def set_active(data_dir: Path | str) -> None:
    global _ACTIVE_DIR
    _ACTIVE_DIR = Path(data_dir)


def personal_rules_path() -> Path | None:
    return _ACTIVE_DIR / "regles.yaml" if _ACTIVE_DIR else None


def _load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=None)
def settings() -> dict:
    s = _load_yaml("settings.yaml")
    s.setdefault("base_currency", "EUR")
    s.setdefault("accounts", {})
    s.setdefault("benchmark", {"ticker": "IWDA.AS", "name": "MSCI World (IWDA)"})
    return s


def auto_rules_path() -> Path | None:
    """Règles créées depuis le dashboard (« Règle » coché lors d'une correction)."""
    return _ACTIVE_DIR / "regles_auto.yaml" if _ACTIVE_DIR else None


def categories() -> dict:
    p, a = personal_rules_path(), auto_rules_path()
    mt = tuple(x.stat().st_mtime if x and x.exists() else 0.0 for x in (p, a))
    return _categories(str(p) if p else "", mt)


def add_auto_rule(pattern: str, category: str, sign: str | None = None) -> None:
    path = auto_rules_path()
    if path is None:
        raise RuntimeError("Aucun profil actif.")
    data = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}
    rules = [r for r in (data.get("rules") or []) if r.get("pattern") != pattern]
    rule = {"pattern": pattern, "category": category}
    if sign:
        rule["sign"] = sign
    data["rules"] = [rule] + rules
    path.write_text("# Règles ajoutées depuis le dashboard (page Dépenses). Modifiables à la main.\n"
                    + yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


@lru_cache(maxsize=8)
def _categories(perso_path: str, _mtime: tuple) -> dict:
    base = _load_yaml("categories.yaml")
    if not perso_path:
        return base
    perso: dict = {}
    if Path(perso_path).exists():
        with open(perso_path, encoding="utf-8") as f:
            perso = yaml.safe_load(f) or {}
    auto = Path(perso_path).with_name("regles_auto.yaml")
    if auto.exists():
        a = yaml.safe_load(auto.read_text(encoding="utf-8")) or {}
        perso["rules"] = list(a.get("rules") or []) + list(perso.get("rules") or [])   # corrections d'abord
    out = dict(base)
    out["categories"] = {**(base.get("categories") or {}), **(perso.get("categories") or {})}
    out["rules"] = list(perso.get("rules") or []) + list(base.get("rules") or [])   # règles perso d'abord
    out["bank_mapping"] = {**(base.get("bank_mapping") or {}), **(perso.get("bank_mapping") or {})}
    out["owner_names"] = perso.get("owner_names") or []
    out["loyer_fixe"] = perso.get("loyer_fixe") or []
    return out


@lru_cache(maxsize=None)
def instruments_config() -> dict:
    return _load_yaml("instruments.yaml") or {}


def reload() -> None:
    settings.cache_clear()
    _categories.cache_clear()
    instruments_config.cache_clear()
