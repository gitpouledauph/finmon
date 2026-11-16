import io
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from common import ROOT, bundle, config, dismissed_alerts, get_db, invalidate, profile_name, set_dismissed

st.title("Data & imports")
profile = config.get_profile(profile_name())
db = get_db()
if profile.name == "demo":
    st.warning("You are on the **Demo** profile. Switch to Personal in the sidebar to import your files.")

tab_imp, tab_inst, tab_state, tab_exp = st.tabs(
    ["Import", "Securities", "Status", "Export"])

# ------------------------------------------------------------- import historique
with tab_imp:
    from finmon import manual

    st.caption("Import each account's history once; afterwards add new trades in Transactions. Formats are detected "
               "from the content and re-imports never create duplicates.")
    with st.expander("Which file for each account (guide in French)", expanded=False):
        st.markdown((ROOT / "docs" / "GUIDE_CSV.md").read_text(encoding="utf-8"))
    st.download_button("Download the CSV template (any other broker, bulk entry)",
                       manual.template_csv().encode("utf-8-sig"), file_name="modele-finmon.csv", mime="text/csv")
    hint = st.radio("Boursorama securities file (positions / movements) belongs to",
                    ["PEA", "Brokerage account (CTO)"], horizontal=True)
    files = st.file_uploader("CSV or Excel files", type=["csv", "txt", "xlsx"], accept_multiple_files=True)
    if files and st.button("Import", type="primary"):
        from finmon.sync import import_any

        with st.spinner("Importing (price history is downloaded to value crypto and currencies)…"):
            for f in files:
                dest = profile.archive / "uploads" / f"{datetime.now():%Y%m%d-%H%M%S}_{f.name}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(f.getvalue())
                try:
                    kind, n = import_any(db, dest, account_hint="pea" if hint == "PEA" else "cto",
                                         online=profile.name != "demo")
                    st.success(f"{f.name}: detected as {kind}, {n} new rows.")
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
            with st.expander("Import warnings"):
                st.dataframe(warn, hide_index=True, width="stretch")
    st.divider()
    st.markdown(f"Or copy files to `{profile.inbox}` and import the inbox:")
    c1, c2 = st.columns(2)
    if c1.button("Import inbox"):
        from finmon.sync import import_inbox

        for line in import_inbox(profile, db, online=profile.name != "demo") or ["Inbox is empty."]:
            st.write(line)
        invalidate()
    if c2.button("Refresh price & FX history", disabled=profile.name == "demo",
                 help="Only tickers and currency pairs are sent to Yahoo Finance."):
        from finmon.sync import refresh_prices

        with st.spinner("Downloading prices…"):
            for line in refresh_prices(db):
                st.write(line)
        invalidate()

# ------------------------------------------------------------- titres
with tab_inst:
    inst = db.table("instruments")
    if inst.empty:
        st.info("Aucun titre pour l'instant.")
    else:
        st.caption("Yahoo ticker, asset class and exposures (JSON). Edited lines are marked manual and never overwritten.")
        cols = ["isin", "name", "ticker", "currency", "asset_class", "exposure", "regions", "sectors", "resolved_by"]
        ed = st.data_editor(inst[cols], hide_index=True, width="stretch", disabled=["isin", "resolved_by"],
                            column_config={"asset_class": st.column_config.SelectboxColumn(
                                options=["Actions", "Obligations", "Monétaire", "Crypto", "Matières premières", "Immobilier"])},
                            key="inst_editor")
        if st.button("Save securities"):
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
                st.success(f"{len(changed)} security(ies) updated. Refresh prices if a ticker changed.")
                invalidate()

# ------------------------------------------------------------- état
with tab_state:
    b = bundle()
    st.markdown("**Accounts**")
    tx = db.read("SELECT account_id, MIN(date) AS debut, MAX(date) AS fin, COUNT(*) AS operations FROM cash_transactions GROUP BY account_id")
    tr = db.read("SELECT account_id, MIN(date) AS debut, MAX(date) AS fin, COUNT(*) AS operations FROM trades GROUP BY account_id")
    acc = b.accounts.rename(columns={"id": "account_id"})
    st.dataframe(acc.merge(pd.concat([tx, tr]), on="account_id", how="left"), hide_index=True, width="stretch")
    last_px = db.read("SELECT MAX(date) AS d FROM prices")["d"][0]
    st.write(f"Derniers cours en base : **{last_px or '—'}**")
    st.markdown("**Import log**")
    st.dataframe(b.import_log, hide_index=True, width="stretch")
    hidden = dismissed_alerts()
    st.markdown(f"**Hidden alerts** ({len(hidden)})")
    if hidden:
        for k, v in hidden.items():
            c1, c2 = st.columns([12, 2], vertical_alignment="center")
            c1.caption(f"{v['text']} — hidden {pd.Timestamp(v['ts']):%d %b %Y}")
            if c2.button("Restore", key=f"undismiss-{k}", width="stretch"):
                set_dismissed([v["text"]], hide=False)
                st.rerun()
    else:
        st.caption("None.")

# ------------------------------------------------------------- export
with tab_exp:
    from finmon.data import export_excel

    st.markdown("Positions, classified transactions, monthly spending, net worth and allocation in one Excel workbook.")
    if st.button("Build Excel export"):
        buf = io.BytesIO()
        export_excel(bundle(), buf)
        st.download_button("Download", buf.getvalue(), file_name=f"finmon-{datetime.now():%Y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption(f"The whole database is one SQLite file: `{profile.db_path}`")
