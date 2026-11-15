"""Bilan d'un mois : où est passé l'argent, comparaison avec la moyenne et l'an dernier."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import bundle, detail_button, empty_state, eur, operations_dialog, plot
from finmon import charts
from finmon.analytics import budget

b = bundle()
st.title("Bilan du mois")
tx = b.tx
if tx.empty:
    empty_state("opérations bancaires")
    st.stop()

types = b.accounts.set_index("id")["type"]
tx = tx[tx["account_id"].map(types).isin(["courant", "autre"])]   # le budget se lit sur courant + carte
months = sorted(tx["month"].unique(), reverse=True)
last_data = tx["date"].max()
# Mois proposé : le dernier mois complet (le mois en cours reste consultable).
default = next((i for i, m in enumerate(months) if m + pd.offsets.MonthEnd(0) <= last_data), 0)
m = st.selectbox("Mois", months, index=default, format_func=charts.mois)
m = pd.Timestamp(m)
partial = m + pd.offsets.MonthEnd(0) > last_data
if partial:
    st.caption(f"Mois incomplet : opérations jusqu'au {last_data:%d/%m/%Y}.")

cur = tx[tx["month"] == m]
prev12 = tx[(tx["month"] < m) & (tx["month"] >= m - pd.DateOffset(months=12))]
n_prev = max(prev12["month"].nunique(), 1)
ly = tx[tx["month"] == m - pd.DateOffset(years=1)]


refunds = st.toggle("Déduire les avoirs carte (remboursements de marchands)", value=False,
                    help="Dépenses = paiements par carte, prélèvements et retraits d'espèces (aucun virement). Activé : les avoirs et annulations "
                         "carte (remboursements de marchands) sont déduits.")
g = budget.global_monthly(tx, deduct_refunds=refunds)
f = g.loc[m] if m in g.index else pd.Series(0.0, index=g.columns)
g12 = g[(g.index < m) & (g.index >= m - pd.DateOffset(months=12))]
fa = g12.mean() if not g12.empty else pd.Series(0.0, index=g.columns)

# ------------------------------------------------------------- KPIs
k = st.columns(4)
k[0].metric("Salaire", eur(f["salaire"]),
            (f"+ {eur(f['exceptionnel'])} exceptionnels" if f["exceptionnel"] else
             f"{eur(f['salaire'] - fa['salaire'], sign=True)} vs moy. 12 mois"), delta_color="off" if f["exceptionnel"] else "normal",
            help="Salaire, plus les revenus exceptionnels saisis dans Vue globale. Les autres entrées sont ignorées.")
k[1].metric("Loyer", eur(f["loyer"]), help="Votre part fixe (colocation).")
k[2].metric("Dépenses hors loyer", eur(f["depenses"]),
            f"{eur(f['depenses'] - fa['depenses'], sign=True)} vs moy. 12 mois", delta_color="inverse")
k[3].metric("Économisé ce mois", eur(f["economise"], sign=True),
            f"{f['taux'] * 100:.0f} % du salaire" if f["taux"] == f["taux"] else None, delta_color="off",
            help="Salaire + revenus exceptionnels − loyer − dépenses hors loyer.")
NOTE = {"depenses": "Paiements par carte, prélèvements et retraits d'espèces du mois, hors loyer : aucun "
                    "virement (émis ou reçu)"
                    + (" ; avoirs carte déduits." if refunds else "."),
        "salaire": "Virements de salaire reçus dans le mois.", "loyer": "Votre part fixe, comptée le 1er du mois."}
for col, part, lab in ((k[0], "salaire", "Salaire"), (k[1], "loyer", "Loyer"), (k[2], "depenses", "Dépenses hors loyer")):
    if detail_button(col, f"dlg_{part}"):
        operations_dialog(f"{lab} — {charts.mois(m)}", budget.global_ops(cur, part, refunds), NOTE[part])

# ------------------------------------------------------------- où va l'argent
st.subheader("Ce qui a été mis de côté")
j = st.columns(3)
j[0].metric("Investi (courtiers)", eur(f["investi"], sign=True),
            help="Virements vers IBKR, Trade Republic, Binance… rapprochés des versements reçus par le courtier.")
j[1].metric("Livrets (net)", eur(f["livrets"], sign=True),
            "versé" if f["livrets"] >= 0 else "retiré des livrets", delta_color="off",
            help="Versements vers les livrets moins retraits des livrets dans le mois : les allers-retours s'annulent.")
for col, part, lab in ((j[0], "investi", "Investi (courtiers)"), (j[1], "livrets", "Livrets (net)")):
    if detail_button(col, f"dlg_{part}"):
        operations_dialog(f"{lab} — {charts.mois(m)}", budget.global_ops(cur, part, refunds))
j[2].metric("Reste sur le compte courant", eur(f["economise"] - f["investi"] - f["livrets"], sign=True),
            help="Économisé − investi − livrets. Négatif : le mois a puisé dans le solde du compte.")

# ------------------------------------------------------------- par catégorie
st.subheader("Dépenses par catégorie")
e_cur = budget.expenses(cur).groupby("category")["spend"].sum()
e_avg = budget.expenses(prev12).groupby("category")["spend"].sum() / n_prev
e_ly = budget.expenses(ly).groupby("category")["spend"].sum()
tab = pd.DataFrame({"Ce mois": e_cur, "Moyenne 12 mois": e_avg, "Même mois l'an dernier": e_ly}).fillna(0.0)
tab = tab[(tab.abs() > 0.5).any(axis=1)]
tab["Écart vs moyenne"] = tab["Ce mois"] - tab["Moyenne 12 mois"]
tab = tab.sort_values("Ce mois", ascending=False)
left, right = st.columns([3, 2])
with left:
    st.dataframe(tab, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="%,.0f €") for c in tab.columns} | {
        "Écart vs moyenne": st.column_config.NumberColumn(format="%+,.0f €")})
with right:
    d = tab["Écart vs moyenne"].sort_values()
    d = d[d.abs() >= 10]
    if not d.empty:
        st.markdown("**Écart à la moyenne**")
        plot(charts.signed_hbar(d.index, d.values), key="delta_cat")

# ------------------------------------------------------------- logement
coloc = cur[cur["category"] == "Loyer & colocation (hors budget)"]
mine = -cur.loc[cur["category"] == "Loyer", "amount"].sum()
if not coloc.empty or mine:
    st.subheader("Logement")
    paid = -coloc.loc[coloc["amount"] < 0, "amount"].sum()
    got = coloc.loc[coloc["amount"] > 0, "amount"].sum()
    l1, l2, l3, l4 = st.columns(4)
    l1.metric("Ma part (dans le budget)", eur(mine),
              help="Montant fixe défini dans data/<profil>/regles.yaml › loyer_fixe.")
    l2.metric("Loyer versé à la propriétaire", eur(paid), help="Hors budget : seulement pour contrôle.")
    l3.metric("Parts reçues des colocataires", eur(got), help="Hors budget : seulement pour contrôle.")
    gap = paid - got - mine
    l4.metric("Écart à régulariser", eur(gap, sign=True),
              "avancé par vous" if gap > 1 else ("reçu en trop" if gap < -1 else "à l'équilibre"), delta_color="off",
              help="Loyer versé − parts reçues − votre part. Positif : les colocataires vous doivent cette somme "
                   "(ou ont payé en avance le mois précédent).")
    hist_c = tx[tx["category"] == "Loyer & colocation (hors budget)"]
    since = hist_c[hist_c["month"] <= m]
    cum = -since["amount"].sum() - (-tx.loc[(tx["category"] == "Loyer") & (tx["month"] <= m)
                                             & (tx["source_cat"] == "loyer fixe"), "amount"].sum())
    st.caption(f"Cumul depuis le début : {eur(cum, sign=True)} "
               "(positif = avancé pour les colocataires). Les virements passés à partir du 25 comptent pour le mois suivant.")
    if not coloc.empty:
        with st.expander("Virements de la colocation ce mois"):
            st.dataframe(coloc.sort_values("date")[["date", "label", "amount"]].rename(
                columns={"date": "Date", "label": "Libellé", "amount": "Montant"}), hide_index=True, width="stretch",
                column_config={"Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                               "Montant": st.column_config.NumberColumn(format="%+,.2f €")})

# ------------------------------------------------------------- plus grosses dépenses
st.subheader("Plus grosses dépenses du mois")
big = budget.expenses(cur).sort_values("spend", ascending=False).head(12)
st.dataframe(big[["date", "merchant", "category", "spend"]].rename(columns={
    "date": "Date", "merchant": "Marchand", "category": "Catégorie", "spend": "Montant"}),
    hide_index=True, width="stretch",
    column_config={"Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                   "Montant": st.column_config.NumberColumn(format="%,.2f €")})

todo = cur[cur["source_cat"] == "défaut"]
if not todo.empty:
    st.info(f"{len(todo)} opération(s) non reconnue(s) ce mois, comptées en « Autres » "
            f"({eur(-todo['amount'].sum(), sign=True)}) : classez-les dans Dépenses › À classer.")

# ------------------------------------------------------------- historique
st.subheader("Mois par mois")
hist = budget.monthly_flows(tx)
inv = -tx[tx["category"] == "Épargne & investissement"].groupby("month")["amount"].sum()
liv = -tx[tx["category"] == "Épargne livrets"].groupby("month")["amount"].sum()
hist = hist.assign(invest=inv, livrets=liv).fillna(0.0).tail(24)
fig = go.Figure()
for col, lab, color in (("income", "Revenus", charts.FIXED["Revenus"]), ("expenses", "Dépenses", charts.FIXED["Dépenses"]),
                        ("invest", "Investi", charts.SERIES[0]), ("livrets", "Livrets (net)", charts.SERIES[3])):
    fig.add_trace(go.Bar(x=hist.index, y=hist[col], name=lab, marker_color=color,
                         hovertemplate="%{y:,.0f} €<extra>" + lab + "</extra>"))
fig.add_vline(x=m, line_dash="dot", line_color=charts.MUTED)
fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05)
plot(charts.layout(fig, 340), key="hist")
