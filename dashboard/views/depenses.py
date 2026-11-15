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
import re as _re  # noqa: E402

from finmon import config as _config  # noqa: E402

cats = sorted(budget.category_types().keys())
vac_names = [""] + b.vacations["name"].tolist()
real = t[~t["source_cat"].isin(["loyer fixe", "ajustement", "étalé"])]
todo = real[real["source_cat"] == "défaut"]
tab_todo, tab_all = st.tabs([f"À classer ({len(todo)})", "Toutes les opérations"])

with tab_todo:
    st.caption("Opérations qu'aucune règle ne reconnaît : elles sont comptées en « Autres dépenses » "
               "(ou « Autres revenus »). Choisissez une catégorie par marchand dans le menu déroulant : "
               "toutes ses opérations sont reclassées, et il sera reconnu automatiquement aux prochains imports.")
    if todo.empty:
        st.success("Tout est classé.")
    else:
        g = (todo.assign(sens=todo["amount"].lt(0).map({True: "debit", False: "credit"}))
             .groupby(["merchant", "sens"])
             .agg(Opérations=("id", "size"), Total=("amount", "sum"), Dernière=("date", "max"),
                  Exemple=("label", "first"), Catégorie=("category", "first"))
             .reset_index().sort_values("Total"))
        ged = st.data_editor(
            g.rename(columns={"merchant": "Marchand"}), hide_index=True, width="stretch", key="todo_editor",
            disabled=["Marchand", "sens", "Opérations", "Total", "Dernière", "Exemple"],
            column_config={
                "sens": None,
                "Catégorie": st.column_config.SelectboxColumn(options=cats, required=True, width="medium"),
                "Total": st.column_config.NumberColumn(format="%+,.2f €"),
                "Dernière": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Exemple": st.column_config.TextColumn(width="large")})
        if st.button("Enregistrer le classement", type="primary", key="save_todo"):
            n = 0
            for r in ged.itertuples(index=False):
                default = "Autres dépenses" if r.sens == "debit" else "Autres revenus"
                if r.Catégorie != default and len(str(r.Marchand).strip()) >= 2:
                    _config.add_auto_rule(_re.escape(str(r.Marchand).strip()), r.Catégorie, r.sens)
                    n += 1
            if n:
                invalidate()
                st.success(f"{n} marchand(s) classé(s) : règles enregistrées.")
                st.rerun()
            else:
                st.info("Aucune catégorie modifiée.")

with tab_all:
    st.caption("Corrigez une catégorie ou rattachez une dépense à des vacances (ex. billet d'avion acheté à "
               "l'avance). Cochez « Règle » pour appliquer la catégorie à tout le marchand, y compris aux "
               "prochains imports.")
    q = st.text_input("Rechercher un libellé", "")
    view = t_sel[~t_sel["source_cat"].isin(["loyer fixe", "ajustement", "étalé"])].sort_values("date", ascending=False)
    if q:
        view = view[view["label"].str.contains(q, case=False, regex=False)]
    view = view.head(500)
    ed = st.data_editor(
        view.assign(part=(view["factor"].fillna(1.0) * 100).round(1), full=view["amount_full"].fillna(view["amount"]))[
            ["id", "date", "label", "merchant", "full", "part", "category", "vacation_tag", "source_cat"]].rename(columns={
            "date": "Date", "label": "Libellé", "merchant": "Marchand", "full": "Montant", "part": "Ma part (%)",
            "category": "Catégorie", "vacation_tag": "Vacances", "source_cat": "Origine"}).assign(Règle=False),
        hide_index=True, width="stretch", disabled=["id", "Date", "Libellé", "Marchand", "Montant", "Origine"],
        column_config={
            "id": None,
            "Règle": st.column_config.CheckboxColumn(
                help="Coché : la catégorie choisie s'appliquera automatiquement à toutes les opérations de ce "
                     "marchand, y compris aux prochains imports."),
            "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Montant": st.column_config.NumberColumn(format="%.2f €"),
            "Ma part (%)": st.column_config.NumberColumn(
                min_value=0.0, max_value=100.0, step=5.0, format="%.0f %%",
                help="Part de la dépense qui vous revient (50 % pour une dépense partagée en deux). "
                     "Seule cette part est comptée dans le budget."),
            "Catégorie": st.column_config.SelectboxColumn(options=cats, required=True),
            "Vacances": st.column_config.SelectboxColumn(options=vac_names),
        }, key="editor")
    if st.button("Enregistrer les corrections", type="primary"):
        orig = view.set_index("id")
        changed = []
        for r in ed.itertuples(index=False):
            o = orig.loc[r.id]
            cat_changed = r.Catégorie != o["category"]
            vac = r.Vacances if isinstance(r.Vacances, str) and r.Vacances else None
            vac_changed = vac != (o["vacation_tag"] if isinstance(o["vacation_tag"], str) and o["vacation_tag"] else None)
            part = r[5]
            old_part = float(o["factor"]) * 100 if o["factor"] == o["factor"] else 100.0
            part_changed = part is not None and part == part and abs(part - old_part) > 0.01
            if cat_changed or vac_changed or part_changed:
                ch = {"tx_id": r.id}
                if cat_changed:
                    ch["category"] = r.Catégorie
                if vac_changed:
                    ch["vacation"] = vac
                if part_changed:
                    ch["factor"] = part / 100
                changed.append(ch)
        rules = 0
        for r in ed[ed["Règle"]].itertuples(index=False):
            merchant = str(r.Marchand or "").strip()
            if len(merchant) >= 3:
                o = orig.loc[r.id]
                _config.add_auto_rule(_re.escape(merchant), r.Catégorie, "debit" if o["amount"] < 0 else "credit")
                rules += 1
        if changed or rules:
            from finmon.db import set_override

            for c in changed:
                set_override(get_db(), c.pop("tx_id"), **{k: v for k, v in c.items() if k != "factor" or v is not None})
            invalidate()
            st.success(f"{len(changed)} correction(s) enregistrée(s)" + (f", {rules} règle(s) créée(s)" if rules else "") + ".")
            st.rerun()
        else:
            st.info("Aucune modification.")
download_df(t_sel.drop(columns=["month"]).set_index("date"), "operations")
