"""Generates a self-contained static HTML dashboard from the current artifacts.

Run from the project root:
    uv run python build_static.py

Output:
    docs/index.html

The HTML file embeds all Plotly charts as inline JavaScript so it works
with no server and no Python. Push docs/ to GitHub and enable Pages.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import charts, data, layout  # noqa: F401

CSS_PATH = Path("app/assets/style.css")
DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)


def _fig_html(fig, first: bool = False) -> str:
    """Render a Plotly figure to an HTML div string."""
    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs="cdn" if first else False,
        config={"displayModeBar": False},
    )


def _kpi_block(label: str, value: str, note: str = "") -> str:
    return f"""
    <div class="kpi">
      <span class="kpi-label">{label}</span>
      <span class="kpi-value">{value}</span>
      <span class="kpi-note">{note}</span>
    </div>"""


def _card(title: str, subtitle: str, body: str) -> str:
    return f"""
  <div class="card">
    <div class="card-head">
      <h3>{title}</h3>
      <p class="muted">{subtitle}</p>
    </div>
    {body}
  </div>"""


def _holdings_html(timeline: pd.DataFrame, customer_id: int) -> str:
    import pandas as _pd
    df = timeline[timeline["customer_id"] == customer_id].copy()
    if df.empty:
        return "<p class='muted'>No product history on record.</p>"
    df["snapshot_date"] = _pd.to_datetime(df["snapshot_date"])
    latest = df["snapshot_date"].max()
    currently_held = set(df[df["snapshot_date"] == latest]["product"])
    first_seen = df.groupby("product")["snapshot_date"].min()
    if not currently_held:
        return "<p class='muted'>No products held at the latest snapshot.</p>"

    def dur(since_dt):
        months = (latest.year - since_dt.year) * 12 + (latest.month - since_dt.month)
        if months < 1:
            return "less than a month"
        if months < 12:
            return f"{months} month{'s' if months != 1 else ''}"
        yrs, mos = divmod(months, 12)
        if mos == 0:
            return f"{yrs} year{'s' if yrs != 1 else ''}"
        return f"{yrs}y {mos}m"

    count = len(currently_held)
    cards = ""
    for p in sorted(currently_held):
        name = p.replace("_", " ").title()
        duration = dur(first_seen.get(p, latest))
        cards += f"""
      <div class="holding-card">
        <span class="holding-name">{name}</span>
        <span class="holding-since">{duration}</span>
      </div>"""

    return f"""
    <p class='muted' style='font-size:13px;margin-bottom:10px'>
      Currently holds {count} product{'s' if count != 1 else ''}.
    </p>
    <div class="holdings-grid">{cards}</div>"""


def _recs_html(recs: pd.DataFrame) -> str:
    if recs.empty:
        return "<p class='muted'>No recommendations available.</p>"
    max_score = max(float(recs["score"].max()), 1e-9)
    rows = ""
    for _, r in recs.iterrows():
        pct = max(6, int(100 * float(r["score"]) / max_score))
        name = str(r["product"]).replace("_", " ").title()
        reason = str(r["reason"]).capitalize()
        rows += f"""
      <tr>
        <td class="rank">{int(r['rank'])}</td>
        <td class="prod">{name}</td>
        <td><div class="scorebar-wrap"><div class="scorebar" style="width:{pct}%"></div></div></td>
        <td class="reason">{reason}</td>
      </tr>"""
    return f"""
    <h4 style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:10px;
               letter-spacing:0.02em;text-transform:uppercase;">
      New Product Offering
    </h4>
    <table class="recs-table">
      <tr><th>#</th><th>Product</th><th>Likelihood</th><th>Reason</th></tr>
      {rows}
    </table>"""


def build() -> str:
    s = data.summary()
    lb = data.leaderboard()
    fc = data.forecasts()
    trends = data.product_trends()
    timeline = data.holdings_timeline()
    recs_all = data.recommendations()
    customers = data.customers()

    # pick the customer with the most lifetime adds for the static view
    top_cid = int(
        customers.sort_values("lifetime_product_adds", ascending=False)
        .iloc[0]["customer_id"]
    )
    recs = recs_all[recs_all["customer_id"] == top_cid].sort_values("rank")

    latest = s.get("latest_month", "")
    try:
        import datetime
        latest_label = datetime.datetime.strptime(latest, "%Y-%m-%d").strftime("%B %Y")
    except Exception:
        latest_label = latest

    lift = (
        s["champion_map_at_7"] / s["baseline_map_at_7"] - 1
        if s.get("baseline_map_at_7") else 0
    )
    model_labels = {
        "lightgbm": "Gradient Boosting",
        "blend_lgbm_cf": "Combined Approach",
        "item_item_cf": "Customer Similarity",
        "als_factorization": "Pattern Matching",
        "popularity_baseline": "Popularity Baseline",
    }
    champion_display = model_labels.get(
        s.get("champion_model", ""), s.get("champion_model", "").replace("_", " ").title()
    )

    # -- render figures -------------------------------------------------
    fig_lb = charts.model_leaderboard(lb)
    fig_fc = charts.adoption_forecast(fc, "payroll_deposit")
    fig_tl = charts.holdings_timeline(timeline, top_cid)
    fig_sm = charts.product_small_multiples(trends)

    html_lb = _fig_html(fig_lb, first=True)
    html_fc = _fig_html(fig_fc)
    html_tl = _fig_html(fig_tl)
    html_sm = _fig_html(fig_sm)

    css = CSS_PATH.read_text(encoding="utf-8") if CSS_PATH.exists() else ""

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Propensity Lab</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>{css}</style>
</head>
<body>
<div class="page">

  <!-- header -->
  <div class="header">
    <div>
      <h1>Propensity Lab</h1>
      <p class="muted">Which financial products is each customer most likely to add next?</p>
    </div>
    <div class="pills">
      <span class="pill">{s.get('months_loaded', '?')} months of history</span>
      <span class="pill pill-fresh">through {latest_label}</span>
    </div>
  </div>

  <!-- KPIs -->
  <div class="kpi-row">
    {_kpi_block("Customers Analyzed", f"{s.get('customers_scored', 0):,}")}
    {_kpi_block("Recommendation Accuracy", f"{s.get('champion_map_at_7', 0):.3f}",
                f"{lift:+.1%} better than guessing by popularity alone")}
    {_kpi_block("Best Performing Model", champion_display,
                "chosen by testing against actual customer behavior")}
    {_kpi_block("New Sign-Ups Expected Next Month",
                f"{s.get('projected_adds_next_month', 0):,}",
                "across all products, based on current trends")}
  </div>

  <!-- leaderboard + forecast -->
  <div class="grid-2">
    {_card("How Each Approach Compares",
           "Accuracy of every model tested against actual customer decisions "
           "from the last three months. Higher is better.",
           html_lb)}
    {_card("Six-Month Outlook",
           "How many customers are expected to sign up for Payroll Deposit each month. "
           "The shaded area shows the range of likely outcomes.",
           html_fc)}
  </div>

  <!-- customer view -->
  {_card("Individual Customer View",
         f"Products customer {top_cid} currently holds (left), with how long they have "
         "had each one. What to offer next is on the right.",
         f"""<div class="grid-2">
           <div>{_holdings_html(timeline, top_cid)}{html_tl}</div>
           <div>{_recs_html(recs)}</div>
         </div>""")}

  <!-- small multiples -->
  {_card("Where New Sign-Ups Are Coming From",
         "The most active products by new customers added each month. "
         "Each chart shows total sign-ups for the period and whether the trend is rising or falling.",
         html_sm)}

  <p class="muted footer">
    Based on historical retail banking customer data, 2015&#8211;2016.
  </p>

</div>
</body>
</html>"""

    out = DOCS_DIR / "index.html"
    out.write_text(page, encoding="utf-8")
    size_kb = round(out.stat().st_size / 1024)
    print(f"wrote {out}  ({size_kb} KB)")
    return str(out)


if __name__ == "__main__":
    build()
