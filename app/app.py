"""Dash entry point.

Run with:  uv run python app/app.py   then open http://127.0.0.1:8050

The layout is rebuilt on every page load and a five-minute interval
re-renders the charts, so the daily pipeline refresh appears without
restarting the server.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dash import Dash, Input, Output

from app import charts, data, layout

app = Dash(
    __name__,
    title="Propensity Lab",
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    ],
)
app.layout = layout.build_layout  # callable: fresh artifacts on page load


@app.callback(
    Output("leaderboard-chart", "figure"),
    Output("trends-chart", "figure"),
    Output("pipeline-log", "children"),
    Input("refresh-tick", "n_intervals"),
)
def refresh_static(_):
    return (
        charts.model_leaderboard(data.leaderboard()),
        charts.product_small_multiples(data.product_trends()),
        layout.log_table(data.run_log()),
    )


@app.callback(
    Output("forecast-chart", "figure"),
    Input("forecast-product", "value"),
    Input("refresh-tick", "n_intervals"),
)
def refresh_forecast(product, _):
    return charts.adoption_forecast(data.forecasts(), product)


@app.callback(
    Output("customer-timeline", "figure"),
    Output("customer-recs", "children"),
    Input("customer-select", "value"),
    Input("refresh-tick", "n_intervals"),
)
def refresh_customer(customer_id, _):
    recs = data.recommendations()
    mine = recs[recs["customer_id"] == customer_id].sort_values("rank")
    return (
        charts.holdings_timeline(data.holdings_timeline(), customer_id),
        layout.recs_table(mine),
    )


if __name__ == "__main__":
    app.run(debug=False, port=8050)
