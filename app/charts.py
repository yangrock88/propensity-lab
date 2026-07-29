"""Plotly figure builders.

One visual language everywhere: white panels, faint horizontal grid,
a single indigo accent, muted slate for context, no chart junk.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

ACCENT = "#4f46e5"
ACCENT_SOFT = "rgba(79, 70, 229, 0.12)"
SLATE = "#94a3b8"
INK = "#0f172a"
GREEN = "#059669"

FONT = dict(family="Inter, Segoe UI, sans-serif", color=INK, size=13)


def _base(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        height=height,
        font=FONT,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=8, b=8),
        hoverlabel=dict(bgcolor="white", font=FONT, bordercolor="#e2e8f0"),
        legend=dict(orientation="h", y=1.08, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#e2e8f0")
    fig.update_yaxes(
        gridcolor="#eef2f7", zeroline=False, linecolor="rgba(0,0,0,0)"
    )
    return fig


MODEL_LABELS = {
    "lightgbm": "Gradient boosting",
    "blend_lgbm_cf": "Combined approach",
    "item_item_cf": "Customer similarity",
    "als_factorization": "Pattern matching",
    "popularity_baseline": "Popularity baseline",
}


def _label(p: str) -> str:
    return p.replace("_", " ").title()


def _model_label(m: str) -> str:
    return MODEL_LABELS.get(m, m.replace("_", " "))


def model_leaderboard(lb: pd.DataFrame) -> go.Figure:
    lb = lb.sort_values("map_at_7")
    best = lb["map_at_7"].max()
    colors = [
        ACCENT if v == best
        else ("#cbd5e1" if name == "popularity_baseline" else "#a5b4fc")
        for name, v in zip(lb["model"], lb["map_at_7"])
    ]
    fig = go.Figure(
        go.Bar(
            x=lb["map_at_7"],
            y=[_model_label(m) for m in lb["model"]],
            orientation="h",
            marker=dict(color=colors, cornerradius=6),
            text=[f"{v:.3f}" for v in lb["map_at_7"]],
            textposition="outside",
            hovertemplate="%{y}: accuracy score %{x:.4f}<extra></extra>",
        )
    )
    fig.update_xaxes(range=[0, lb["map_at_7"].max() * 1.22], title="Accuracy score (higher is better)")
    return _base(fig, height=280)


def adoption_forecast(fc: pd.DataFrame, product: str) -> go.Figure:
    df = fc[fc["product"] == product].sort_values("month")
    hist = df[df["kind"] == "actual"]
    fut = df[df["kind"] == "forecast"]
    # bridge the visual gap between the last actual and first forecast
    bridge = pd.concat([hist.tail(1), fut])

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pd.concat([bridge["month"], bridge["month"][::-1]]),
            y=pd.concat([bridge["hi"].fillna(bridge["adds"]),
                         bridge["lo"].fillna(bridge["adds"])[::-1]]),
            fill="toself", fillcolor=ACCENT_SOFT,
            line=dict(width=0), hoverinfo="skip", showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=hist["month"], y=hist["adds"], name="new sign-ups",
            line=dict(color=INK, width=2.4),
            hovertemplate="%{x|%b %Y}: %{y:.0f} new sign-ups<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=bridge["month"], y=bridge["adds"], name="projected",
            line=dict(color=ACCENT, width=2.4, dash="dot"),
            hovertemplate="%{x|%b %Y}: %{y:.0f} projected<extra></extra>",
        )
    )
    fig.update_yaxes(title="customers signing up per month", rangemode="tozero")
    return _base(fig)


def holdings_timeline(timeline: pd.DataFrame, customer_id: int) -> go.Figure:
    df = timeline[timeline["customer_id"] == customer_id].copy()
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(text="No products on record for this customer", showarrow=False, font=FONT)
        return _base(fig, height=300)

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    products = (
        df.groupby("product")["snapshot_date"].min().sort_values().index.tolist()
    )
    for i, p in enumerate(products):
        d = df[df["product"] == p].sort_values("snapshot_date")
        fig.add_trace(
            go.Scatter(
                x=d["snapshot_date"], y=[i] * len(d),
                mode="lines+markers",
                line=dict(color=ACCENT, width=5), marker=dict(size=5, color=ACCENT),
                opacity=0.75, showlegend=False,
                hovertemplate=f"{_label(p)} — held {len(d)} month{'s' if len(d) != 1 else ''}<extra></extra>",
            )
        )
    fig.update_yaxes(
        tickvals=list(range(len(products))),
        ticktext=[_label(p) for p in products],
        autorange="reversed", showgrid=False,
    )
    return _base(fig, height=max(240, 30 * len(products) + 90))


def _trend_label(y: "pd.Series") -> str:
    """Single-character trend direction based on first-half vs second-half mean."""
    vals = y.to_numpy()
    if len(vals) < 4 or vals.mean() == 0:
        return ""
    mid = len(vals) // 2
    chg = (vals[mid:].mean() - vals[:mid].mean()) / max(vals[:mid].mean(), 1)
    if chg > 0.08:
        return " ↑"
    if chg < -0.08:
        return " ↓"
    return " →"


def product_small_multiples(
    trends: pd.DataFrame,
    forecasts: "pd.DataFrame | None" = None,
    top_n: int = 9,
) -> go.Figure:
    """3 x 3 grid of mini trend charts, one per top product.

    Each title shows the product name, total sign-ups, trend arrow, and
    next month's projected value. When forecast data is supplied each
    chart extends the historical line with a dotted projection and an
    uncertainty band, mirroring the Six-Month Outlook card above.
    """
    from plotly.subplots import make_subplots

    trends = trends.copy()
    trends["snapshot_date"] = pd.to_datetime(trends["snapshot_date"])
    first = trends["snapshot_date"].min()
    trends = trends[trends["snapshot_date"] > first]
    top = (
        trends.groupby("product")["adds"].sum().nlargest(top_n).index.tolist()
    )

    # Pre-process forecast: keep first 3 future months per product.
    fc_by_product: dict[str, pd.DataFrame] = {}
    if forecasts is not None:
        fc = forecasts.copy()
        fc["month"] = pd.to_datetime(fc["month"])
        for p, grp in fc[fc["kind"] == "forecast"].sort_values("month").groupby("product"):
            fc_by_product[p] = grp.head(3).reset_index(drop=True)

    titles = []
    for p in top:
        d = trends[trends["product"] == p]
        total = int(d["adds"].sum())
        arrow = _trend_label(d.sort_values("snapshot_date")["adds"])
        if p in fc_by_product:
            nxt = int(round(float(fc_by_product[p].iloc[0]["adds"])))
            titles.append(f"{_label(p)}  ({total:,} sign-ups{arrow}  \u00b7  ~{nxt:,} next month)")
        else:
            titles.append(f"{_label(p)}  ({total:,} sign-ups{arrow})")

    rows, cols = 3, 3
    fig = make_subplots(
        rows=rows, cols=cols,
        subplot_titles=titles,
        vertical_spacing=0.20,
        horizontal_spacing=0.08,
    )
    for i, p in enumerate(top):
        r, c = i // cols + 1, i % cols + 1
        d = trends[trends["product"] == p].sort_values("snapshot_date")

        # Historical area
        fig.add_trace(
            go.Scatter(
                x=d["snapshot_date"], y=d["adds"], fill="tozeroy",
                line=dict(color=ACCENT, width=2), fillcolor=ACCENT_SOFT,
                showlegend=False,
                hovertemplate="%{x|%b %Y}: %{y} new sign-ups<extra></extra>",
            ),
            row=r, col=c,
        )

        # Forecast extension (band + dotted line)
        if p in fc_by_product:
            pfc = fc_by_product[p]
            last = d.iloc[-1]
            bx = [last["snapshot_date"]] + pfc["month"].tolist()
            by = [float(last["adds"])] + pfc["adds"].tolist()
            hi = pfc["hi"].fillna(pfc["adds"]).tolist()
            lo = pfc["lo"].fillna(pfc["adds"]).tolist()

            # Shaded uncertainty band
            fig.add_trace(
                go.Scatter(
                    x=bx + pfc["month"].tolist()[::-1],
                    y=[float(last["adds"])] + hi + lo[::-1],
                    fill="toself", fillcolor=ACCENT_SOFT,
                    line=dict(width=0), hoverinfo="skip", showlegend=False,
                ),
                row=r, col=c,
            )

            # Dotted projection line
            fig.add_trace(
                go.Scatter(
                    x=bx, y=by,
                    line=dict(color=ACCENT, width=1.5, dash="dot"),
                    showlegend=False,
                    hovertemplate="%{x|%b %Y}: ~%{y:.0f} projected<extra></extra>",
                ),
                row=r, col=c,
            )

    fig.update_annotations(font=dict(size=10, color="#475569"))
    fig.update_xaxes(
        tickformat="%b '%y",
        tickfont=dict(size=9, color=SLATE),
        nticks=4,
        showgrid=False,
    )
    fig.update_yaxes(
        tickfont=dict(size=9, color=SLATE),
        nticks=4,
        gridcolor="#eef2f7",
    )
    result = _base(fig, height=760)
    result.update_layout(margin=dict(l=4, r=4, t=72, b=8))
    return result
