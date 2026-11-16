"""Projections & goals: net-worth projection by asset class, financial independence, savings goals."""
import uuid
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from common import bundle, empty_state, en, eur, get_db, invalidate, pct, plot
from finmon import charts
from finmon.analytics import budget
from finmon.analytics import projection as pj

b = bundle()
st.title("Projections & goals")
if not b.allocation:
    empty_state()
    st.stop()

# ------------------------------------------------------------- inputs from the data
cls = b.allocation["Classe d'actif"]
start = {en(r.label): float(r.value) for r in cls.itertuples()}
net_worth = sum(start.values())
types = b.accounts.set_index("id")["type"]
tx = b.tx[b.tx["account_id"].map(types).isin(["courant", "autre"])] if not b.tx.empty else b.tx
g = budget.global_monthly(tx) if not tx.empty else pd.DataFrame()
if not g.empty:
    last_data = tx.loc[~tx["source_cat"].isin(["étalé", "ajustement", "loyer fixe"]), "date"].max()
    g = g[g.index + pd.offsets.MonthEnd(0) <= last_data]
    g = g[g.index >= (g.index[g["salaire"] > 0].min() if (g["salaire"] > 0).any() else g.index.min())]
avg_saving = float(g["economise"].mean()) if not g.empty else 1000.0
avg_spend = float((g["loyer"] + g["depenses"]).mean()) * 12 if not g.empty else 30000.0

tab_proj, tab_goals = st.tabs(["Net worth projection", "Savings goals"])

# ============================================================= projection
with tab_proj:
    c1, c2, c3, c4 = st.columns(4)
    horizon = c1.select_slider("Horizon", [5, 10, 15, 20, 25, 30, 40], value=20, format_func=lambda y: f"{y} y")
    monthly = c2.number_input("Monthly saving (€)", value=round(avg_saving / 50) * 50, step=50,
                              help=f"Default: average saved per month since first salary ({eur(avg_saving)}).")
    growth = c3.number_input("Saving growth / yr (%)", value=2.0, step=0.5) / 100
    infl = c4.number_input("Inflation (%)", value=2.0, step=0.25) / 100

    with st.expander("Assumptions by asset class", icon=":material/tune:"):
        rows = pd.DataFrame({"Asset class": list(start), "Today": list(start.values()),
                             "Expected return %": [pj.DEFAULT_RETURNS.get(k, 0.03) * 100 for k in start],
                             "Share of new savings %": [0.0] * len(start)})
        if "Equities" in rows["Asset class"].values:
            rows.loc[rows["Asset class"] == "Equities", "Share of new savings %"] = 70.0
        if "Regulated savings" in rows["Asset class"].values:
            rows.loc[rows["Asset class"] == "Regulated savings", "Share of new savings %"] = 15.0
        if "Crypto" in rows["Asset class"].values:
            rows.loc[rows["Asset class"] == "Crypto", "Share of new savings %"] = 5.0
        if "Employee savings" in rows["Asset class"].values:
            rows.loc[rows["Asset class"] == "Employee savings", "Share of new savings %"] = 10.0
        ed = st.data_editor(rows, hide_index=True, width="stretch", key="proj_ed", disabled=["Asset class", "Today"],
                            column_config={"Today": st.column_config.NumberColumn(format="%,.0f €"),
                                           "Expected return %": st.column_config.NumberColumn(format="%.1f", step=0.5),
                                           "Share of new savings %": st.column_config.NumberColumn(format="%.0f", step=5)})
    rets = dict(zip(ed["Asset class"], ed["Expected return %"] / 100))
    split = dict(zip(ed["Asset class"], ed["Share of new savings %"]))
    df = pj.project(start, rets, monthly, split, horizon, infl, growth)
    w_ret = sum(start[k] * rets.get(k, 0) for k in start) / net_worth if net_worth else 0

    fi_rate = 0.04
    fi_target = avg_spend / fi_rate
    fi_year = pj.years_to_target(df, fi_target, "real")
    end = df.iloc[-1]
    k = st.columns(4)
    k[0].metric("Net worth today", eur(net_worth), f"expected return {w_ret * 100:.1f} % / yr", delta_color="off")
    k[1].metric(f"In {horizon} years", eur(end["total"]), f"{eur(end['real'])} in today's euros", delta_color="off")
    k[2].metric("Contributions", eur(end["contributed"]), f"growth {eur(end['growth'], sign=True)}", delta_color="off")
    k[3].metric("Financial independence", f"{date.today().year + int(fi_year)}" if fi_year is not None else f"> {horizon} y",
                f"target {eur(fi_target)} · 4 % rule", delta_color="off",
                help=f"Annual spending {eur(avg_spend)} (rent + spending, average) ÷ 4 % withdrawal rate, in today's euros.")

    years = [date.today().year + y for y in df.index]
    fig = go.Figure()
    base = df["start"]
    fig.add_trace(go.Bar(x=years, y=base, name="Today's wealth", marker_color="#2a3140",
                         hovertemplate="%{y:,.0f} €<extra>Today's wealth</extra>"))
    fig.add_trace(go.Bar(x=years, y=df["contributed"], name="Contributions", marker_color=charts.CAT[0],
                         hovertemplate="%{y:,.0f} €<extra>Contributions</extra>"))
    fig.add_trace(go.Bar(x=years, y=df["growth"].clip(lower=0), name="Growth", marker_color=charts.CAT[2],
                         hovertemplate="%{y:,.0f} €<extra>Growth</extra>"))
    fig.add_trace(go.Scatter(x=years, y=df["real"], name="Inflation-adjusted", mode="lines",
                             line=dict(color=charts.CAT[1], width=2, dash="dot"),
                             hovertemplate="%{y:,.0f} €<extra>Real</extra>"))
    if fi_target < df["total"].max() * 1.3:
        fig.add_hline(y=fi_target, line_dash="dash", line_color=charts.INK_MUTED,
                      annotation_text="FI target", annotation_position="top left")
    fig.update_layout(barmode="stack", bargap=0.25)
    theme.section("Projected net worth")
    plot(charts.layout(fig, 400), key="proj")

    theme.section("By asset class")
    by = df[[c for c in start if c in df.columns]].copy()
    plot(charts.line(by.set_axis(years), list(by.columns), height=300, area=True,
                     colors={c: charts.CAT[i % len(charts.CAT)] for i, c in enumerate(by.columns)}), key="proj_cls")

