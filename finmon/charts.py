"""Graphes Plotly au style commun (palette validée, marques fines, survol)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Palette catégorielle, ordre fixe (validée daltonisme sur paires adjacentes).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#a8a7a1"
GOOD, BAD = "#0ca30c", "#d03b3b"
MUTED = "#898781"
GRID = "rgba(137,135,129,0.25)"
# Rampe séquentielle (une teinte) : du plus faible au plus fort, contre le fond.
# En sombre, les faibles valeurs se fondent dans le fond et les fortes s'éclaircissent.
SEQ_LIGHT = [[0, "#f4f8fd"], [0.25, "#b7d3f6"], [0.5, "#6da7ec"], [0.75, "#2a78d6"], [1, "#104281"]]
SEQ_DARK = [[0, "#1a2433"], [0.25, "#1d4a85"], [0.5, "#2a78d6"], [0.75, "#6da7ec"], [1, "#cfe1f9"]]
THEME = "dark"  # le dashboard est en mode sombre (.streamlit/config.toml)
FONT = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif'

# Couleurs fixes par entité : une couleur suit toujours la même chose.
FIXED = {
    "Sous-jacent": SERIES[0], "Change": SERIES[1], "Effet croisé": OTHER,
    "Investissements": SERIES[0], "Épargne réglementée": SERIES[2], "Liquidités": SERIES[3],
    "Autres actifs": SERIES[6], "Capital investi": MUTED,
    "Revenus": SERIES[2], "Dépenses": SERIES[1], "Épargne": SERIES[0],
}


MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]


def mois(ts) -> str:
    return f"{MOIS[ts.month - 1]} {ts.year}"


def _date_axis(fig: go.Figure, x) -> None:
    if isinstance(x, pd.DatetimeIndex):
        fig.update_xaxes(tickformat="%m/%Y", hoverformat="%d/%m/%Y")


def eur(x: float | None, dec: int = 0, sign: bool = False) -> str:
    if x is None or x != x:
        return "—"
    s = f"{x:+,.{dec}f}" if sign else f"{x:,.{dec}f}"
    return s.replace(",", " ").replace(".", ",") + " €"


def pct(x: float | None, dec: int = 1, sign: bool = True) -> str:
    if x is None or x != x:
        return "—"
    s = f"{x * 100:+.{dec}f}" if sign else f"{x * 100:.{dec}f}"
    return s.replace(".", ",") + " %"


def color_map(labels: list[str], max_series: int = 7) -> dict[str, str]:
    """Attribue les slots dans l'ordre donné ; au-delà => « Autres » gris."""
    m = {}
    for i, lab in enumerate(labels):
        m[lab] = FIXED.get(lab) or (SERIES[i] if i < max_series else OTHER)
    m["Autres"] = OTHER
    return m


def layout(fig: go.Figure, height: int = 360, legend: bool = True, yfmt: str | None = ",.0f", ysuffix: str = " €") -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=24, b=8),
        font=dict(family=FONT, size=13),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified", showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        separators=", ",
        hoverlabel=dict(font_family=FONT),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, ticks="", title=None, tickangle=0, automargin=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=True, zerolinecolor=GRID, title=None,
                     tickformat=yfmt, ticksuffix=ysuffix)
    return fig


def line(df: pd.DataFrame, cols: list[str], height=340, colors: dict | None = None, area: bool = False,
         dash: dict | None = None, ysuffix=" €", yfmt=",.0f", hover_fmt=",.0f") -> go.Figure:
    cm = colors or color_map(cols)
    fig = go.Figure()
    for c in cols:
        fig.add_trace(go.Scatter(
            x=df.index, y=df[c], name=c, mode="lines",
            line=dict(width=2, color=cm.get(c, OTHER), dash=(dash or {}).get(c)),
            stackgroup="one" if area else None,
            hovertemplate=f"%{{y:{hover_fmt}}}{ysuffix}<extra>{c}</extra>",
        ))
    fig = layout(fig, height, legend=len(cols) > 1, ysuffix=ysuffix, yfmt=yfmt)
    _date_axis(fig, df.index)
    return fig


