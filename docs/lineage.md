# Lineage and Ownership

Maintainer: Rocky Yang
Last reviewed: 2026-07-28

## Flow

Every layer reads only from the layer above it. There are no side doors:
the dashboard cannot reach the warehouse, the ML code cannot reach the raw
schema, and nothing writes to a layer it does not own.

    Kaggle CSV  or  pipeline/synth.py        (source)
        |
        v
    pipeline/ingest.py                        (landing)
        raw.customer_snapshots
        |
        v
    dbt: staging                              (certification)
        stg_customer_snapshots
        |
        v
    dbt: intermediate                         (shaping)
        int_holdings_long
        |
        v
    dbt: marts                                (business grain)
        fct_product_adds
        dim_customer
        agg_product_month
        |
        +--------------------------+
        v                          v
    ml/features.py             ml/forecast.py
    ml/models.py                   |
    ml/evaluate.py                 |
    ml/train.py                    |
        |                          |
        v                          v
    data/artifacts/*.parquet, *.json          (published product)
        |
        v
    app/ (Plotly Dash)                        (consumption)

The scheduler (scheduler.py) runs the left side top to bottom once a day.
The Dash app is a pure consumer: it polls artifact modification times and
re-renders when they change, so a refresh needs no app restart.

## Ownership

| Layer | Owner | Change process |
|---|---|---|
| Source contract (48-column Santander schema) | external | never edited; adapters live in ingest only |
| pipeline/ | Rocky Yang | code review; any schema change must update staging and this doc in the same change |
| dbt models and tests | Rocky Yang | dbt build must pass before merge; grain changes require a version note in the model description |
| ml/ | Rocky Yang | leaderboard from the walk-forward backtest must accompany any model change |
| artifacts contract | Rocky Yang | additive changes preferred; renaming or removing a field requires updating app/data.py in the same change |
| app/ | Rocky Yang | visual changes only; no data logic allowed in the app layer |

## Why the boundaries sit where they do

Renaming happens exactly once, in staging. Everyone downstream speaks the
business vocabulary (checking_account, credit_card), and nobody has to
remember that ind_tjcr_fin_ult1 means credit card.

The add-event definition lives in one dbt model, fct_product_adds. The
recommender's training target and the forecaster's input series both
derive from it, so the two systems can never quietly disagree about what
an "add" is.

Training is separated from serving by the artifact directory. A failed
refresh leaves yesterday's artifacts in place, which means the dashboard
degrades to stale rather than broken. Staleness is visible in the header
timestamp, so nobody is misled.
