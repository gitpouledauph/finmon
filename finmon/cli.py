"""Ligne de commande : python -m finmon <commande>.

  import       importe les CSV déposés dans data/reel/inbox/
  sync         import + Trade Republic (pytr) + cours et change
  sync-tr      Trade Republic seulement (interactif : code à 4 chiffres)
  prices       met à jour cours, change et métadonnées des titres
  demo         (re)génère le profil de démonstration
  export       exporte tout en Excel dans data/<profil>/exports/
  status       résumé de ce qui est en base
  dashboard    lance le dashboard Streamlit
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime

from . import config
from .db import DB


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="finmon", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["import", "sync", "sync-tr", "prices", "demo", "export", "status", "dashboard"])
    ap.add_argument("--profile", default=None, help="reel (défaut) ou demo")
    ap.add_argument("--no-tr", action="store_true", help="sync : ne pas lancer pytr")
    args = ap.parse_args(argv)
    profile = config.get_profile(args.profile)

    if args.command == "demo":
        from . import demo

        print(demo.build())
        print(f"Profil démo prêt : {config.get_profile('demo').db_path}")
        return

    db = DB(profile.db_path)
    if args.command == "import":
        from .sync import import_inbox

        logs = import_inbox(profile, db) or ["Rien à importer dans " + str(profile.inbox)]
    elif args.command == "sync":
        from .sync import refresh_all

        logs = refresh_all(profile, tr=not args.no_tr, interactive=sys.stdin.isatty())
    elif args.command == "sync-tr":
        from .importers import traderepublic

        logs = traderepublic.sync(db, profile.archive / "traderepublic" / "latest", interactive=True)
    elif args.command == "prices":
        from . import market

        logs = market.update_all(db)
    elif args.command == "export":
        from .data import export_excel, load

        path = profile.exports / f"finmon-{datetime.now():%Y%m%d-%H%M}.xlsx"
        export_excel(load(db), path)
        logs = [f"Export : {path}"]
    elif args.command == "status":
        logs = []
        for t in ("accounts", "cash_transactions", "trades", "position_snapshots", "instruments", "prices", "fx_rates"):
            n = db.read(f"SELECT COUNT(*) AS n FROM {t}")["n"][0]
            logs.append(f"{t:20s} {n:>8}")
        logs.append(db.read("SELECT account_id, MIN(date) AS debut, MAX(date) AS fin, COUNT(*) AS n "
                            "FROM cash_transactions GROUP BY account_id").to_string(index=False))
    elif args.command == "dashboard":
        app = config.ROOT / "dashboard" / "Accueil.py"
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(app)], check=False)
        return
    print("\n".join(logs))


if __name__ == "__main__":
    main()