def stacked_bars(df: pd.DataFrame, height=380, colors: dict | None = None, ysuffix=" €") -> go.Figure:
    """df : index = x (mois), colonnes = séries."""
    cm = colors or color_map(list(df.columns))
    fig = go.Figure()
    for c in df.columns:
        fig.add_trace(go.Bar(x=df.index, y=df[c], name=c, marker=dict(color=cm.get(c, OTHER), line=dict(width=0)),
                             hovertemplate=f"%{{y:,.0f}}{ysuffix}<extra>{c}</extra>"))
    fig.update_layout(barmode="stack", bargap=0.25)
    fig = layout(fig, height, ysuffix=ysuffix)
    if isinstance(df.index, pd.DatetimeIndex):
        fig.update_xaxes(tickformat="%m/%Y", hoverformat="%m/%Y")
    else:
        fig.update_xaxes(type="category")
    return fig


def hbar(labels, values, height=None, color=SERIES[0], text=None, xsuffix=" €") -> go.Figure:
    labels, values = list(labels), list(values)
    fig = go.Figure(go.Bar(
        y=labels, x=values, orientation="h", marker=dict(color=color, line=dict(width=0)),
        text=text, textposition="outside", cliponaxis=False,
        hovertemplate=f"%{{y}} : %{{x:,.0f}}{xsuffix}<extra></extra>",
    ))
    fig = layout(fig, height or max(160, 34 * len(labels) + 40), legend=False, ysuffix="")
    fig.update_layout(hovermode="closest", bargap=0.35)
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)", ticksuffix="  ", tickformat=None, type="category")
    lo, hi = min(values + [0]), max(values + [0])
    span = (hi - lo) or 1.0
    pad = 0.32 if text is not None else 0.04
    fig.update_xaxes(showgrid=True, gridcolor=GRID, ticksuffix=xsuffix, tickformat=",.0f", nticks=5,
                     range=[lo - (pad * span if lo < 0 else 0), hi + (pad * span if hi > 0 else 0)])
    return fig


def signed_hbar(labels, values, height=None, xsuffix=" €") -> go.Figure:
    colors = [GOOD if v >= 0 else BAD for v in values]
    text = [eur(v, sign=True) if xsuffix == " €" else f"{v:+.1f}" for v in values]
    return hbar(labels, values, height, color=colors, text=text, xsuffix=xsuffix)


def waterfall(steps: list[tuple[str, float]], start_label: str, start: float, end_label: str) -> go.Figure:
    x = [start_label] + [s[0] for s in steps] + [end_label]
    y = [start] + [s[1] for s in steps] + [0]
    measure = ["absolute"] + ["relative"] * len(steps) + ["total"]
    fig = go.Figure(go.Waterfall(
        x=x, y=y, measure=measure,
        increasing=dict(marker=dict(color=GOOD)), decreasing=dict(marker=dict(color=BAD)),
        totals=dict(marker=dict(color=SERIES[0])),
        connector=dict(line=dict(color=GRID, width=1)),
        text=[eur(start)] + [eur(s[1], sign=True) for s in steps] + [eur(start + sum(s[1] for s in steps))],
        textposition="outside", hovertemplate="%{x} : %{y:,.0f} €<extra></extra>",
    ))
    fig = layout(fig, 380, legend=False)
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(range=[0, max(start, start + sum(s[1] for s in steps), start + sum(max(s[1], 0) for s in steps)) * 1.12])
    return fig


def heatmap(df: pd.DataFrame, height=None) -> go.Figure:
    """Catégories × mois, rampe séquentielle bleue (une seule teinte)."""
    fig = go.Figure(go.Heatmap(
        z=df.values, x=[d.strftime("%m/%y") for d in df.columns], y=list(df.index),
        colorscale=SEQ_DARK if THEME == "dark" else SEQ_LIGHT,
        xgap=2, ygap=2, hovertemplate="%{y} · %{x} : %{z:,.0f} €<extra></extra>",
        colorbar=dict(title=None, ticksuffix=" €", thickness=10),
    ))
    fig = layout(fig, height or max(260, 26 * len(df.index) + 60), legend=False, ysuffix="")
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)", tickformat=None)
    return fig


