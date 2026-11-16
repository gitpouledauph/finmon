"""Allocation & exposure: look-through breakdowns, diversification score, holdings map."""
import pandas as pd
import streamlit as st

import theme
from common import bundle, download_df, empty_state, en, eur, pct, plot
from finmon import charts
from finmon.analytics.allocation import SCORE_DIMS, allocation, diversification

b = bundle()
head, right = st.columns([2, 3], vertical_alignment="bottom")
head.title("Allocation")
if not b.allocation:
    empty_state("data")
    st.stop()
scope = right.segmented_control("Scope", ["Investments", "Total wealth"], default="Investments",
                                label_visibility="collapsed") or "Investments"
pf = b.portfolio
if scope == "Investments":
    inv_cash = pf.accounts.sort_values("date").groupby("account_id").tail(1)[["account_id", "cash"]] if not pf.accounts.empty else None
    alloc = allocation(pf.current, None, b.accounts, inv_cash, include_cash=True)
else:
    alloc = b.allocation
if not alloc:
    empty_state("positions")
    st.stop()

lines = alloc["_lines"]
total = lines["value"].sum()
div = diversification(alloc, pf.current)

# ------------------------------------------------------------- headline
c = st.columns([1.3, 1, 1, 1])
with c[0]:
    sc = div["score"]
    color = "#4fb286" if sc >= 70 else ("#c9a96e" if sc >= 45 else "#e06c75")
    label = "Well diversified" if sc >= 70 else ("Moderately diversified" if sc >= 45 else "Concentrated")
    st.html(f"<div style='background:#121620;border:1px solid #1f2533;border-radius:12px;padding:12px 16px'>"
            f"<div class='fm-eyebrow'>Diversification score</div>"
            f"<div class='fm-score'><span class='v' style='color:{color}'>{sc:.0f}</span>"
            f"<span style='color:#8b93a3'>/ 100 · {label}</span></div></div>")
c[1].metric("Analysed", eur(total))
if div["top_name"]:
    c[2].metric("Largest line", pct(div["top_weight"], sign=False), div["top_name"], delta_color="off")
    c[3].metric("Top 5 lines", pct(div["top5"], sign=False), delta_color="off")

bars = "".join(
    f"<div style='display:grid;grid-template-columns:120px 1fr 120px;gap:.8rem;align-items:center;margin:.35rem 0'>"
    f"<span style='font-size:.8rem;color:#c3c9d4'>{k}</span>"
    f"<div class='fm-bar'><div style='width:{v * 100:.0f}%;background:{'#4fb286' if v >= .7 else '#c9a96e' if v >= .45 else '#e06c75'}'></div></div>"
    f"<span style='font-size:.75rem;color:#8b93a3;text-align:right'>{div['effective'][k]:.1f} eff. / {SCORE_DIMS[k][0]:.0f}</span></div>"
    for k, v in div["parts"].items())
with st.expander("Score breakdown", icon=":material/analytics:"):
    st.html(bars)
    st.caption("Effective number = 1 / Σ weight² per dimension, capped at the target shown. "
               "Weights: holdings 30 %, geography 20 %, sectors 20 %, asset classes 15 %, currencies 15 %.")

# ------------------------------------------------------------- donuts
DIMS = [("Classe d'actif", "Asset class"), ("Zone géographique", "Region"), ("Devise (sous-jacent)", "Currency"),
        ("Secteur (actions)", "Sector · equities"), ("Enveloppe", "Account type"), ("Établissement", "Institution")]
avail = [(k, t) for k, t in DIMS if k in alloc]
for i in range(0, len(avail), 3):
    cols = st.columns(3)
    for col, (k, title) in zip(cols, avail[i:i + 3]):
        d = alloc[k].copy()
        if len(d) > 8:
            other = pd.DataFrame({"label": ["Other"], "value": [d["value"].iloc[7:].sum()],
                                  "weight": [d["weight"].iloc[7:].sum()]})
            d = pd.concat([d.head(7), other], ignore_index=True)
        labels = [en(x) for x in d["label"]]
        with col:
            theme.section(title, f"{len(alloc[k])}")
            top = d.iloc[0]
            plot(charts.donut(labels, d["value"], height=210,
                              center=f"<b>{top['weight'] * 100:.0f}%</b><br><span style='font-size:11px;color:#8b93a3'>"
                                     f"{en(top['label'])}</span>"), key=f"dn-{k}")
            st.html(charts.legend_rows(labels, d["value"]))

# ------------------------------------------------------------- holdings map
if not pf.current.empty:
    theme.section("Holdings map", "size = value · colour = unrealized return")
    cur = pf.current.copy()
    cur["group"] = cur["asset_class"].map(en).fillna("Other")
    tm = cur.groupby(["group", "name"], as_index=False).agg(value=("value", "sum"), cost=("cost", "sum"))
    tm["perf"] = (tm["value"] / tm["cost"] - 1).where(tm["cost"] > 0)
    plot(charts.perf_treemap(tm[tm["value"] > 0], height=480), key="tm")
    download_df(lines.drop(columns=["exposure", "regions", "sectors"]).set_index("name"), "allocation", "Export CSV")
