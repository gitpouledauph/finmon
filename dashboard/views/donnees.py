import io
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from common import ROOT, bundle, config, dismissed_alerts, get_db, invalidate, profile_name, set_dismissed

st.title("Données & imports")
profile = config.get_profile(profile_name())
db = get_db()
if profile.name == "demo":
    st.warning("Vous êtes sur le profil **Démo**. Repassez sur « Mes données » dans la barre latérale pour importer vos fichiers.")

tab_imp, tab_inst, tab_state, tab_exp = st.tabs(
    ["Import historique", "Titres", "État des données", "Export"])

# ------------------------------------------------------------- import historique
with tab_imp:
    from finmon import manual

    st.markdown(
        "**Une seule fois** : importez l'historique de chaque compte. Ensuite, ajoutez vos nouvelles opérations "
        "dans **Saisir une opération** — plus aucune connexion n'est nécessaire. "
        "Le format est reconnu automatiquement et ré-importer un fichier ne crée pas de doublons.")
    with st.expander("Quel fichier pour chaque compte ?", expanded=True):
        st.markdown((ROOT / "docs" / "GUIDE_CSV.md").read_text(encoding="utf-8"))
    st.download_button("Modèle CSV finmon (pour tout autre courtier ou une saisie en masse)",
                       manual.template_csv().encode("utf-8-sig"), file_name="modele-finmon.csv", mime="text/csv")
    hint = st.radio("Pour un fichier Boursorama de titres (positions / mouvements), il s'agit du…",
                    ["PEA", "Compte-titres (CTO)"], horizontal=True)
    files = st.file_uploader("Fichiers CSV ou Excel", type=["csv", "txt", "xlsx"], accept_multiple_files=True)
    if files and st.button("Importer", type="primary"):
        from finmon.sync import import_any

        with st.spinner("Import (les cours historiques sont téléchargés pour valoriser crypto et devises)…"):
            for f in files:
                dest = profile.archive / "uploads" / f"{datetime.now():%Y%m%d-%H%M%S}_{f.name}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(f.getvalue())
                try:
                    kind, n = import_any(db, dest, account_hint="pea" if hint == "PEA" else "cto",
                                         online=profile.name != "demo")
                    st.success(f"{f.name} : reconnu comme « {kind} », {n} nouvelles lignes.")
                except Exception as e:
                    db.log("upload", f.name, 0, "error", str(e))
                    st.error(f"{f.name} : {e}")
            if profile.name != "demo":
                from finmon.sync import refresh_prices

                for line in refresh_prices(db):
                    st.write(line)
        invalidate()
        warn = db.read("SELECT file, message FROM import_log WHERE status IN ('warning','error') "
                       "ORDER BY ts DESC LIMIT 10")
        if not warn.empty:
            with st.expander("Points d'attention de l'import"):
                st.dataframe(warn, hide_index=True, width="stretch")
    st.divider()
    st.markdown(f"Autre possibilité : copier les fichiers dans `{profile.inbox}` puis cliquer :")
    c1, c2 = st.columns(2)
    if c1.button("Importer la boîte de dépôt"):
        from finmon.sync import import_inbox

        for line in import_inbox(profile, db, online=profile.name != "demo") or ["Boîte de dépôt vide."]:
            st.write(line)
        invalidate()
    if c2.button("Mettre à jour l'historique des cours & changes", disabled=profile.name == "demo",
                 help="Seuls les tickers et paires de devises sont envoyés à Yahoo Finance."):
        from finmon.sync import refresh_prices

        with st.spinner("Téléchargement des cours…"):
            for line in refresh_prices(db):
                st.write(line)
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
        if st.button("Enregistrer les titres"):
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
    hidden = dismissed_alerts()
    st.markdown(f"**Alertes masquées** ({len(hidden)})")
    if hidden:
        for k, v in hidden.items():
            c1, c2 = st.columns([12, 2], vertical_alignment="center")
            c1.caption(f"{v['text']} — masquée le {pd.Timestamp(v['ts']):%d/%m/%Y}")
            if c2.button("Réafficher", key=f"undismiss-{k}", width="stretch"):
                set_dismissed([v["text"]], hide=False)
                st.rerun()
    else:
        st.caption("Aucune.")

# ------------------------------------------------------------- export
with tab_exp:
    from finmon.data import export_excel

    st.markdown("Exporte positions, opérations classées, dépenses par mois, patrimoine et allocation dans un classeur Excel.")
    if st.button("Préparer l'export Excel"):
        buf = io.BytesIO()
        export_excel(bundle(), buf)
        st.download_button("Télécharger", buf.getvalue(), file_name=f"finmon-{datetime.now():%Y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption(f"La base complète est un simple fichier SQLite : `{profile.db_path}`")