def treemap(df: pd.DataFrame, path_cols: list[str], value_col: str = "value", height=420) -> go.Figure:
    import plotly.express as px

    tops = list(df.groupby(path_cols[0])[value_col].sum().sort_values(ascending=False).index)
    fig = px.treemap(df, path=path_cols, values=value_col, color=path_cols[0], color_discrete_map=color_map(tops))
    fig.update_traces(marker=dict(line=dict(width=2, color="rgba(255,255,255,0.9)")),
                      hovertemplate="%{label} : %{value:,.0f} € (%{percentRoot:.1%})<extra></extra>",
                      texttemplate="%{label}<br>%{percentRoot:.1%}")
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=8, b=0), font=dict(family=FONT),
                      paper_bgcolor="rgba(0,0,0,0)", separators=", ")
    return fig


# --------------------------------------------------------------------------
# Professional figures (Meridian)
# --------------------------------------------------------------------------
INK, INK_MUTED, SURFACE = "#e9ecf1", "#8b93a3", "#11141a"
CAT = ["#5b8cff", "#f2a65a", "#34c38f", "#c48bff", "#ef6f9a", "#4fc9d9", "#d9c55a", "#8f9bb3"]


def _clean(fig: go.Figure, height: int, legend: bool = True) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=10, b=8), font=dict(family=FONT, size=12, color=INK),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", separators=", ",
                      showlegend=legend, legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None,
                                                     font=dict(color=INK_MUTED, size=11)),
                      hoverlabel=dict(font_family=FONT, bgcolor="#1a1f29", bordercolor="#2a3140"))
    return fig


def donut(labels, values, height=300, center: str | None = None, colors: dict | None = None) -> go.Figure:
    labels, values = list(labels), list(values)
    cm = colors or {l: CAT[i % len(CAT)] if i < len(CAT) else OTHER for i, l in enumerate(labels)}
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.68, sort=False, direction="clockwise",
                           marker=dict(colors=[cm.get(l, OTHER) for l in labels], line=dict(color=SURFACE, width=2)),
                           textinfo="none", hovertemplate="%{label}<br>%{value:,.0f} € · %{percent}<extra></extra>"))
    if center:
        fig.add_annotation(text=center, x=0.5, y=0.5, showarrow=False, font=dict(size=15, color=INK))
    fig = _clean(fig, height, legend=False)
    fig.update_layout(margin=dict(l=4, r=4, t=4, b=4))
    return fig


def legend_rows(labels, values, colors: dict | None = None) -> str:
    """HTML legend with color dot, label, share and value — for donuts."""
    labels, values = list(labels), list(values)
    tot = sum(values) or 1
    cm = colors or {l: CAT[i % len(CAT)] if i < len(CAT) else OTHER for i, l in enumerate(labels)}
    rows = "".join(
        f"<div style='display:flex;justify-content:space-between;align-items:center;padding:3px 0;"
        f"border-bottom:1px solid #1a1f28;font-size:.82rem'>"
        f"<span style='display:flex;align-items:center;gap:.5rem;color:{INK}'>"
        f"<span style='width:8px;height:8px;border-radius:2px;background:{cm.get(l, OTHER)};display:inline-block'></span>{l}</span>"
        f"<span style='color:{INK_MUTED}'>{v / tot * 100:.1f} %&nbsp;&nbsp;<span style='color:{INK}'>{eur(v)}</span></span></div>"
        for l, v in zip(labels, values))
    return f"<div style='padding:2px 4px'>{rows}</div>"


