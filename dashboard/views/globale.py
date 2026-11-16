"""Cash flow: income, rent, spending and savings by month or year, with editable inflow/outflow ledgers."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from common import adjustments_editor, bundle, empty_state, eur, get_db, invalidate, operations_dialog, plot
from finmon import charts
from finmon.analytics import budget
from finmon.db import set_override

b = bundle()
tx = b.tx
if tx.empty:
    st.title("Cash flow")
    empty_state("bank transactions")
    st.stop()
types = b.accounts.set_index("id")["type"]
tx = tx[tx["account_id"].map(types).isin(["courant", "autre"])]

head, c1, c2, c3 = st.columns([1.6, 1, 1.5, 1.1], vertical_alignment="bottom")
head.title("Cash flow")
gran = c1.segmented_control("View", ["Month", "Year"], default="Month", label_visibility="collapsed") or "Month"
span = c2.segmented_control("Period", ["Since 1st salary", "12 m", "24 m"], default="Since 1st salary",
                            label_visibility="collapsed") or "Since 1st salary"
refunds = c3.toggle("Net card refunds", value=False)

g_all = budget.global_monthly(tx, deduct_refunds=refunds)
last_data = budget.last_real_date(tx)
g = g_all[g_all.index + pd.offsets.MonthEnd(0) <= last_data]
g = g[(g["salaire"] != 0) | (g["depenses"] != 0)]
if span == "Since 1st salary":
    first = g.index[g["salaire"] > 0].min() if (g["salaire"] > 0).any() else g.index.min()
    g = g[g.index >= first]
else:
    g = g.tail(12 if span == "12 m" else 24)
if g.empty:
    st.info("No complete month yet.")
    st.stop()

COLS = ["salaire", "exceptionnel", "loyer", "depenses", "economise", "investi", "livrets"]
if gran == "Year":
    view = g.groupby(g.index.year)[COLS].sum()
    rev = view["salaire"] + view["exceptionnel"]
    view["taux"] = view["economise"] / rev.where(rev > 0)
    nmonths = g.groupby(g.index.year).size()
    xs = [f"{y}" + (f" · {n}m" if n < 12 else "") for y, n in zip(view.index, nmonths)]
else:
    view = g
    xs = [d.strftime("%b %y") for d in view.index]

tot = g[COLS].sum()
n = len(g)
income_tot = tot["salaire"] + tot["exceptionnel"]
k = st.columns(5)
k[0].metric("Income / month", eur(income_tot / n), f"salary {eur(tot['salaire'] / n)}", delta_color="off")
k[1].metric("Rent / month", eur(tot["loyer"] / n))
k[2].metric("Spending / month", eur(tot["depenses"] / n))
k[3].metric("Saved / month", eur(tot["economise"] / n, sign=True))
k[4].metric("Savings rate", f"{tot['economise'] / income_tot * 100:.0f} %" if income_tot else "—", f"{n} months",
            delta_color="off")

# ------------------------------------------------------------- income allocation
theme.section("Income allocation", "rent + spending + saved = income")
C = {"Rent": charts.CAT[3], "Spending": charts.CAT[1], "Saved": charts.CAT[2]}
fig = go.Figure()
for col, lab in (("loyer", "Rent"), ("depenses", "Spending"), ("economise", "Saved")):
    fig.add_trace(go.Bar(x=xs, y=view[col], name=lab, marker=dict(color=C[lab], line=dict(width=0)),
                         hovertemplate="%{y:,.0f} €<extra>" + lab + "</extra>"))
fig.add_trace(go.Scatter(x=xs, y=view["salaire"] + view["exceptionnel"], name="Income", mode="lines+markers",
                         line=dict(color=charts.INK, width=1.6), marker=dict(size=6),
                         hovertemplate="%{y:,.0f} €<extra>Income</extra>"))
fig.update_layout(barmode="relative", bargap=0.3)
fig = charts.layout(fig, 360)
fig.update_xaxes(type="category")
plot(fig, key="split")

l, r = st.columns(2)
with l:
    theme.section("Savings rate")
    vals = (view["taux"] * 100).fillna(0)
    fig = go.Figure(go.Bar(x=xs, y=vals, marker_color=[charts.GOOD if v >= 0 else charts.BAD for v in vals],
                           hovertemplate="%{y:.0f} %<extra></extra>"))
    avg = tot["economise"] / income_tot * 100 if income_tot else None
    if avg is not None:
        fig.add_hline(y=avg, line_dash="dot", line_color=charts.INK_MUTED, annotation_text=f"avg {avg:.0f} %",
                      annotation_position="top left", annotation_font_color=charts.INK_MUTED)
    fig = charts.layout(fig, 280, legend=False, yfmt=".0f", ysuffix=" %")
    fig.update_xaxes(type="category")
    plot(fig, key="rate")
with r:
    theme.section("Cumulative")
    cum = pd.DataFrame({"Saved": g["economise"].cumsum(), "Invested": g["investi"].cumsum(),
                        "Savings accounts (net)": g["livrets"].cumsum()})
    plot(charts.line(cum, list(cum.columns), height=280,
                     colors={"Saved": charts.CAT[2], "Invested": charts.CAT[0], "Savings accounts (net)": charts.CAT[3]}),
         key="cum")

# ------------------------------------------------------------- detail
theme.section("Detail", "select a row to open its spending")
table = pd.DataFrame({
    "Period": xs, "Salary": view["salaire"].values, "Other income": view["exceptionnel"].values,
    "Rent": view["loyer"].values, "Spending": view["depenses"].values, "Saved": view["economise"].values,
    "Rate": (view["taux"] * 100).values, "Invested": view["investi"].values, "Savings acc.": view["livrets"].values,
}).iloc[::-1].reset_index(drop=True)
money = st.column_config.NumberColumn(format="%,.0f €")
sel_ev = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                      key=f"glob_sel_{gran}", column_config={
                          "Salary": money, "Other income": money, "Rent": money, "Spending": money,
                          "Saved": st.column_config.NumberColumn(format="%+,.0f €"),
                          "Rate": st.column_config.NumberColumn(format="%.0f %%"),
                          "Invested": st.column_config.NumberColumn(format="%+,.0f €"),
                          "Savings acc.": st.column_config.NumberColumn(format="%+,.0f €")})
if sel_ev.selection.rows:
    i = sel_ev.selection.rows[0]
    per = list(view.index)[::-1][i]
    part_tx = tx[tx["month"].dt.year == per] if gran == "Year" else tx[tx["month"] == per]
    title = f"Spending · {per}" if gran == "Year" else f"Spending · {pd.Timestamp(per):%B %Y}"
    if st.session_state.get("_glob_last") != (gran, i):
        st.session_state["_glob_last"] = (gran, i)
        operations_dialog(title, budget.global_ops(part_tx, "depenses", refunds))

# ------------------------------------------------------------- ledgers
db = get_db()
years = sorted(tx["date"].dt.year.unique(), reverse=True)
tab_in, tab_out, tab_smooth, tab_adj = st.tabs(["Inflows", "Outflows", "Smoothing", "Manual adjustments"])

MODES = {"Default": None, "Income": "income", "Smooth over months": "smooth", "Deduct from spending": "offset",
         "Ignore": "ignore"}
MODE_LABEL = {v: k for k, v in MODES.items() if v}

with tab_in:
    yi = st.segmented_control("Year", years, default=years[0], key="in_year", label_visibility="collapsed") or years[0]
    base = b.tx[b.tx["account_id"].map(types).isin(["courant"]) & (b.tx["date"].dt.year == yi)]
    synthetic = base["id"].astype(str).str.startswith(("spread-", "smooth-", "adj-", "loyer-fixe"))
    raw = base[~synthetic & (((base["amount"] > 0) & ~base["category"].isin(
        ["Épargne livrets", "Épargne & investissement", "Virements internes", "Loyer & colocation (hors budget)"]))
        | base["source_cat"].isin(["traitement", "étalé"]))].copy()
    treat = db.read("SELECT * FROM income_treatment").set_index("tx_id")
    counted = {budget.INCOME_MAIN: "Salary", budget.BONUS: "Bonus", budget.KEPT_INCOME: "Income",
               budget.OFFSET_INFLOW: "Deducts spending", budget.HEALTH_REFUND: "Deducts spending",
               budget.IGNORED: "Ignored / smoothed", budget.SPREAD: "Smoothed"}

    def _tr(i, col, default):
        if i in treat.index:
            v = treat.loc[i, col]
            if v is not None and v == v:
                return v
        return default

    led = pd.DataFrame({
        "id": raw["id"], "Date": raw["date"], "Label": raw["label"], "Amount": raw["amount"],
        "Counted as": [("Smoothed (rule)" if sc == "étalé" else counted.get(c, "Not counted"))
                       for c, sc in zip(raw["category"], raw["source_cat"])],
        "Treatment": [MODE_LABEL.get(_tr(i, "mode", None), "Default") for i in raw["id"]],
        "Months": [int(_tr(i, "months", 12)) for i in raw["id"]],
        "Start": [str(_tr(i, "start", pd.Timestamp(d).strftime("%Y-%m"))) for i, d in zip(raw["id"], raw["date"])],
    }).sort_values("Amount", ascending=False)
    led["Start"] = led["Start"].astype("string")
    led["Months"] = led["Months"].astype("Int64")
    led_ed = st.data_editor(led, hide_index=True, width="stretch", key=f"in_ed_{yi}",
                            disabled=["id", "Date", "Label", "Amount", "Counted as"],
                            column_config={"id": None, "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                           "Amount": st.column_config.NumberColumn(format="%,.2f €"),
                                           "Treatment": st.column_config.SelectboxColumn(options=list(MODES), required=True),
                                           "Months": st.column_config.NumberColumn(min_value=1, max_value=36, step=1),
                                           "Start": st.column_config.TextColumn(help="First month, YYYY-MM")})
    if st.button("Save inflows", type="primary", key="save_in"):
        for rr in led_ed.itertuples(index=False):
            mode = MODES[rr.Treatment]
            if mode is None:
                db.execute("DELETE FROM income_treatment WHERE tx_id = ?", [rr.id])
            else:
                db.upsert("income_treatment", pd.DataFrame([{"tx_id": rr.id, "mode": mode, "months": int(rr.Months or 1),
                                                             "start": str(rr.Start)[:7]}]), mode="replace")
        invalidate()
        st.rerun()

with tab_out:
    yo = st.segmented_control("Year", years, default=years[0], key="out_year", label_visibility="collapsed") or years[0]
    outs = budget.global_ops(b.tx[b.tx["date"].dt.year == yo], "depenses", refunds)
    outs = outs[~outs["id"].astype(str).str.startswith(("adj-", "spread-", "smooth-", "loyer-fixe"))]
    cats = sorted(budget.category_types())
    full = outs["amount_full"].fillna(outs["amount"]) if "amount_full" in outs else outs["amount"]
    ol = pd.DataFrame({"id": outs["id"], "Date": outs["date"], "Merchant": outs["merchant"], "Category": outs["category"],
                       "Amount": full, "Share %": (outs["factor"].fillna(1.0) * 100).round(1),
                       "Exclude": outs["factor"].fillna(1.0) == 0}).sort_values("Date", ascending=False)
    ol_ed = st.data_editor(ol, hide_index=True, width="stretch", key=f"out_ed_{yo}", height=460,
                           disabled=["id", "Date", "Merchant", "Amount"],
                           column_config={"id": None, "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                          "Amount": st.column_config.NumberColumn(format="%+,.2f €"),
                                          "Category": st.column_config.SelectboxColumn(options=cats, required=True),
                                          "Share %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=5.0,
                                                                                   format="%.0f %%")})
    if st.button("Save outflows", type="primary", key="save_out"):
        before = ol.set_index("id")
        for rr in ol_ed.itertuples(index=False):
            o = before.loc[rr.id]
            share = 0.0 if rr.Exclude else (rr[5] or 0) / 100
            fields = {}
            if rr.Category != o["Category"]:
                fields["category"] = rr.Category
            if abs(share - (0.0 if o["Exclude"] else o["Share %"] / 100)) > 1e-6:
                fields["factor"] = share
            if fields:
                set_override(db, rr.id, **fields)
        invalidate()
        st.rerun()

with tab_smooth:
    all_months = sorted({pd.Timestamp(x) for x in tx["month"].unique()}
                        | {pd.Timestamp(last_data).to_period("M").to_timestamp() + pd.DateOffset(months=k) for k in range(1, 13)})
    real = b.tx[b.tx["account_id"].map(types).isin(["courant", "autre"])
                & ~b.tx["id"].astype(str).str.startswith(("spread-", "smooth-", "adj-", "loyer-fixe"))]
    real = real[real["amount"].abs() >= 50]

    def _smooth_form(kind: str, pool: pd.DataFrame, key: str):
        with st.form(f"smooth_{key}", clear_on_submit=True, border=True):
            st.markdown(f"**Smooth {kind}**")
            pool = pool.sort_values("date", ascending=False)
            opts = list(pool["id"])
            lab = {r.id: f"{r.date:%d %b %Y} · {r.label[:48]} · {eur(r.amount, 2, sign=True)}" for r in pool.itertuples()}
            f1, f2, f3 = st.columns([3, 1, 1.2])
            pick = f1.selectbox("Transaction", opts, format_func=lambda i: lab.get(i, i)) if opts else None
            n_m = f2.number_input("Months", min_value=1, max_value=36, value=12, step=1)
            first = pool.set_index("id").loc[pick, "month"] if pick is not None else all_months[-1]
            start = f3.selectbox("From", all_months, index=all_months.index(pd.Timestamp(first)) if pd.Timestamp(first) in all_months else 0,
                                 format_func=lambda d: d.strftime("%b %Y"))
            if st.form_submit_button("Apply", type="primary") and pick is not None:
                db.upsert("income_treatment", pd.DataFrame([{"tx_id": pick, "mode": "smooth", "months": int(n_m),
                                                             "start": start.strftime("%Y-%m")}]), mode="replace")
                invalidate()
                st.rerun()

    s1, s2 = st.columns(2)
    with s1:
        _smooth_form("an inflow", real[real["amount"] > 0], "in")
    with s2:
        _smooth_form("an expense", real[(real["amount"] < 0) & (real["cat_type"] == "expense")], "out")
    cur_s = db.read("SELECT * FROM income_treatment WHERE mode = 'smooth'")
    if not cur_s.empty:
        info = b.tx.set_index("id")
        cur_s = cur_s[cur_s["tx_id"].isin(info.index)]
        sv = pd.DataFrame({"Remove": False, "tx_id": cur_s["tx_id"],
                           "Date": info.loc[cur_s["tx_id"], "date"].values, "Label": info.loc[cur_s["tx_id"], "label"].values,
                           "Amount": info.loc[cur_s["tx_id"], "amount"].values, "Months": cur_s["months"].values,
                           "From": cur_s["start"].values,
                           "Per month": info.loc[cur_s["tx_id"], "amount"].values / cur_s["months"].values})
        sed = st.data_editor(sv, hide_index=True, width="stretch", key="smooth_ed",
                             disabled=["tx_id", "Date", "Label", "Amount", "Months", "From", "Per month"],
                             column_config={"tx_id": None, "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                            "Amount": st.column_config.NumberColumn(format="%+,.2f €"),
                                            "Per month": st.column_config.NumberColumn(format="%+,.2f €")})
        if st.button("Remove selected", key="smooth_rm"):
            for r_ in sed[sed["Remove"]].itertuples(index=False):
                db.execute("DELETE FROM income_treatment WHERE tx_id = ?", [r_.tx_id])
            invalidate()
            st.rerun()

with tab_adj:
    adjustments_editor(list(tx["month"].unique()), "globale")
