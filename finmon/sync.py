"""Import des fichiers historiques (une fois) et mise à jour des cours."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .config import Profile
from .db import DB
from .importers import binance, boursorama, ibkr, traderepublic

SOURCES = ("boursorama", "traderepublic", "binance", "ibkr", "modele")


def import_inbox(profile: Profile, db: DB, online: bool = True) -> list[str]:
    """Importe tous les fichiers déposés dans data/<profil>/inbox/** puis les archive."""
    logs = []
    for path in sorted(profile.inbox.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".csv", ".txt", ".xlsx"):
            continue
        folder = path.parent.name.lower()
        try:
            kind, n = import_any(db, path, account_hint=path.name, online=online)
            logs.append(f"OK — {path.name} : {kind}, {n} nouvelles lignes")
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = profile.archive / folder / f"{stamp}_{path.name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), dest)
        except Exception as e:  # on continue avec les autres fichiers
            db.log(folder, path.name, 0, "error", str(e))
            logs.append(f"Erreur — {path.name} : {e}")
    return logs


def import_any(db: DB, path: Path, account_hint: str | None = None, online: bool = True) -> tuple[str, int]:
    """Reconnaît la source d'après le contenu du fichier et l'importe."""
    from . import manual
    from .parsing import read_csv_auto, read_text

    path = Path(path)
    if path.suffix.lower() in (".csv", ".txt") and ibkr.detect_text(read_text(path)):
        return ibkr.import_file(db, path, online=online)
    df = read_csv_auto(path)
    if binance.detect(df):
        return binance.import_file(db, path, online=online)
    if traderepublic.detect(df):
        return traderepublic.import_file(db, path)
    if manual.detect(df):
        return manual.import_template(db, path, online=online)
    return boursorama.import_file(db, path, account_hint=account_hint or path.name)


def refresh_prices(db: DB) -> list[str]:
    from . import market

    logs = market.update_all(db)
    n, t = market.live_update(db)
    return logs + [f"Cours en direct : {n} valeurs à {t}"]
