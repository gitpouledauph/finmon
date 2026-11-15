import streamlit as st

from common import bundle, download_df, empty_state, eur, pct, plot
from finmon import charts
from finmon.analytics.allocation import allocation

b = bundle()
st.title("Allocation & exposition")
if not b.allocation:
    empty_state()
    st.stop()

scope = st.segmented_control("Périmètre", ["Patrimoine total", "Investissements seuls"], default="Patrimoine total")
pf = b.portfolio
if scope == "Investissements seuls":
    inv_cash = pf.accounts.sort_values("date").groupby("account_id").tail(1)[["account_id", "cash"]] if not pf.accounts.empty else None
    alloc = allocation(pf.current, None, b.accounts, inv_cash, include_cash=True)
else:
    alloc = b.allocation
if not alloc:
    empty_state("positions")
    st.stop()

lines = alloc["_lines"]
total = lines["value"].sum()
c = st.columns(4)
c[0].metric("Total analysé", eur(total))
if not pf.current.empty:
    w = pf.current.sort_values("value", ascending=False)["value"] / total
    c[1].metric("1re ligne", pct(w.iloc[0], sign=False), pf.current.sort_values("value", ascending=False)["name"].iloc[0],
                delta_color="off")
    c[2].metric("5 premières lignes", pct(w.head(5).sum(), sign=False), delta_color="off")
usd = alloc["Devise (sous-jacent)"]
non_eur = usd.loc[usd["label"] != "EUR", "weight"].sum()
c[3].metric("Exposé hors euro", pct(non_eur, sign=False), help="Part du total dont la valeur dépend d'une devise étrangère (sous-jacent).")

st.caption("Zones, devises et secteurs sont calculés « par transparence » : un ETF est éclaté selon son "
           "indice (profils types ou données Yahoo). Ajustez les répartitions dans Données › Titres.")

dims = [k for k in alloc if not k.startswith("_")]
for i in range(0, len(dims), 2):
    cols = st.columns(2)
    for col, dim in zip(cols, dims[i:i + 2]):
        d = alloc[dim]
        with col:
            st.subheader(dim)
            plot(charts.hbar(d["label"], d["value"], text=[f"{w * 100:.1f} %".replace(".", ",") for w in d["weight"]]),
                 key=f"al-{dim}")

st.subheader("Carte des lignes")
tm = lines.groupby(["asset_class", "name"], as_index=False)["value"].sum()
plot(charts.treemap(tm, ["asset_class", "name"]), key="tm")
download_df(lines.drop(columns=["exposure", "regions", "sectors"]).set_index("name"), "allocation")
