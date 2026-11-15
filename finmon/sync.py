"""Orchestration : importer la boîte de dépôt, synchroniser TR, mettre à jour les cours."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .config import Profile
from .db import DB
from .importers import boursorama, traderepublic


def import_inbox(profile: Profile, db: DB) -> list[str]:
    """Importe tous les CSV déposés dans data/<profil>/inbox/** puis les archive."""
    logs = []
    for path in sorted(profile.inbox.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".csv", ".txt", ".xlsx"):
            continue
        folder = path.parent.name.lower()
        try:
            if folder == "traderepublic":
                kind, n = traderepublic.import_file(db, path)
            else:
                kind, n = import_any(db, path)
            logs.append(f"✅ {path.name} : {kind}, {n} nouvelles lignes")
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = profile.archive / folder / f"{stamp}_{path.name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), dest)
        except Exception as e:  # on continue avec les autres fichiers
            db.log(folder, path.name, 0, "error", str(e))
            logs.append(f"❌ {path.name} : {e}")
    return logs


def import_any(db: DB, path: Path, account_hint: str | None = None) -> tuple[str, int]:
    """Détecte la source (Boursorama ou Trade Republic) d'après les colonnes."""
    from .parsing import read_csv_auto

    df = read_csv_auto(path)
    if traderepublic.detect(df):
        return traderepublic.import_file(db, path)
    return boursorama.import_file(db, path, account_hint=account_hint or path.name)


def refresh_all(profile: Profile, tr: bool = False, interactive: bool = True, prices: bool = True) -> list[str]:
    from . import market

    db = DB(profile.db_path)
    logs = import_inbox(profile, db)
    if tr:
        try:
            logs += traderepublic.sync(db, profile.archive / "traderepublic" / "latest", interactive=interactive)
        except Exception as e:
            db.log("traderepublic", None, 0, "error", str(e))
            logs.append(f"❌ Trade Republic : {e}")
    if prices and profile.name != "demo":
        logs += market.update_all(db)
    return logs
