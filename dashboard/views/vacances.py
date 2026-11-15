import pandas as pd
import streamlit as st

from common import bundle, empty_state, eur, get_db, invalidate, plot
from finmon import charts
from finmon.analytics import budget

b = bundle()
st.title("Vacances")
if b.tx.empty:
    empty_state("opérations bancaires")
    st.stop()

db = get_db()
vac = b.vacations.copy()

# ------------------------------------------------------------- périodes
with st.expander("Mes périodes de vacances", expanded=vac.empty):
    st.caption("Toute dépense pendant une période compte pour le voyage (hors loyer, abonnements, impôts…). "
               "Les achats faits avant (billets, hôtels) se rattachent depuis la page Dépenses, colonne « Vacances ».")
    edit = st.data_editor(
        vac.assign(start=pd.to_datetime(vac["start"]), end=pd.to_datetime(vac["end"])) if not vac.empty
        else pd.DataFrame({"name": pd.Series(dtype=str), "start": pd.Series(dtype="datetime64[ns]"),
                           "end": pd.Series(dtype="datetime64[ns]"), "note": pd.Series(dtype=str)}),
        num_rows="dynamic", hide_index=True, width="stretch",
        column_config={"name": st.column_config.TextColumn("Nom", required=True),
                       "start": st.column_config.DateColumn("Début", format="DD/MM/YYYY", required=True),
                       "end": st.column_config.DateColumn("Fin", format="DD/MM/YYYY", required=True),
                       "note": st.column_config.TextColumn("Note")}, key="vac_editor")
    if st.button("Enregistrer les périodes", type="primary"):
        e = edit.dropna(subset=["name", "start", "end"]).copy()
        e["start"] = pd.to_datetime(e["start"]).dt.strftime("%Y-%m-%d")
        e["end"] = pd.to_datetime(e["end"]).dt.strftime("%Y-%m-%d")
        db.execute("DELETE FROM vacations")
        db.upsert("vacations", e[["name", "start", "end", "note"]], mode="replace")
        invalidate()
        st.rerun()

sug = budget.suggest_vacations(b.tx, vac)
if not sug.empty:
    st.markdown("**Séjours détectés automatiquement** (paiements en devise étrangère)")
    for i, r in sug.iterrows():
        c1, c2 = st.columns([4, 1])
        c1.write(f"• {r['name']} — du {r['start']:%d/%m/%Y} au {r['end']:%d/%m/%Y}, {r['ops']} opérations, {eur(r['total'])}")
        if c2.button("Ajouter", key=f"sug{i}"):
            db.upsert("vacations", pd.DataFrame([{"name": r["name"], "start": r["start"].isoformat(),
                                                  "end": r["end"].isoformat(), "note": "détecté"}]), mode="replace")
            invalidate()
            st.rerun()

if vac.empty:
    st.info("Ajoutez une période ci-dessus pour voir le coût de vos voyages.")
    st.stop()

spend = budget.vacation_spend(b.tx, vac)
if spend.empty:
    st.info("Aucune dépense trouvée sur ces périodes.")
    st.stop()

# ------------------------------------------------------------- synthèse
trips = vac.set_index("name")
agg = spend.groupby("vacation")["spend"].sum().reindex(trips.index).fillna(0.0)
days = (pd.to_datetime(trips["end"]) - pd.to_datetime(trips["start"])).dt.days + 1
year_of = pd.to_datetime(trips["start"]).dt.year
exp_year = budget.expenses(b.tx).groupby("year")["spend"].sum()
this_year = pd.Timestamp.today().year

c = st.columns(4)
c[0].metric(f"Vacances {this_year}", eur(agg[year_of == this_year].sum()))
c[1].metric(f"Vacances {this_year - 1}", eur(agg[year_of == this_year - 1].sum()))
share = agg[year_of == this_year - 1].sum() / exp_year.get(this_year - 1, float("nan"))
c[2].metric(f"Part des dépenses {this_year - 1}", f"{share * 100:.0f} %" if share == share else "—")
c[3].metric("Coût moyen par jour", eur((agg / days).mean()))

st.subheader("Coût par voyage")
cat = spend.pivot_table(index="vacation", columns="category", values="spend", aggfunc="sum", fill_value=0.0)
cat = cat.reindex(trips.sort_values("start").index).dropna(how="all").fillna(0.0)
top = list(cat.sum().sort_values(ascending=False).index[:7])
g = cat[top].copy()
rest = [c for c in cat.columns if c not in top]
if rest:
    g["Autres"] = cat[rest].sum(axis=1)
plot(charts.stacked_bars(g, colors=charts.color_map(top)), key="trips")

l, r = st.columns(2)
with l:
    st.subheader("Par année")
    y = agg.groupby(year_of).sum()
    plot(charts.hbar([str(i) for i in y.index], y.values, text=[eur(v) for v in y.values]), key="years")
with r:
    st.subheader("Coût par jour")
    per = (agg / days).sort_values(ascending=False)
    plot(charts.hbar(per.index, per.values, text=[eur(v) for v in per.values]), key="perday")

with st.expander("Détail des opérations"):
    pick = st.selectbox("Voyage", trips.index.tolist())
    d = spend[spend["vacation"] == pick].sort_values("date")
    st.dataframe(d[["date", "label", "category", "spend", "foreign_currency"]].rename(columns={
        "date": "Date", "label": "Libellé", "category": "Catégorie", "spend": "Montant", "foreign_currency": "Devise"}),
        hide_index=True, width="stretch",
        column_config={"Montant": st.column_config.NumberColumn(format="%.2f €"),
                       "Date": st.column_config.DateColumn(format="DD/MM/YYYY")})
