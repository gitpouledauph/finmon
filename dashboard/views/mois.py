"""Monthly review: one month against an average, last year or any other month."""
import pandas as pd
import streamlit as st

import theme
from common import adjustments_editor, bundle, detail_button, empty_state, en, eur, operations_dialog, plot, signed_style
from finmon import charts
from finmon.analytics import budget

b = bundle()
tx = b.tx
if tx.empty:
    st.title("Monthly review")
    empty_state("bank transactions")
    st.stop()

types = b.accounts.set_index("id")["type"]
tx = tx[tx["account_id"].map(types).isin(["courant", "autre"])]
last_data = budget.last_real_date(tx)
months = sorted((pd.Timestamp(m) for m in tx["month"].unique() if pd.Timestamp(m) <= last_data), reverse=True)
default = next((i for i, m in enumerate(months) if m + pd.offsets.MonthEnd(0) <= last_data), 0)

head, c1, c2, c3 = st.columns([1.5, 1.1, 1.4, 1], vertical_alignment="bottom")
head.title("Monthly review")
m = c1.selectbox("Month", months, index=default, format_func=lambda d: d.strftime("%B %Y"))
AVG, LY = "12-month average", "Same month last year"
other_months = [x for x in months if x != m]
cmp = c2.selectbox("Compare with", [AVG, LY] + other_months,
                   format_func=lambda x: x if isinstance(x, str) else x.strftime("%B %Y"))
refunds = c3.toggle("Net card refunds", value=False)

g = budget.global_monthly(tx, deduct_refunds=refunds)
f = g.loc[m] if m in g.index else pd.Series(0.0, index=g.columns)
cur = tx[tx["month"] == m]
if cmp == AVG:
    first_salary = g.index[g["salaire"] > 0].min() if (g["salaire"] > 0).any() else g.index.min()
    ref_months = [x for x in g.index if m - pd.DateOffset(months=12) <= x < m and x >= first_salary]
    cmp_label = "12-m avg"
elif cmp == LY:
    ref_months = [m - pd.DateOffset(years=1)]
    cmp_label = (m - pd.DateOffset(years=1)).strftime("%b %Y")
else:
    ref_months = [cmp]
    cmp_label = cmp.strftime("%b %Y")
gr = g.reindex(ref_months).fillna(0.0)
fa = gr.mean() if len(gr) else pd.Series(0.0, index=g.columns)
ref_tx = tx[tx["month"].isin(ref_months)]
n_ref = max(len(ref_months), 1)
if m + pd.offsets.MonthEnd(0) > last_data:
    st.caption(f"Partial month · data to {last_data:%d %b %Y}")

# ------------------------------------------------------------- KPIs
k = st.columns(4)
k[0].metric("Income", eur(f["salaire"] + f["exceptionnel"]),
            f"{eur(f['salaire'] + f['exceptionnel'] - fa['salaire'] - fa['exceptionnel'], sign=True)} vs {cmp_label}")
k[1].metric("Rent", eur(f["loyer"]))
k[2].metric("Spending", eur(f["depenses"]), f"{eur(f['depenses'] - fa['depenses'], sign=True)} vs {cmp_label}",
            delta_color="inverse")
k[3].metric("Saved", eur(f["economise"], sign=True),
            f"{f['taux'] * 100:.0f} % of income" if f["taux"] == f["taux"] else None, delta_color="off")
for col, part, lab in ((k[0], "salaire", "Salary"), (k[1], "loyer", "Rent"), (k[2], "depenses", "Spending")):
    if detail_button(col, f"dlg_{part}", "Details"):
        operations_dialog(f"{lab} · {m:%B %Y}", budget.global_ops(cur, part, refunds))
if f["exceptionnel"] and detail_button(k[3], "dlg_exc", "Other income"):
    operations_dialog(f"Other income · {m:%B %Y}", budget.global_ops(cur, "exceptionnel", refunds))

