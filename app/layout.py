"""Page structure. Pure composition, no callbacks, no data crunching."""
from __future__ import annotations

import datetime

import pandas as pd
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
        dt = datetime.datetime.strptime(latest, "%Y-%m-%d")
        latest_label = dt.strftime("%B %Y")
    except Exception:
        latest_label = latest
    pills = [
        html.Span(f"{s.get('months_loaded', '?')} months of history", className="pill"),
        html.Span(f"through {latest_label}", className="pill pill-fresh"),
    ]
    return html.Div(
        className="header",
        children=[
            html.Div(
                children=[
                    html.H1("Propensity Lab"),
                    html.P(
                        "Which financial products is each customer most likely to add next?",
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


def customer_holdings_cards(timeline: pd.DataFrame, customer_id: int) -> html.Div:
    """Product portfolio for one customer, shown as readable badge cards.

    Each card states the product name and when the customer first acquired
    it, so a viewer understands the relationship without reading a chart.
    """
    df = timeline[timeline["customer_id"] == customer_id].copy()
    if df.empty:
        return html.P("No product history on record for this customer.", className="muted")

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    latest = df["snapshot_date"].max()
    currently_held = set(df[df["snapshot_date"] == latest]["product"])
    first_seen = df.groupby("product")["snapshot_date"].min()

    count = len(currently_held)
    if count == 0:
        return html.P("This customer holds no products at the latest snapshot.", className="muted")

    def _duration(since_dt: "pd.Timestamp") -> str:
        months = (latest.year - since_dt.year) * 12 + (latest.month - since_dt.month)
        if months < 1:
            return "less than a month"
        if months < 12:
            return f"{months} month{'s' if months != 1 else ''}"
        yrs, mos = divmod(months, 12)
        if mos == 0:
            return f"{yrs} year{'s' if yrs != 1 else ''}"
        return f"{yrs}y {mos}m"

    cards = []
    for product in sorted(currently_held):
        since_dt = first_seen.get(product, latest)
        cards.append(
            html.Div(
                className="holding-card",
                children=[
                    html.Span(
                        product.replace("_", " ").title(),
                        className="holding-name",
                    ),
                    html.Span(_duration(since_dt), className="holding-since"),
                ],
            )
        )

    return html.Div([
        html.P(
            f"Currently holds {count} product{'s' if count != 1 else ''}.",
            className="muted",
            style={"marginBottom": "10px", "fontSize": "13px"},
        ),
        html.Div(className="holdings-grid", children=cards),
    ])


def build_layout() -> html.Div:
    s = data.summary()
    products = sorted(data.forecasts()["product"].unique())
    options = [{"label": p.replace("_", " ").title(), "value": p} for p in products]

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
                        "Accuracy of every model tested against actual customer decisions "
                        "from the last three months. Higher is better.",
                        dcc.Graph(id="leaderboard-chart", config={"displayModeBar": False}),
                    ),
                    _card(
                        "Six-month outlook",
                        "How many customers are expected to sign up for a given product "
                        "each month. The shaded area shows the range of likely outcomes.",
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
                "Products this customer currently holds on the left, with how long "
                "they have had each one. What to offer next is on the right.",
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
                                html.Div(id="customer-holdings"),
                                html.Div(id="customer-recs"),
                            ],
                        ),
                    ]
                ),
            ),
            _card(
                "Where new sign-ups are coming from",
                "The nine most active products. Each panel shows monthly new customers, "
                "total sign-ups for the period, and whether the trend is rising or falling.",
                dcc.Graph(id="trends-chart", config={"displayModeBar": False}),
            ),
            dcc.Interval(id="refresh-tick", interval=5 * 60 * 1000),
            html.Footer(
                "Based on historical retail banking customer data, 2015–2016.",
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
                    html.Td(r["product"].replace("_", " ").title(), className="prod"),
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
    head = html.Tr([html.Th("#"), html.Th("Product"), html.Th("Likelihood"), html.Th("Reason")])
    table = html.Table(className="recs-table", children=[head] + rows)
    return html.Div([
        html.H4(
            "New Product Offering",
            style={
                "fontSize": "13px",
                "fontWeight": "600",
                "color": "#0f172a",
                "marginBottom": "10px",
                "letterSpacing": "0.02em",
                "textTransform": "uppercase",
            },
        ),
        table,
    ])
