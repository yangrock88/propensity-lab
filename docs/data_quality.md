# Data Quality and Operating Contract

Maintainer: Rocky Yang
Last reviewed: 2026-07-29

## Pipeline contract

This project uses a fixed historical dataset (Santander, 2015–2016). The
pipeline replays monthly snapshots sequentially, simulating how a production
warehouse would receive new monthly data. Running `scheduler.py` loads the
next snapshot, rebuilds dbt models, runs all tests, retrains the models, and
publishes dashboard artifacts.

- A full run completes in under five minutes on a laptop.
- Failure behavior: the run stops at the first failed step and logs the
  reason. Artifacts from the previous successful run stay in place so the
  dashboard continues serving correct data.

## Test coverage

All 20 checks run as part of `dbt build`. A run with any test failure
publishes nothing.

| Model | Tests |
|---|---|
| raw.customer_snapshots (source) | not_null on fecha_dato, ncodpers |
| stg_customer_snapshots | unique + not_null on snapshot_customer_key, not_null on snapshot_date and customer_id, accepted_values on segment |
| fct_product_adds | not_null on add_month, customer_id, product; accepted_values on product against the canonical 24-name list |
| dim_customer | unique + not_null on customer_id |
| agg_product_month | not_null on snapshot_date and product |

Current status: 20 checks (15 data tests, 5 model builds), all passing as of
the last review date.

## Known data issues and how they are handled

| Issue | Where it appears | Handling |
|---|---|---|
| Negative tenure (antiguedad = -999999) | real Kaggle file | floored at 0 in staging |
| Missing gross income | real file, roughly a quarter of rows | left null in staging; imputed with the median at feature time |
| Empty-string categoricals | real file | converted to null in staging so counts are honest |
| First loaded month has zero adds | fct_product_adds, by construction | forecaster drops the first month |
| Age outliers (under 18, over 100) | real file | kept in staging; accepted as known debt |

## Troubleshooting

1. A failed run writes `refresh_status = "failed"` into `data/state.json`
   and the full traceback into `logs/refresh.log`.
2. Reproduce or re-run: `uv run python scheduler.py`
3. If the warehouse is suspect, delete `data/warehouse.duckdb` and
   `data/state.json` and run the scheduler — the pipeline rebuilds
   everything from the source file or the generator deterministically.

## Snapshot cursor behavior

The cursor stops advancing once all 17 snapshot months are loaded.
Subsequent runs retrain on the full window, which is useful after code
changes. To replay from the beginning, clear `state.json`.
