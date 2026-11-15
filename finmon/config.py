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
    return Profile(name=sub, data_dir=base / sub).ensure()


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


@lru_cache(maxsize=None)
def categories() -> dict:
    return _load_yaml("categories.yaml")


@lru_cache(maxsize=None)
def instruments_config() -> dict:
    return _load_yaml("instruments.yaml") or {}


def reload() -> None:
    settings.cache_clear()
    categories.cache_clear()
    instruments_config.cache_clear()
