import io
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from common import ROOT, bundle, config, get_db, invalidate, profile_name

st.title("Données & imports")
profile = config.get_profile(profile_name())
db = get_db()
if profile.name == "demo":
    st.warning("Vous êtes sur le profil **Démo**. Repassez sur « Mes données » dans la barre latérale pour importer vos fichiers.")

tab_imp, tab_tr, tab_inst, tab_state, tab_exp = st.tabs(
    ["📄 Importer des CSV", "🇩🇪 Trade Republic", "🏷️ Titres", "🔎 État des données", "📤 Export"])

# ------------------------------------------------------------- import CSV
with tab_imp:
    st.markdown(
        "Déposez ici vos exports **Boursorama** (opérations de compte courant/livret, positions ou mouvements "
        "du PEA/CTO) ou les fichiers **pytr**. Le format est reconnu automatiquement ; ré-importer un fichier "
        "qui recoupe un précédent ne crée pas de doublons.")
    with st.expander("📘 Quels fichiers exporter depuis Boursorama ?"):
        st.markdown((ROOT / "docs" / "GUIDE_CSV.md").read_text(encoding="utf-8"))
    hint = st.radio("Pour un fichier de titres, il s'agit du…", ["PEA", "Compte-titres (CTO)"], horizontal=True)
    files = st.file_uploader("Fichiers CSV ou Excel", type=["csv", "txt", "xlsx"], accept_multiple_files=True)
    if files and st.button("Importer", type="primary"):
        from finmon.sync import import_any

        for f in files:
            dest = profile.archive / "uploads" / f"{datetime.now():%Y%m%d-%H%M%S}_{f.name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.getvalue())
            try:
                kind, n = import_any(db, dest, account_hint="pea" if hint == "PEA" else "cto")
                st.success(f"{f.name} : reconnu comme « {kind} », {n} nouvelles lignes.")
            except Exception as e:
                db.log("upload", f.name, 0, "error", str(e))
                st.error(f"{f.name} : {e}")
        invalidate()
    st.divider()
    st.markdown(f"Vous pouvez aussi copier les fichiers dans `{profile.inbox}` (sous-dossiers `boursorama/`, "
                "`traderepublic/`) puis cliquer :")
    c1, c2 = st.columns(2)
    if c1.button("📥 Importer la boîte de dépôt"):
        from finmon.sync import import_inbox

        for line in import_inbox(profile, db) or ["Boîte de dépôt vide."]:
            st.write(line)
        invalidate()
    if c2.button("🌐 Mettre à jour cours & taux de change", disabled=profile.name == "demo",
                 help="Seuls les ISIN/tickers et paires de devises sont envoyés à Yahoo Finance."):
        from finmon import market

        with st.spinner("Téléchargement des cours…"):
            for line in market.update_all(db):
                st.write(line)
        invalidate()

# ------------------------------------------------------------- Trade Republic
with tab_tr:
    from finmon.importers import traderepublic as trmod

    st.markdown(
        "Trade Republic n'a pas d'API officielle : finmon utilise **pytr**, un client open source qui "
        "tourne sur votre Mac. Identifiants et cookies restent dans `~/.pytr/`.")
    st.markdown("**Première connexion (une fois, dans un terminal) :**")
    st.code(f"cd {ROOT}\nsource .venv-finmon/bin/activate\npytr login --store_credentials", language="bash")
    st.caption("pytr demande votre numéro et votre PIN, puis un code reçu dans l'app. "
               "⚠️ --store_credentials enregistre le PIN en clair dans ~/.pytr/credentials : "
               "omettez l'option si vous préférez le ressaisir à chaque synchro (via `python -m finmon sync-tr`).")
    ok = trmod.credentials_stored()
    st.write("Identifiants enregistrés : " + ("✅ oui" if ok else "❌ non"))
    if st.button("🔄 Synchroniser Trade Republic", disabled=not ok or profile.name == "demo", type="primary"):
        with st.spinner("pytr exporte vos transactions… (peut prendre une minute)"):
            try:
                for line in trmod.sync(db, profile.archive / "traderepublic" / "latest", interactive=False):
                    st.write(line)
                from finmon import market

                for line in market.update_all(db):
                    st.write(line)
            except Exception as e:
                st.error(str(e))
                st.info("Si pytr demande un nouveau code, lancez `python -m finmon sync-tr` dans un terminal.")
        invalidate()

# ------------------------------------------------------------- titres
with tab_inst:
    inst = db.table("instruments")
    if inst.empty:
        st.info("Aucun titre pour l'instant.")
    else:
        st.caption("Ticker Yahoo utilisé pour les cours, classe d'actif et expositions (JSON). "
                   "Une ligne modifiée ici est marquée « manuel » et n'est plus écrasée automatiquement.")
        cols = ["isin", "name", "ticker", "currency", "asset_class", "exposure", "regions", "sectors", "resolved_by"]
        ed = st.data_editor(inst[cols], hide_index=True, width="stretch", disabled=["isin", "resolved_by"],
                            column_config={"asset_class": st.column_config.SelectboxColumn(
                                options=["Actions", "Obligations", "Monétaire", "Crypto", "Matières premières", "Immobilier"])},
                            key="inst_editor")
        if st.button("💾 Enregistrer les titres"):
            bad = []
            for c in ("exposure", "regions", "sectors"):
                for v, isin in zip(ed[c], ed["isin"]):
                    try:
                        json.loads(v or "{}")
                    except ValueError:
                        bad.append(f"{isin} ({c})")
            if bad:
                st.error("JSON invalide : " + ", ".join(bad))
            else:
                changed = ed[(ed[cols].astype(str) != inst[cols].astype(str)).any(axis=1)].copy()
                changed["resolved_by"] = "manuel"
                changed["region"] = [max(json.loads(r or '{"Autre":1}'), key=json.loads(r or '{"Autre":1}').get) for r in changed["regions"]]
                changed["sector"] = None
                db.upsert("instruments", changed, mode="replace")
                st.success(f"{len(changed)} titre(s) mis à jour. Pensez à « Mettre à jour cours » si le ticker a changé.")
                invalidate()

# ------------------------------------------------------------- état
with tab_state:
    b = bundle()
    st.markdown("**Comptes**")
    tx = db.read("SELECT account_id, MIN(date) AS debut, MAX(date) AS fin, COUNT(*) AS operations FROM cash_transactions GROUP BY account_id")
    tr = db.read("SELECT account_id, MIN(date) AS debut, MAX(date) AS fin, COUNT(*) AS operations FROM trades GROUP BY account_id")
    acc = b.accounts.rename(columns={"id": "account_id"})
    st.dataframe(acc.merge(pd.concat([tx, tr]), on="account_id", how="left"), hide_index=True, width="stretch")
    last_px = db.read("SELECT MAX(date) AS d FROM prices")["d"][0]
    st.write(f"Derniers cours en base : **{last_px or '—'}**")
    st.markdown("**Journal des imports**")
    st.dataframe(b.import_log, hide_index=True, width="stretch")

# ------------------------------------------------------------- export
with tab_exp:
    from finmon.data import export_excel

    st.markdown("Exporte positions, opérations classées, dépenses par mois, patrimoine et allocation dans un classeur Excel.")
    if st.button("Préparer l'export Excel"):
        buf = io.BytesIO()
        export_excel(bundle(), buf)
        st.download_button("⬇️ Télécharger", buf.getvalue(), file_name=f"finmon-{datetime.now():%Y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption(f"La base complète est un simple fichier SQLite : `{profile.db_path}`")
