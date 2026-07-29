"""Generates a self-contained static HTML dashboard from the current artifacts.

Run from the project root:
    uv run python build_static.py

Output:
    docs/index.html

All Plotly charts are embedded as inline JavaScript and remain fully
interactive (hover, zoom, pan). The customer selector is a native HTML
dropdown backed by pre-rendered data for the top 20 customers — no
server required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import charts, data

CSS_PATH = Path("app/assets/style.css")
DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)

TOP_CUSTOMERS = 20  # number of customers pre-rendered for the JS dropdown


# ---------------------------------------------------------------------------
# HTML fragment helpers
# ---------------------------------------------------------------------------

def _fig_html(fig, first: bool = False) -> str:
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
    df = timeline[timeline["customer_id"] == customer_id].copy()
    if df.empty:
        return "<p class='muted'>No product history on record.</p>"
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    latest = df["snapshot_date"].max()
    currently_held = set(df[df["snapshot_date"] == latest]["product"])
    first_seen = df.groupby("product")["snapshot_date"].min()
    if not currently_held:
        return "<p class='muted'>No products held at the latest snapshot.</p>"

    def _dur(since_dt: pd.Timestamp) -> str:
        months = (latest.year - since_dt.year) * 12 + (latest.month - since_dt.month)
        if months < 1:
            return "less than a month"
        if months < 12:
            return f"{months} month{'s' if months != 1 else ''}"
        yrs, mos = divmod(months, 12)
        return f"{yrs}y {mos}m" if mos else f"{yrs} year{'s' if yrs != 1 else ''}"

    count = len(currently_held)
    cards = "".join(
        f"""<div class="holding-card">
          <span class="holding-name">{p.replace('_', ' ').title()}</span>
          <span class="holding-since">{_dur(first_seen.get(p, latest))}</span>
        </div>"""
        for p in sorted(currently_held)
    )
    return (
        f"<p class='muted' style='font-size:13px;margin-bottom:10px'>"
        f"Currently holds {count} product{'s' if count != 1 else ''}.</p>"
        f"<div class='holdings-grid'>{cards}</div>"
    )


def _recs_html(recs: pd.DataFrame) -> str:
    if recs.empty:
        return "<p class='muted'>No recommendations available.</p>"
    max_score = max(float(recs["score"].max()), 1e-9)
    rows = "".join(
        f"""<tr>
          <td class="rank">{int(r['rank'])}</td>
          <td class="prod">{str(r['product']).replace('_', ' ').title()}</td>
          <td><div class="scorebar-wrap">
            <div class="scorebar" style="width:{max(6, int(100*float(r['score'])/max_score))}%"></div>
          </div></td>
          <td class="reason">{str(r['reason']).capitalize()}</td>
        </tr>"""
        for _, r in recs.iterrows()
    )
    return (
        "<h4 style='font-size:13px;font-weight:600;color:#0f172a;margin-bottom:10px;"
        "letter-spacing:0.02em;text-transform:uppercase;'>New Product Offering</h4>"
        "<table class='recs-table'>"
        "<tr><th>#</th><th>Product</th><th>Likelihood</th><th>Reason</th></tr>"
        f"{rows}</table>"
    )


def _build_customer_data(
    timeline: pd.DataFrame,
    recs_all: pd.DataFrame,
    customers_df: pd.DataFrame,
) -> tuple[dict, list[int]]:
    """Pre-render holdings + recs HTML for the top N customers."""
    top_ids = (
        customers_df
        .sort_values("lifetime_product_adds", ascending=False)
        .head(TOP_CUSTOMERS)["customer_id"]
        .astype(int)
        .tolist()
    )
    result: dict[int, dict] = {}
    for cid in top_ids:
        mine = recs_all[recs_all["customer_id"] == cid].sort_values("rank")
        result[cid] = {
            "holdings": _holdings_html(timeline, cid),
            "recs": _recs_html(mine),
        }
    return result, top_ids


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build() -> str:
    s = data.summary()
    lb = data.leaderboard()
    fc = data.forecasts()
    trends = data.product_trends()
    timeline = data.holdings_timeline()
    recs_all = data.recommendations()
    customers_df = data.customers()

    customer_data, top_ids = _build_customer_data(timeline, recs_all, customers_df)
    first_cid = top_ids[0]

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
        s.get("champion_model", ""),
        s.get("champion_model", "").replace("_", " ").title(),
    )

    # figures — Plotly CDN loaded once via the leaderboard chart
    fig_lb = charts.model_leaderboard(lb)
    fig_fc = charts.adoption_forecast(fc, "payroll_deposit")
    fig_sm = charts.product_small_multiples(trends)

    html_lb = _fig_html(fig_lb, first=True)
    html_fc = _fig_html(fig_fc)
    html_sm = _fig_html(fig_sm)

    css = CSS_PATH.read_text(encoding="utf-8") if CSS_PATH.exists() else ""

    # customer dropdown options
    select_options = "\n".join(
        f'<option value="{cid}">Customer {cid}</option>' for cid in top_ids
    )

    # pre-rendered customer data serialised for JS
    js_data = json.dumps(customer_data)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Propensity Lab</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
{css}
.cust-select {{
  display: block;
  max-width: 260px;
  width: 100%;
  margin-bottom: 14px;
  padding: 8px 12px;
  border: 1px solid #e7eaf0;
  border-radius: 8px;
  font-size: 13.5px;
  font-family: Inter, "Segoe UI", sans-serif;
  color: #0f172a;
  background: #ffffff;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(15,23,42,0.04);
}}
.cust-select:focus {{ outline: none; border-color: #4f46e5; box-shadow: 0 0 0 3px #eef2ff; }}
  </style>
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
    {_kpi_block("New Sign-Ups Expected",
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
           "Customers expected to sign up for Payroll Deposit each month. "
           "The shaded area shows the range of likely outcomes.",
           html_fc)}
  </div>

  <!-- customer view with JS dropdown -->
  {_card("Individual Customer View",
         "Products this customer currently holds on the left, with how long they have "
         "had each one. What to offer next is on the right.",
         f"""
    <select class="cust-select" id="cust-select" onchange="pickCustomer(this.value)">
      {select_options}
    </select>
    <div class="grid-2">
      <div id="cust-holdings"></div>
      <div id="cust-recs"></div>
    </div>
    <script>
      const CDATA = {js_data};
      function pickCustomer(id) {{
        document.getElementById('cust-holdings').innerHTML = CDATA[id].holdings;
        document.getElementById('cust-recs').innerHTML    = CDATA[id].recs;
      }}
      pickCustomer('{first_cid}');
    </script>""")}

  <!-- small multiples -->
  {_card("Where New Sign-Ups Are Coming From",
         "The most active products by new customers added each month. "
         "Each chart shows total sign-ups for the period and whether the trend is rising or falling.",
         html_sm)}

  <p class="muted footer">Based on historical retail banking customer data, 2015&#8211;2016.</p>

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
