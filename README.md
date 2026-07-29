# Propensity Lab

[![Live Demo](https://img.shields.io/badge/Live%20Demo-GitHub%20Pages-4f46e5?logo=github)](https://yangrock88.github.io/propensity-lab/)

Per-customer product recommendations and adoption forecasts for a retail banking book, built on the public Santander dataset.

Two questions the system answers:

1. Which products is each customer most likely to add next? Top 7 per customer, each with a plain-language reason.
2. How many customers will add each product over the next six months? A forecast with an 80% confidence band and a validated error estimate.

Five models compete in a walk-forward backtest on each run and the winner publishes the recommendations. At the time of writing the champion is LightGBM at MAP@7 0.536 against a popularity baseline of 0.511. The whole leaderboard, including the model that loses to the baseline, is on the dashboard — a leaderboard that only shows winners is marketing.

## Stack

| Layer | Tool |
|---|---|
| Warehouse | DuckDB |
| Modeling and tests | dbt (dbt-duckdb) — 5 models, 20 schema checks per run |
| Pipelines and ML | Python: pandas, LightGBM, numpy ALS, statsmodels |
| Orchestration | scheduler.py |
| Dashboard | Plotly Dash (interactive) + GitHub Pages (static export) |

## Running it locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

    git clone https://github.com/yangrock88/propensity-lab
    cd propensity-lab
    uv sync
    uv run python scheduler.py    # builds the warehouse and trains the models (~2 min)
    uv run python app/app.py      # starts the dashboard

The first run loads eight months of data and trains the full model suite. Each later run adds one more month, the same way a production warehouse picks up a new monthly load.

## Using the real dataset

The Kaggle competition license does not allow redistributing the source file, so the repository ships with a synthetic generator that emits the same 48-column schema. To run on the real data, download `train_ver2.csv` from the Santander Product Recommendation competition on Kaggle and place it in `data/raw/`. The pipeline detects the file automatically and switches; every layer above the landing table is identical either way.

## Layout

    pipeline/      ingest + synthetic data generator
    dbt_project/   staging, intermediate and mart models with tests
    ml/            features, five models, walk-forward backtest, forecasting
    app/           Dash app — reads published artifacts only, never trains
    docs/          data dictionary, lineage, quality contract, model cards,
                   executive summary, design notes
    scheduler.py   pipeline orchestration — one step at a time, fail-safe
    config.py      every path and tunable constant in one place
    build_static.py  regenerates the GitHub Pages dashboard from current artifacts

## Documentation

- [Executive summary](docs/executive_summary.md) — the story, why each model exists, how to read the numbers
- [Model cards](docs/model_cards.md) — method, metrics and limitations per model
- [Data dictionary](docs/data_dictionary.md) — every table and artifact, with grain and cleaning rules
- [Lineage and ownership](docs/lineage.md)
- [Data quality and operating contract](docs/data_quality.md)
- [Design notes](docs/design_thinking.md)

## Evaluation

No random splits. For each of the three most recent months, the suite trains only on earlier months and is scored on the adds that actually happened in that month (MAP@7 and precision@7; products already held are excluded from each customer's candidate set). The leaderboard averages across folds. Forecasts are validated separately by backcasting the last three months per product before refitting on the full series — the resulting MAPE ships inside the forecast artifact and the uncertainty band on each chart comes from those backcast residuals.
