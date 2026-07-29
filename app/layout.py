"""Page structure. Pure composition, no callbacks, no data crunching."""
from __future__ import annotations

from dash import dcc, html

from app import data


def _card(title: str, subtitle: str, body, extra_class: str = "") -> html.Div:
    return html.Div(
        className=f"card {extra_class}".strip(),
        children=[
            html.Div(
                className="card-head",
                children=[html.H3(title), html.P(subtitle, className="muted")],
            ),
            body,
        ],
    )


def _kpi(label: str, value: str, note: str = "") -> html.Div:
    return html.Div(
        className="kpi",
        children=[
            html.Span(label, className="kpi-label"),
            html.Span(value, className="kpi-value"),
            html.Span(note, className="kpi-note"),
        ],
    )


def header(s: dict) -> html.Div:
    source = "Kaggle source file" if s.get("source") == "kaggle" else "demo generator"
    pills = [
        html.Span(f"data: {source}", className="pill"),
        html.Span(f"{s.get('months_loaded', '?')} months loaded", className="pill"),
        html.Span(f"through {s.get('latest_month', '?')}", className="pill"),
        html.Span(f"refreshed {s.get('run_ts', '?')[:16]} UTC", className="pill pill-fresh"),
    ]
    return html.Div(
        className="header",
        children=[
            html.Div(
                children=[
                    html.H1("Propensity Lab"),
                    html.P(
                        "Per-customer product recommendations and adoption "
                        "forecasts for a retail bank, refreshed daily.",
                        className="muted",
                    ),
                ]
            ),
            html.Div(className="pills", children=pills),
        ],
    )


def kpi_row(s: dict) -> html.Div:
    lift = (
        s["champion_map_at_7"] / s["baseline_map_at_7"] - 1
        if s.get("baseline_map_at_7")
        else 0
    )
    return html.Div(
        className="kpi-row",
        children=[
            _kpi("Customers scored", f"{s.get('customers_scored', 0):,}"),
            _kpi(
                "Champion MAP@7",
                f"{s.get('champion_map_at_7', 0):.3f}",
                f"{lift:+.1%} vs popularity baseline",
            ),
            _kpi(
                "Champion model",
                s.get("champion_model", "-").replace("_", " "),
                "selected by walk-forward backtest",
            ),
            _kpi(
                "Projected adds next month",
                f"{s.get('projected_adds_next_month', 0):,}",
                "sum of per-product forecasts",
            ),
        ],
    )


def build_layout() -> html.Div:
    s = data.summary()
    products = sorted(data.forecasts()["product"].unique())
    options = [{"label": p.replace("_", " "), "value": p} for p in products]

    return html.Div(
        className="page",
        children=[
            header(s),
            kpi_row(s),
            html.Div(
                className="grid-2",
                children=[
                    _card(
                        "Model backtest",
                        "walk-forward MAP@7 across the three most recent months",
                        dcc.Graph(id="leaderboard-chart", config={"displayModeBar": False}),
                    ),
                    _card(
                        "Adoption forecast",
                        "monthly product adds, six months ahead with an 80% band",
                        html.Div(
                            children=[
                                dcc.Dropdown(
                                    id="forecast-product", options=options,
                                    value="payroll_deposit", clearable=False,
                                    className="select",
                                ),
                                dcc.Graph(id="forecast-chart", config={"displayModeBar": False}),
                            ]
                        ),
                    ),
                ],
            ),
            _card(
                "Customer lookup",
                "holdings history on the left, current top-7 recommendations on the right",
                html.Div(
                    children=[
                        dcc.Dropdown(
                            id="customer-select",
                            options=data.customer_options(),
                            value=data.customer_options()[0]["value"],
                            clearable=False, className="select select-narrow",
                        ),
                        html.Div(
                            className="grid-2",
                            children=[
                                dcc.Graph(id="customer-timeline", config={"displayModeBar": False}),
                                html.Div(id="customer-recs"),
                            ],
                        ),
                    ]
                ),
            ),
            _card(
                "Where growth is coming from",
                "monthly adds for the eight most-added products",
                dcc.Graph(id="trends-chart", config={"displayModeBar": False}),
            ),
            _card(
                "Pipeline health",
                "latest scheduled runs, most recent first",
                html.Div(id="pipeline-log"),
            ),
            dcc.Interval(id="refresh-tick", interval=5 * 60 * 1000),
            html.Footer(
                "Built on DuckDB, dbt and LightGBM. Data refreshes daily via "
                "the scheduled pipeline; this page picks up new artifacts "
                "automatically.",
                className="muted footer",
            ),
        ],
    )


def recs_table(recs) -> html.Table:
    max_score = max(recs["score"].max(), 1e-9)
    rows = []
    for _, r in recs.iterrows():
        pct = max(6, int(100 * r["score"] / max_score))
        rows.append(
            html.Tr(
                children=[
                    html.Td(f"{int(r['rank'])}", className="rank"),
                    html.Td(r["product"].replace("_", " "), className="prod"),
                    html.Td(
                        html.Div(
                            className="scorebar-wrap",
                            children=html.Div(
                                className="scorebar", style={"width": f"{pct}%"}
                            ),
                        )
                    ),
                    html.Td(r["reason"], className="reason"),
                ]
            )
        )
    head = html.Tr([html.Th("#"), html.Th("product"), html.Th("score"), html.Th("why")])
    return html.Table(className="recs-table", children=[head] + rows)


def log_table(runs: list[dict]) -> html.Table:
    head = html.Tr(
        [html.Th("run (UTC)"), html.Th("source"), html.Th("months"), html.Th("rows")]
    )
    rows = [
        html.Tr(
            [
                html.Td(r.get("ts", "")[:16].replace("T", " ")),
                html.Td(r.get("source", "")),
                html.Td(str(r.get("months_loaded", ""))),
                html.Td(f"{r.get('rows', 0):,}"),
            ]
        )
        for r in reversed(runs[-8:])
    ]
    return html.Table(className="recs-table", children=[head] + rows)
