"""Ligne de commande : python -m finmon <commande>.

  import       importe les fichiers déposés dans data/reel/inbox/ (Boursorama, Binance, IBKR, TR, modèle)
  export-tr    UNE FOIS : exporte l'historique Trade Republic avec pytr puis l'importe
  prices       met à jour cours (historique + dernier cours), change et métadonnées
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
    ap.add_argument("command", choices=["import", "export-tr", "prices", "demo", "export", "status", "dashboard"])
    ap.add_argument("--profile", default=None, help="reel (défaut) ou demo")
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
    elif args.command == "export-tr":
        from .importers import traderepublic

        logs = traderepublic.sync(db, profile.archive / "traderepublic" / "historique", interactive=True)
        logs.append("Historique Trade Republic importé. Vous pouvez supprimer ~/.pytr si vous ne voulez plus de lien.")
    elif args.command == "prices":
        from .sync import refresh_prices

        logs = refresh_prices(db)
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