def perf_treemap(df: pd.DataFrame, height=460) -> go.Figure:
    """Lines sized by value, colored by performance (diverging red/grey/green), grouped by a parent column."""
    import numpy as np

    d = df.copy()
    perf = d["perf"].fillna(0).clip(-0.5, 0.5)
    ids, labels, parents, values, colors, texts, hover = [], [], [], [], [], [], []
    for g, sub in d.groupby("group"):
        ids.append(f"g:{g}"); labels.append(g); parents.append(""); values.append(sub["value"].sum())
        colors.append("#151922"); texts.append(""); hover.append(f"{g}<br>{eur(sub['value'].sum())}")
    for r, p in zip(d.itertuples(), perf):
        ids.append(f"l:{r.group}:{r.name}"); labels.append(r.name); parents.append(f"g:{r.group}")
        values.append(r.value); colors.append(p)
        texts.append(f"{r.name}<br>{(r.perf or 0) * 100:+.1f} %")
        hover.append(f"{r.name}<br>{eur(r.value)} · {(r.perf or 0) * 100:+.1f} %")
    num = [c if isinstance(c, float) else np.nan for c in colors]
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="total", text=texts,
        texttemplate="%{text}", hovertext=hover, hovertemplate="%{hovertext}<extra></extra>",
        marker=dict(colors=[c if isinstance(c, float) else 0 for c in colors],
                    colorscale=[[0, "#c0392b"], [0.35, "#7a2f35"], [0.5, "#2a2f3a"], [0.65, "#1f6b4f"], [1, "#27ae60"]],
                    cmin=-0.5, cmax=0.5, line=dict(color=SURFACE, width=2), showscale=False),
        root_color="rgba(0,0,0,0)", tiling=dict(pad=2), pathbar=dict(visible=False),
        textfont=dict(color="#f3f5f8", size=12),
    ))
    _ = num
    fig = _clean(fig, height, legend=False)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    return fig


def grouped_hbar(categories, series: dict, height=None, colors: dict | None = None, xsuffix=" €") -> go.Figure:
    """Horizontal grouped bars: one row per category, one bar per series (e.g. this month vs other)."""
    cats = list(categories)
    cm = colors or {k: CAT[i] for i, k in enumerate(series)}
    fig = go.Figure()
    for name, vals in series.items():
        fig.add_trace(go.Bar(y=cats, x=list(vals), name=name, orientation="h", marker=dict(color=cm[name], line=dict(width=0)),
                             hovertemplate="%{y}<br>%{x:,.0f}" + xsuffix + "<extra>" + name + "</extra>"))
    fig = _clean(fig, height or max(220, 30 * len(cats) * max(1, len(series)) // 1.6 + 60))
    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.06, hovermode="closest")
    fig.update_yaxes(autorange="reversed", showgrid=False, ticksuffix="  ", tickfont=dict(color=INK_MUTED))
    fig.update_xaxes(showgrid=True, gridcolor=GRID, ticksuffix=xsuffix, tickformat=",.0f", nticks=5, zeroline=False,
                     tickfont=dict(color=INK_MUTED))
    return fig


def diverging_hbar(labels, values, height=None, xsuffix=" €", invert: bool = False) -> go.Figure:
    """Signed horizontal bars with value labels inside the plot area (no clipping).
    invert=True: positive values are bad (e.g. more spending)."""
    labels, values = list(labels), list(values)
    colors = [(BAD if invert else GOOD) if v >= 0 else (GOOD if invert else BAD) for v in values]
    fig = go.Figure(go.Bar(y=labels, x=values, orientation="h", marker=dict(color=colors, line=dict(width=0)),
                           text=[(eur(v, sign=True) if xsuffix == " €" else f"{v:+.1f}{xsuffix}") for v in values],
                           textposition="outside", cliponaxis=False, textfont=dict(color=INK_MUTED, size=11),
                           hovertemplate="%{y}: %{x:+,.0f}" + xsuffix + "<extra></extra>"))
    lo, hi = min(values + [0]), max(values + [0])
    span = (hi - lo) or 1
    fig = _clean(fig, height or max(200, 28 * len(labels) + 50), legend=False)
    fig.update_layout(bargap=0.35, hovermode="closest", margin=dict(l=8, r=40, t=8, b=8))
    fig.update_yaxes(autorange="reversed", showgrid=False, ticksuffix="  ", tickfont=dict(color=INK_MUTED))
    fig.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor="#3a4252", ticksuffix=xsuffix,
                     tickformat=",.0f", nticks=5, range=[lo - 0.25 * span if lo < 0 else 0, hi + 0.25 * span if hi > 0 else 0],
                     tickfont=dict(color=INK_MUTED))
    return fig
