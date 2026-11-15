"""Synthèse du patrimoine : total, évolution, puis répartition cliquable (catégorie > compte > lignes)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from common import bundle, empty_state, eur, get_db, invalidate, pct, period_picker, period_start, plot, show_warnings
from finmon import charts
from finmon.analytics import budget, portfolio

b = bundle()
if not b.has_data or b.networth.empty:
    st.title("Patrimoine")
    empty_state()
    st.stop()

nw = b.networth.copy()
by_bucket = nw.pivot_table(index="date", columns="bucket", values="value", aggfunc="sum").fillna(0.0).sort_index()
total = by_bucket.sum(axis=1)
last = total.index[-1]
ORDER = ["Investissements", "Liquidités", "Épargne réglementée", "Autres actifs"]

# ------------------------------------------------------------- en-tête
head, per = st.columns([3, 2], vertical_alignment="bottom")
with per:
    key = period_picker("home_period", "1A")
start = period_start(key, last, total.index[0])
t0 = total.asof(start)
var = total.iloc[-1] - t0
with head:
    theme.hero("Patrimoine net", eur(total.iloc[-1]), var, f"{eur(var, sign=True)} ({pct(var / t0) if t0 else '—'})",
               f"sur {key}")
show_warnings(b, "home")

pf = portfolio.summary(b.portfolio) if not b.portfolio.accounts.empty else {}

# ------------------------------------------------------------- évolution
view = by_bucket[by_bucket.index >= start]
order = [c for c in ORDER if c in view.columns]
plot(charts.line(view, order, height=340, area=True), key="nw")

# ------------------------------------------------------------- répartition cliquable
st.subheader("Répartition")
st.caption("Cliquez sur une catégorie pour voir les comptes qui la composent, puis sur un compte pour voir son détail.")
cur = nw[nw["date"] == last]
cur = cur[cur["value"].abs() > 0.5]
cats = (cur.groupby("bucket")["value"].sum().reindex([c for c in ORDER if c in set(cur["bucket"])]).dropna()
        .rename("Montant").to_frame())
cats["Part"] = cats["Montant"] / cats["Montant"].sum() * 100
cats["Comptes"] = cur.groupby("bucket")["account_id"].nunique()
cats = cats.reset_index().rename(columns={"bucket": "Catégorie"})

MONEY = st.column_config.NumberColumn(format="%,.0f €")
SHARE = st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100)

left, right = st.columns([2, 3])
with left:
    ev = st.dataframe(cats[["Catégorie", "Montant", "Part", "Comptes"]], hide_index=True, width="stretch",
                      on_select="rerun", selection_mode="single-row", key="cat_sel",
                      column_config={"Montant": MONEY, "Part": SHARE})
    picked = ev.selection.rows[0] if ev.selection.rows else 0
    cat = cats.iloc[picked]["Catégorie"]

PART_LABEL = {"Espèces": "Espèces non investies", "Titres": "Titres", "Solde": "Solde"}
with right:
    acc = cur[cur["bucket"] == cat].copy()
    acc["Nature"] = acc["part"].map(PART_LABEL).fillna("")
    acc = (acc.groupby(["account_id", "name", "institution", "Nature"], dropna=False)["value"].sum()
           .sort_values(ascending=False).reset_index())
    acc["Part"] = acc["value"] / acc["value"].sum() * 100
    st.markdown(f"**{cat}** · {eur(acc['value'].sum())}")
    ev2 = st.dataframe(acc.rename(columns={"name": "Compte", "institution": "Établissement", "value": "Montant"})
                       [["Compte", "Établissement", "Nature", "Montant", "Part"]],
                       hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                       key=f"acc_sel_{cat}", column_config={"Montant": MONEY, "Part": SHARE})
    if cat == "Liquidités":
        st.caption("Les espèces non investies chez un courtier (versées mais pas encore placées, ou issues d'une "
                   "vente) comptent ici, et non dans les investissements.")

# Détail d'un compte
if ev2.selection.rows:
    row = acc.iloc[ev2.selection.rows[0]]
    st.markdown(f"**{row['name']}** · {row['Nature'].lower()}")
    a_id = row["account_id"]
    c = b.portfolio.current
    lines = c[c["account_id"] == a_id] if not c.empty else c
    if row["Nature"] == "Titres" and not lines.empty:
        t = lines.assign(pv=lines["value"] - lines["cost"]).sort_values("value", ascending=False)
        t = pd.DataFrame({"Ligne": t["name"], "Quantité": t["qty"], "PRU": t["pru"], "Cours": t["price"],
                          "Valeur": t["value"], "Plus-value": t["pv"],
                          "Perf.": (t["value"] / t["cost"] - 1) * 100})
        st.dataframe(t, hide_index=True, width="stretch", column_config={
            "Quantité": st.column_config.NumberColumn(format="%.4g"),
            "PRU": st.column_config.NumberColumn(format="%,.2f €"),
            "Cours": st.column_config.NumberColumn(format="%,.2f €"), "Valeur": MONEY,
            "Plus-value": st.column_config.NumberColumn(format="%+,.0f €"),
            "Perf.": st.column_config.NumberColumn(format="%+.1f %%")})
    elif row["Nature"] == PART_LABEL["Espèces"]:
        st.write(f"Espèces non investies sur ce compte : **{eur(row['value'])}**. D'où elles viennent :")
        KIND = {"deposit": "Versements", "withdrawal": "Retraits", "buy": "Achats", "sell": "Ventes",
                "dividend": "Dividendes", "interest": "Intérêts", "fee": "Frais", "tax": "Impôts et taxes",
                "reward": "Récompenses"}
        ops = get_db().read("SELECT kind, SUM(amount) AS montant, COUNT(*) AS n FROM trades "
                            "WHERE account_id = ? GROUP BY kind", [a_id])
        ops = ops[ops["kind"].isin(KIND)].assign(Mouvement=lambda d: d["kind"].map(KIND))
        ops = ops.set_index("kind").reindex([k_ for k_ in KIND if k_ in set(ops["kind"])]).reset_index()
        st.dataframe(ops.rename(columns={"montant": "Montant", "n": "Opérations"})[["Mouvement", "Opérations", "Montant"]],
                     hide_index=True, width="content",
                     column_config={"Montant": st.column_config.NumberColumn(format="%+,.2f €")})
        st.caption(f"Solde = somme de ces mouvements ({eur(ops['montant'].sum(), 2)}).")
    else:
        st.write(f"Solde au {last:%d/%m/%Y} : **{eur(row['value'])}**.")
        rate = b.accounts.set_index("id").get("rate")
        if rate is not None and a_id in rate.index and rate[a_id] == rate[a_id]:
            st.caption(f"Taux {rate[a_id]:.2f} % par an · intérêts estimés sur 12 mois : "
                       f"{eur(row['value'] * rate[a_id] / 100)}".replace(".", ","))

# ------------------------------------------------------------- plan d'épargne entreprise
pee_accounts = b.accounts[b.accounts["type"] == "epargne_salariale"]
for acc_row in pee_accounts.itertuples():
    import uuid as _uuid
    from datetime import date as _date

    _db = get_db()
    st.subheader(acc_row.name)
    contrib = _db.read("SELECT * FROM manual_contributions WHERE account_id = ? ORDER BY date", [acc_row.id])
    vals = b.balance_snapshots[b.balance_snapshots["account_id"] == acc_row.id].sort_values("date")
    value = float(vals["balance"].iloc[-1]) if not vals.empty else None
    invested = float(contrib["amount"].sum()) if not contrib.empty else 0.0
    gain = value - invested if value is not None and invested > 0 else None
    m1, m2, m3 = st.columns(3)
    m1.metric("Valeur actuelle", eur(value) if value is not None else "—",
              f"au {pd.Timestamp(vals['date'].iloc[-1]):%d/%m/%Y}" if value is not None else "à renseigner", delta_color="off")
    m2.metric("Total versé", eur(invested), f"{len(contrib)} versement(s)", delta_color="off")
    m3.metric("Plus-value", eur(gain, sign=True) if gain is not None else "—",
              pct(gain / invested) if gain is not None else "ajoutez vos versements",
              delta_color="normal" if gain is not None else "off",
              help="Valeur actuelle − total versé (versements − retraits).")
    a1, a2 = st.columns(2)
    with a1.form(f"pee_contrib_{acc_row.id}", clear_on_submit=True):
        st.markdown("**Ajouter un versement**")
        c1_, c2_, c3_ = st.columns(3)
        dc = c1_.date_input("Date", value=_date.today(), max_value=_date.today(), format="DD/MM/YYYY")
        ac = c2_.number_input("Montant (€)", step=50.0, format="%.2f",
                              help="Montant investi (négatif pour un retrait / déblocage).")
        tc = c3_.selectbox("Origine", ["Intéressement", "Participation", "Abondement", "Versement personnel", "Retrait"])
        if st.form_submit_button("Ajouter") and ac:
            amount = -abs(ac) if tc == "Retrait" else ac
            _db.upsert("manual_contributions", pd.DataFrame([{"id": _uuid.uuid4().hex[:10], "account_id": acc_row.id,
                                                              "date": dc.isoformat(), "amount": amount, "label": tc}]))
            invalidate()
            st.rerun()
    with a2.form(f"pee_value_{acc_row.id}", clear_on_submit=True):
        st.markdown("**Mettre à jour la valeur**")
        v1_, v2_ = st.columns(2)
        dv = v1_.date_input("Date", value=_date.today(), max_value=_date.today(), format="DD/MM/YYYY")
        vv = v2_.number_input("Valeur actuelle (€)", min_value=0.0, step=100.0, format="%.2f")
        if st.form_submit_button("Enregistrer") and vv:
            _db.upsert("balance_snapshots", pd.DataFrame([{"account_id": acc_row.id, "date": dv.isoformat(),
                                                           "balance": vv, "source": "manuel"}]), mode="replace")
            invalidate()
            st.rerun()
    if not contrib.empty or len(vals) > 1:
        with st.expander("Historique : versements et valeurs"):
            if len(vals) >= 1 and not contrib.empty:
                days_ = pd.date_range(min(pd.to_datetime(contrib["date"]).min(), pd.to_datetime(vals["date"]).min()),
                                      pd.Timestamp(_date.today()), freq="D")
                cum = contrib.assign(d=pd.to_datetime(contrib["date"])).groupby("d")["amount"].sum() \
                    .reindex(days_).fillna(0.0).cumsum()
                vs = vals.assign(d=pd.to_datetime(vals["date"])).set_index("d")["balance"]
                vs = vs[~vs.index.duplicated(keep="last")].reindex(days_).ffill()
                plot(charts.line(pd.DataFrame({"Valeur": vs, "Total versé": cum}), ["Valeur", "Total versé"],
                                 height=260, dash={"Total versé": "dot"},
                                 colors={"Valeur": charts.SERIES[0], "Total versé": charts.MUTED}), key=f"pee_{acc_row.id}")
            if not contrib.empty:
                ed_c = st.data_editor(contrib.assign(Supprimer=False)[["Supprimer", "id", "date", "label", "amount"]]
                                      .rename(columns={"date": "Date", "label": "Origine", "amount": "Montant"}),
                                      hide_index=True, width="stretch", key=f"pee_ed_{acc_row.id}",
                                      disabled=["id", "Date", "Origine", "Montant"],
                                      column_config={"id": None, "Montant": st.column_config.NumberColumn(format="%+,.2f €")})
                if st.button("Supprimer la sélection", key=f"pee_del_{acc_row.id}"):
                    for r_ in ed_c[ed_c["Supprimer"]].itertuples(index=False):
                        _db.execute("DELETE FROM manual_contributions WHERE id = ?", [r_.id])
                    invalidate()
                    st.rerun()

# ------------------------------------------------------------- valeurs saisies à la main
manual_acc = b.accounts[b.accounts["type"].isin(["livret", "autre"])
                        & b.accounts["id"].str.startswith("manuel:")]
if not manual_acc.empty:
    missing = not set(manual_acc["id"]) <= set(b.balance_snapshots["account_id"])
    with st.expander("Mettre à jour une valeur saisie à la main (livrets…)", expanded=missing):
        bs = b.balance_snapshots.sort_values("date").groupby("account_id").tail(1).set_index("account_id")
        from datetime import date as _date

        rows = pd.DataFrame({"id": manual_acc["id"], "Compte": manual_acc["name"],
                             "Valeur actuelle": manual_acc["id"].map(bs["balance"]),
                             "Au": pd.to_datetime(manual_acc["id"].map(bs["date"])),
                             "Nouvelle valeur": manual_acc["id"].map(bs["balance"]).astype(float),
                             "Date": pd.Timestamp(_date.today())})
        ed_v = st.data_editor(rows, hide_index=True, width="stretch", key="manual_values",
                              disabled=["id", "Compte", "Valeur actuelle", "Au"],
                              column_config={"id": None,
                                             "Valeur actuelle": st.column_config.NumberColumn(format="%,.2f €"),
                                             "Au": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                             "Nouvelle valeur": st.column_config.NumberColumn(format="%,.2f €", min_value=0.0),
                                             "Date": st.column_config.DateColumn(format="DD/MM/YYYY")})
        if st.button("Enregistrer les valeurs", type="primary", key="save_manual_values"):
            n = 0
            for r in ed_v.itertuples(index=False):
                new_v, old_v = r[4], r[2]
                if new_v is not None and new_v == new_v and (old_v != old_v or abs(new_v - old_v) > 0.005):
                    get_db().upsert("balance_snapshots", pd.DataFrame([{
                        "account_id": r.id, "date": pd.Timestamp(r.Date).date().isoformat(), "balance": float(new_v),
                        "source": "manuel"}]), mode="replace")
                    n += 1
            if n:
                from common import invalidate

                invalidate()
                st.rerun()
            st.info("Aucune valeur modifiée.")

# ------------------------------------------------------------- performance & budget
st.subheader("Indicateurs")
flows = budget.monthly_flows(b.tx)
full_months = flows[flows.index < pd.Timestamp(last.year, last.month, 1)]
last12 = full_months.tail(12)
k = st.columns(4)
if pf:
    k[0].metric("Plus-value investissements", eur(pf.get("pnl_total"), sign=True),
                help="Valeur actuelle − argent net versé (latent + réalisé + dividendes + intérêts − frais).")
    k[1].metric("Performance (TWR)", pct(pf["twr"]),
                f"TRI {pct(pf['xirr'])} / an" if pf.get("xirr") is not None else None,
                help="TWR : performance indépendante des versements. TRI : rendement annualisé, versements compris.")
if not full_months.empty:
    lm = full_months.iloc[-1]
    k[2].metric(f"Dépenses {charts.mois(full_months.index[-1])}", eur(lm["expenses"]),
                f"{eur(lm['expenses'] - last12['expenses'].mean(), sign=True)} vs moy. 12 mois", delta_color="inverse")
    rate12 = last12["savings"].sum() / last12["income"].sum() if last12["income"].sum() else None
    k[3].metric("Taux d'épargne 12 mois", pct(rate12, 0, sign=False))
else:
    k[2].metric("Dépenses", "—", help="Importez les exports de compte courant Boursorama.")
    k[3].metric("Taux d'épargne", "—")

if not full_months.empty:
    st.subheader("Revenus et dépenses — 12 derniers mois")
    m = last12.rename(columns={"income": "Revenus", "expenses": "Dépenses"})
    fig = go.Figure()
    for c_ in ["Revenus", "Dépenses"]:
        fig.add_trace(go.Bar(x=m.index, y=m[c_], name=c_, marker_color=charts.FIXED[c_],
                             hovertemplate="%{y:,.0f} €<extra>" + c_ + "</extra>"))
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    plot(charts.layout(fig, 300), key="ie")
