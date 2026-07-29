# Propensity Lab

Daily-refreshed product recommendations and adoption forecasts for a
retail bank, built on the public Santander product dataset schema.

Two questions, answered every morning:

1. Which products is each customer most likely to add next month?
   Top 7 per customer, each with a reason in plain language.
2. How many customers will add each product over the next six months?
   A forecast with an 80% band and a validated error estimate.

Five models compete in a walk-forward backtest on every refresh and the
winner publishes the recommendations. At the time of writing the
champion is LightGBM at MAP@7 0.536 against a popularity baseline of
0.511. The whole leaderboard, including the model that loses to the
baseline, is on the dashboard, because a leaderboard that only shows
winners is marketing.

## Stack

| Layer | Tool |
|---|---|
| Warehouse | DuckDB |
| Modeling and tests | dbt (dbt-duckdb), 5 models, 20 checks per run |
| Pipelines and ML | Python: pandas, LightGBM, numpy ALS, statsmodels |
| Orchestration | scheduler.py + Windows Task Scheduler, daily |
| Dashboard | Plotly Dash |

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

    git clone <repo-url>
    cd nextproduct
    uv sync
    uv run python scheduler.py       # first full pipeline run, ~2 min
    uv run python app/app.py         # dashboard at http://127.0.0.1:8050

The first run generates a demo panel (20,000 customers, monthly
snapshots) with realistic cross-sell structure, loads the first eight
months, builds and tests the dbt models, backtests the model suite and
publishes the dashboard artifacts. Each later run loads one more month,
which is how a daily warehouse load is simulated.

To schedule the daily refresh:

    powershell -ExecutionPolicy Bypass -File register_task.ps1

## Using the real dataset

The Kaggle competition license does not allow redistributing the file,
so the repository ships with a generator that emits the same 48-column
schema. To run on the real data instead, download train_ver2.csv from
the Santander Product Recommendation competition on Kaggle, place it at
data/raw/train_ver2.csv, delete data/state.json and data/warehouse.duckdb,
and run the scheduler. The pipeline detects the file and switches
automatically; every layer above the landing table is identical either way.

## Layout

    pipeline/      ingest + demo generator
    dbt_project/   staging, intermediate and mart models with tests
    ml/            features, five models, walk-forward backtest, forecasting
    app/           Dash app; reads published artifacts only, never trains
    docs/          data dictionary, lineage, quality contract, model cards,
                   executive summary, design notes
    scheduler.py   the daily refresh, one step at a time, fail-safe
    config.py      every path and constant in one place

## Documentation

- [Executive summary](docs/executive_summary.md): the story, why each
  model exists, and how to read the numbers
- [Model cards](docs/model_cards.md): method, metrics and limitations
  per model
- [Data dictionary](docs/data_dictionary.md): every table and artifact,
  with grain and cleaning rules
- [Lineage and ownership](docs/lineage.md)
- [Data quality and operating contract](docs/data_quality.md)
- [Design notes](docs/design_thinking.md)

## Evaluation in one paragraph

No random splits. For each of the three most recent months, the suite
trains only on earlier months and is scored on the adds that actually
happened in that month (MAP@7 and precision@7, products already held are
excluded from a customer's candidates). The leaderboard averages the
folds. Forecasts are validated separately by backcasting the last three
months per product before refitting on the full series; the resulting
MAPE ships inside the forecast artifact and the band on the chart comes
from those backcast residuals.
