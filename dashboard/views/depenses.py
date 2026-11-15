import pandas as pd
import streamlit as st

from common import bundle, download_df, empty_state, eur, get_db, invalidate, plot
from finmon import charts
from finmon.analytics import budget

b = bundle()
st.title("Dépenses")
tx = b.tx
if tx.empty:
    empty_state("opérations bancaires")
    st.stop()

# ------------------------------------------------------------- filtres
names = b.accounts.set_index("id")["name"].to_dict()
budget_accounts = sorted(a for a in tx["account_id"].unique()
                         if b.accounts.set_index("id")["type"].get(a) in ("courant", "cto"))
f1, f2, f3 = st.columns([2, 1, 1])
accs = f1.multiselect("Comptes", budget_accounts, default=budget_accounts, format_func=lambda a: names.get(a, a))
years = sorted(tx["year"].unique(), reverse=True)
year = f2.selectbox("Année", ["12 derniers mois"] + [str(y) for y in years])
gran = f3.segmented_control("Vue", ["Mois", "Année"], default="Mois")

t = tx[tx["account_id"].isin(accs)]
last_month = t["month"].max()
if year == "12 derniers mois":
    t_sel = t[t["month"] > last_month - pd.DateOffset(months=12)]
else:
    t_sel = t[t["year"] == int(year)]
e_all = budget.expenses(t)
e = budget.expenses(t_sel)

# Couleurs fixes : top 7 catégories sur tout l'historique (indépendant du filtre).
top = list(e_all.groupby("category")["spend"].sum().sort_values(ascending=False).index[:7])
cmap = charts.color_map(top)

# ------------------------------------------------------------- KPIs
flows = budget.monthly_flows(t_sel)
complete = flows[flows.index < pd.Timestamp.today().to_period("M").to_timestamp()]
c = st.columns(4)
c[0].metric("Dépenses sur la période", eur(e["spend"].sum()))
c[1].metric("Moyenne mensuelle", eur(complete["expenses"].mean() if not complete.empty else None),
            help="Sur les mois complets de la période.")
c[2].metric("Revenus sur la période", eur(flows["income"].sum()))
rate = flows["savings"].sum() / flows["income"].sum() if flows["income"].sum() else None
c[3].metric("Taux d'épargne", f"{rate * 100:.0f} %" if rate is not None else "—")

# ------------------------------------------------------------- graphes
st.subheader("Dépenses par catégorie")
if gran == "Année":
    piv = e_all.pivot_table(index="year", columns="category", values="spend", aggfunc="sum", fill_value=0.0)
    piv.index = piv.index.astype(str)
else:
    piv = e.pivot_table(index="month", columns="category", values="spend", aggfunc="sum", fill_value=0.0)
keep = [c for c in top if c in piv.columns]
other = [c for c in piv.columns if c not in keep]
grouped = piv[keep].copy()
if other:
    grouped["Autres"] = piv[other].sum(axis=1)
plot(charts.stacked_bars(grouped, colors=cmap), key="stack")

l, r = st.columns(2)
with l:
    st.subheader("Répartition")
    by_cat = e.groupby("category")["spend"].sum().sort_values(ascending=False)
    by_cat = by_cat[by_cat > 0]
    share = by_cat / by_cat.sum()
    plot(charts.hbar(by_cat.index, by_cat.values, color=[cmap.get(c, charts.OTHER) for c in by_cat.index],
                     text=[f"{eur(v)} · {s * 100:.0f} %" for v, s in zip(by_cat.values, share.values)]), key="cat")
with r:
    st.subheader("Principaux marchands")
    by_m = e.groupby("merchant")["spend"].agg(["sum", "count"]).sort_values("sum", ascending=False).head(15)
    plot(charts.hbar(by_m.index, by_m["sum"], text=[f"{eur(v)} · {n} op." for v, n in zip(by_m["sum"], by_m["count"])]),
         key="merch")

st.subheader("Carte de chaleur catégorie × mois")
hm = e.pivot_table(index="category", columns="month", values="spend", aggfunc="sum", fill_value=0.0)
hm = hm.loc[hm.sum(axis=1).sort_values(ascending=False).index]
plot(charts.heatmap(hm.clip(lower=0)), key="heat")

# ------------------------------------------------------------- édition
st.subheader("Opérations")
st.caption("Corrigez une catégorie ou rattachez une dépense à des vacances (ex. billet d'avion acheté à l'avance) : "
           "la correction est mémorisée et prime sur les règles automatiques.")
cats = list((budget.category_types()).keys())
vac_names = [""] + b.vacations["name"].tolist()
only = st.toggle("Seulement « À classer »", value=False)
q = st.text_input("Rechercher un libellé", "")
view = t_sel.sort_values("date", ascending=False)
if only:
    view = view[view["category"] == "À classer"]
if q:
    view = view[view["label"].str.contains(q, case=False, regex=False)]
view = view.head(500)
ed = st.data_editor(
    view[["id", "date", "label", "amount", "category", "vacation_tag", "source_cat"]].rename(columns={
        "date": "Date", "label": "Libellé", "amount": "Montant", "category": "Catégorie",
        "vacation_tag": "Vacances", "source_cat": "Origine"}),
    hide_index=True, width="stretch", disabled=["id", "Date", "Libellé", "Montant", "Origine"],
    column_config={
        "id": None,
        "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Montant": st.column_config.NumberColumn(format="%.2f €"),
        "Catégorie": st.column_config.SelectboxColumn(options=cats, required=True),
        "Vacances": st.column_config.SelectboxColumn(options=vac_names),
    }, key="editor")
if st.button("💾 Enregistrer les corrections", type="primary"):
    orig = view.set_index("id")
    changed = []
    for r in ed.itertuples(index=False):
        o = orig.loc[r.id]
        cat_changed = r.Catégorie != o["category"]
        vac = r.Vacances if isinstance(r.Vacances, str) and r.Vacances else None
        vac_changed = vac != (o["vacation_tag"] if isinstance(o["vacation_tag"], str) and o["vacation_tag"] else None)
        if cat_changed or vac_changed:
            changed.append({"tx_id": r.id, "category": r.Catégorie if (cat_changed or o["source_cat"] == "manuel") else None,
                            "vacation": vac})
    if changed:
        get_db().upsert("category_overrides", pd.DataFrame(changed), mode="replace")
        invalidate()
        st.success(f"{len(changed)} correction(s) enregistrée(s).")
        st.rerun()
    else:
        st.info("Aucune modification.")
download_df(t_sel.drop(columns=["month"]).set_index("date"), "operations")
