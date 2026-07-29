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
    latest = s.get("latest_month", "?")
    try:
        import datetime
        dt = datetime.datetime.strptime(latest, "%Y-%m-%d")
        latest_label = dt.strftime("%B %Y")
    except Exception:
        latest_label = latest
    run_ts = s.get("run_ts", "?")
    run_label = run_ts[:10] if run_ts != "?" else "?"
    pills = [
        html.Span(f"{s.get('months_loaded', '?')} months of history", className="pill"),
        html.Span(f"through {latest_label}", className="pill"),
        html.Span(f"last updated {run_label}", className="pill pill-fresh"),
    ]
    return html.Div(
        className="header",
        children=[
            html.Div(
                children=[
                    html.H1("Propensity Lab"),
                    html.P(
                        "Which financial products is each customer likely to add next? "
                        "Updated every morning.",
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
    model_labels = {
        "lightgbm": "Gradient boosting",
        "blend_lgbm_cf": "Combined approach",
        "item_item_cf": "Customer similarity",
        "als_factorization": "Pattern matching",
        "popularity_baseline": "Popularity baseline",
    }
    champion_raw = s.get("champion_model", "-")
    champion_display = model_labels.get(champion_raw, champion_raw.replace("_", " "))
    return html.Div(
        className="kpi-row",
        children=[
            _kpi("Customers analyzed", f"{s.get('customers_scored', 0):,}"),
            _kpi(
                "Recommendation accuracy",
                f"{s.get('champion_map_at_7', 0):.3f}",
                f"{lift:+.1%} better than guessing by popularity alone",
            ),
            _kpi(
                "Best performing model",
                champion_display,
                "chosen by testing against actual customer behavior",
            ),
            _kpi(
                "New sign-ups expected next month",
                f"{s.get('projected_adds_next_month', 0):,}",
                "across all products, based on current trends",
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
                        "How each approach compares",
                        "Accuracy of every model tested against actual customer decisions from the last three months. Higher is better.",
                        dcc.Graph(id="leaderboard-chart", config={"displayModeBar": False}),
                    ),
                    _card(
                        "Six-month outlook",
                        "How many customers are expected to sign up for a given product each month. The shaded area shows the range of likely outcomes.",
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
                "Individual customer view",
                "Products this customer currently holds on the left. What they are most likely to add next on the right, with the reason why.",
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
                "Where new sign-ups are coming from",
                "The eight most active products by new customers added each month.",
                dcc.Graph(id="trends-chart", config={"displayModeBar": False}),
            ),
            _card(
                "Data freshness",
                "Recent daily updates. A gap here means the morning refresh did not run.",
                html.Div(id="pipeline-log"),
            ),
            dcc.Interval(id="refresh-tick", interval=5 * 60 * 1000),
            html.Footer(
                "Refreshes every morning. Numbers update automatically — no page reload needed.",
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
    head = html.Tr([html.Th("#"), html.Th("product"), html.Th("likelihood"), html.Th("reason")])
    return html.Table(className="recs-table", children=[head] + rows)


def log_table(runs: list[dict]) -> html.Table:
    head = html.Tr(
        [html.Th("updated at"), html.Th("months of data"), html.Th("customer records"), html.Th("status")]
    )
    rows = [
        html.Tr(
            [
                html.Td(r.get("ts", "")[:10]),
                html.Td(str(r.get("months_loaded", ""))),
                html.Td(f"{r.get('rows', 0):,}"),
                html.Td("ok" if r.get("refresh_status") == "ok" else ("failed" if r.get("refresh_status") == "failed" else "—")),
            ]
        )
        for r in reversed(runs[-8:])
    ]
    return html.Table(className="recs-table", children=[head] + rows)