# ============================================================= goals
SCOPES = {"net_worth": "Net worth", "investments": "Investments", "savings": "Regulated savings + cash"}
with tab_goals:
    db = get_db()
    nw = b.networth[b.networth["date"] == b.networth["date"].max()]
    current = {"net_worth": nw["value"].sum(),
               "investments": nw.loc[nw["bucket"] == "Investissements", "value"].sum(),
               "savings": nw.loc[nw["bucket"].isin(["Épargne réglementée", "Liquidités"]), "value"].sum()}
    goals = db.read("SELECT * FROM goals ORDER BY deadline")
    if goals.empty:
        st.caption("No goal yet.")
    for gl in goals.itertuples():
        have = max(0.0, current.get(gl.scope, 0.0))
        prog = min(1.0, have / gl.target) if gl.target else 0.0
        months = None
        if gl.deadline:
            dl = pd.Timestamp(gl.deadline)
            months = max(0, (dl.year - date.today().year) * 12 + dl.month - date.today().month)
        need = pj.required_monthly(have, gl.target, months, 0.04) if months is not None else None
        color = "#34c38f" if prog >= 1 else charts.CAT[0]
        st.html(
            f"<div style='background:#11141a;border:1px solid #1e232d;border-radius:12px;padding:14px 18px;margin:.4rem 0'>"
            f"<div style='display:flex;justify-content:space-between;align-items:baseline'>"
            f"<span style='font-weight:600;font-size:1rem'>{gl.name}</span>"
            f"<span style='color:#8b93a3;font-size:.8rem'>{SCOPES.get(gl.scope, gl.scope)}"
            f"{' · by ' + pd.Timestamp(gl.deadline).strftime('%b %Y') if gl.deadline else ''}</span></div>"
            f"<div style='display:flex;justify-content:space-between;margin:.5rem 0 .35rem 0;font-size:.85rem'>"
            f"<span>{eur(have)} <span style='color:#8b93a3'>of {eur(gl.target)}</span></span>"
            f"<span style='color:{color};font-weight:600'>{prog * 100:.0f} %</span></div>"
            f"<div class='fm-bar'><div style='width:{prog * 100:.1f}%;background:{color}'></div></div>"
            f"<div style='color:#8b93a3;font-size:.78rem;margin-top:.45rem'>"
            + (f"Required: {eur(need)} / month at 4 % · current pace {eur(avg_saving)} / month"
               if need is not None and prog < 1 else ("Reached" if prog >= 1 else "No deadline"))
            + "</div></div>")
    with st.expander("Add a goal", icon=":material/add:", expanded=goals.empty):
        with st.form("goal", clear_on_submit=True, border=False):
            a1, a2, a3, a4 = st.columns([2, 1, 1, 1.4])
            name = a1.text_input("Name", placeholder="e.g. Apartment deposit")
            target = a2.number_input("Target (€)", min_value=0.0, step=1000.0)
            deadline = a3.date_input("Deadline", value=date(date.today().year + 3, 12, 31), format="DD/MM/YYYY")
            scope = a4.selectbox("Measured on", list(SCOPES), format_func=SCOPES.get)
            if st.form_submit_button("Add goal", type="primary") and name and target:
                db.upsert("goals", pd.DataFrame([{"id": uuid.uuid4().hex[:10], "name": name.strip(), "target": target,
                                                  "deadline": deadline.isoformat(), "scope": scope, "initial": 0.0}]))
                invalidate()
                st.rerun()
    if not goals.empty:
        with st.expander("Edit goals", icon=":material/edit:"):
            eg = st.data_editor(goals.assign(Delete=False)[["Delete", "id", "name", "target", "deadline", "scope"]]
                                .rename(columns={"name": "Name", "target": "Target", "deadline": "Deadline", "scope": "Scope"}),
                                hide_index=True, width="stretch", key="goal_ed", disabled=["id", "Scope"],
                                column_config={"id": None, "Target": st.column_config.NumberColumn(format="%,.0f €")})
            if st.button("Save goals"):
                for r in eg.itertuples(index=False):
                    if r.Delete:
                        db.execute("DELETE FROM goals WHERE id = ?", [r.id])
                    else:
                        db.execute("UPDATE goals SET name = ?, target = ?, deadline = ? WHERE id = ?",
                                   [r.Name, float(r.Target), str(r.Deadline)[:10], r.id])
                invalidate()
                st.rerun()