j = st.columns(3)
j[0].metric("Invested", eur(f["investi"], sign=True))
j[1].metric("Savings accounts (net)", eur(f["livrets"], sign=True))
j[2].metric("Current account change", eur(f["economise"] - f["investi"] - f["livrets"], sign=True))
for col, part, lab in ((j[0], "investi", "Invested"), (j[1], "livrets", "Savings accounts")):
    if detail_button(col, f"dlg_{part}", "Details"):
        operations_dialog(f"{lab} · {m:%B %Y}", budget.global_ops(cur, part, refunds))

# ------------------------------------------------------------- by category
ops_cur = budget.global_ops(cur, "depenses", refunds)
ops_ref = budget.global_ops(ref_tx, "depenses", refunds)
a = (-ops_cur.groupby("category")["amount"].sum())
r = (-ops_ref.groupby("category")["amount"].sum()) / n_ref
tab = pd.DataFrame({"this": a, "ref": r}).fillna(0.0)
tab = tab[(tab.abs() > 0.5).any(axis=1)].sort_values("this", ascending=False)
tab.index = [en(c) for c in tab.index]
tab["delta"] = tab["this"] - tab["ref"]
this_label = m.strftime("%b %Y")

theme.section(f"Spending by category · {this_label} vs {cmp_label}")
l, rr = st.columns([1.25, 1])
with l:
    plot(charts.grouped_hbar(tab.index, {this_label: tab["this"].values, cmp_label: tab["ref"].values},
                             colors={this_label: charts.CAT[0], cmp_label: "#4a5263"},
                             height=max(260, 34 * len(tab) + 60)), key="cmp_bars")
with rr:
    d = tab["delta"].sort_values(ascending=False)
    d = d[d.abs() >= 5]
    plot(charts.diverging_hbar(d.index, d.values, height=max(260, 34 * len(tab) + 60), invert=True), key="cmp_delta")

t = pd.DataFrame({"Category": tab.index, this_label: tab["this"].values, cmp_label: tab["ref"].values,
                  "Δ": tab["delta"].values,
                  "Δ %": (tab["delta"] / tab["ref"].where(tab["ref"] > 0) * 100).values})
st.dataframe(signed_style(t, []).map(lambda v: f"color: {charts.BAD}" if v > 0 else (f"color: {charts.GOOD}" if v < 0 else ""),
                                     subset=["Δ", "Δ %"]).format({this_label: "{:,.0f} €", cmp_label: "{:,.0f} €",
                                                                   "Δ": "{:+,.0f} €", "Δ %": "{:+.0f} %"}, na_rep="—"),
             hide_index=True, width="stretch")

# ------------------------------------------------------------- top expenses
l2, r2 = st.columns([1.4, 1])
with l2:
    theme.section("Largest expenses")
    big = ops_cur.assign(spend=-ops_cur["amount"]).sort_values("spend", ascending=False).head(10)
    st.dataframe(pd.DataFrame({"Date": big["date"].dt.strftime("%d %b"), "Merchant": big["merchant"],
                               "Category": big["category"].map(en), "Amount": big["spend"]}),
                 hide_index=True, width="stretch", column_config={"Amount": st.column_config.NumberColumn(format="%,.2f €")})
with r2:
    coloc = cur[cur["category"] == "Loyer & colocation (hors budget)"]
    if not coloc.empty or f["loyer"]:
        theme.section("Housing · shared flat")
        paid = -coloc.loc[coloc["amount"] < 0, "amount"].sum()
        got = coloc.loc[coloc["amount"] > 0, "amount"].sum()
        gap = paid - got - f["loyer"]
        h = pd.DataFrame({"": ["Paid to landlord", "Received from flatmates", "My share", "Balance"],
                          "Amount": [paid, got, f["loyer"], gap]})
        st.dataframe(h, hide_index=True, width="stretch",
                     column_config={"Amount": st.column_config.NumberColumn(format="%,.2f €")})

todo = cur[cur["source_cat"] == "défaut"]
if not todo.empty:
    st.caption(f"{len(todo)} unclassified transaction(s) · {eur(-todo['amount'].sum(), sign=True)} · Spending › To classify")

with st.expander("Manual adjustments", icon=":material/tune:"):
    adjustments_editor([pd.Timestamp(x) for x in tx["month"].unique()], "mois", default_month=m)
