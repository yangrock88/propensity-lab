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
    return p.replace("_", " ")


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
                hovertemplate=f"Holding {_label(p)} as of %{{x|%b %Y}}<extra></extra>",
            )
        )
    fig.update_yaxes(
        tickvals=list(range(len(products))),
        ticktext=[_label(p) for p in products],
        autorange="reversed", showgrid=False,
    )
    return _base(fig, height=max(240, 30 * len(products) + 90))


def product_small_multiples(trends: pd.DataFrame, top_n: int = 8) -> go.Figure:
    from plotly.subplots import make_subplots

    trends = trends.copy()
    trends["snapshot_date"] = pd.to_datetime(trends["snapshot_date"])
    first = trends["snapshot_date"].min()
    trends = trends[trends["snapshot_date"] > first]
    top = (
        trends.groupby("product")["adds"].sum().nlargest(top_n).index.tolist()
    )
    rows = 2
    cols = top_n // rows
    fig = make_subplots(
        rows=rows, cols=cols, subplot_titles=[_label(p) for p in top],
        vertical_spacing=0.22, horizontal_spacing=0.05,
    )
    for i, p in enumerate(top):
        d = trends[trends["product"] == p].sort_values("snapshot_date")
        fig.add_trace(
            go.Scatter(
                x=d["snapshot_date"], y=d["adds"], fill="tozeroy",
                line=dict(color=ACCENT, width=1.8), fillcolor=ACCENT_SOFT,
                showlegend=False,
                hovertemplate="%{x|%b %Y}: %{y} new sign-ups<extra></extra>",
            ),
            row=i // cols + 1, col=i % cols + 1,
        )
    fig.update_annotations(font=dict(size=12, color="#475569"))
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showticklabels=False, showgrid=False)
    return _base(fig, height=320)
