# Data Quality and Operating Contract

Maintainer: Rocky Yang
Last reviewed: 2026-07-28

## Refresh contract

- Cadence: daily, 06:30 local time, via the Windows Task Scheduler job
  NextProductDailyRefresh (registered by register_task.ps1).
- A run advances the warehouse by one monthly snapshot, rebuilds all dbt
  models, runs every schema test, retrains the model suite, backtests it,
  rescoring all customers, and republishes the dashboard artifacts.
- Budget: a full run completes in under five minutes on a laptop. The
  task's hard execution limit is one hour.
- Failure behavior: the run stops at the first failed step and logs the
  reason. Artifacts from the previous successful run stay in place, so the
  dashboard serves stale-but-correct data. Staleness is visible in the
  header pill ("refreshed ... UTC").

## Test coverage

All tests run on every refresh as part of dbt build. A refresh with any
test failure publishes nothing.

| Model | Tests |
|---|---|
| raw.customer_snapshots (source) | not_null on fecha_dato, ncodpers; freshness is implicit in the ingest cursor |
| stg_customer_snapshots | unique + not_null on snapshot_customer_key (grain), not_null on snapshot_date and customer_id, accepted_values on segment |
| fct_product_adds | not_null on add_month, customer_id, product; accepted_values on product against the canonical 24-name list |
| dim_customer | unique + not_null on customer_id |
| agg_product_month | not_null on snapshot_date and product |

Current status: 20 checks (15 data tests plus 5 model builds), all
passing as of the last review date.

## Known data issues and how they are handled

| Issue | Where it appears | Handling |
|---|---|---|
| Negative tenure (antiguedad = -999999) | real Kaggle file | floored at 0 in staging |
| Missing gross income | real file, roughly a quarter of rows | left null in staging; imputed with the median at feature time, never in the warehouse |
| Empty-string categoricals | real file | converted to null in staging so counts are honest |
| First loaded month has zero adds | fct_product_adds, by construction | forecaster drops the first month; documented in the model description |
| Age outliers (under 18, over 100) | real file | kept in staging; the feature layer clips through median imputation only when null. A stricter rule would belong in staging with a test, noted here as accepted debt |

## Escalation path

1. A failed refresh writes refresh_status = "failed" into data/state.json
   and the full traceback into logs/refresh.log.
2. The dashboard's pipeline health strip shows the last eight runs;
   a missing daily entry means the task did not fire (check Task
   Scheduler history), a "failed" entry means it fired and broke.
3. Reproduce interactively with: uv run python scheduler.py
4. If the warehouse itself is suspect, delete data/warehouse.duckdb and
   data/state.json and run the scheduler once; the pipeline rebuilds
   everything from the source file or the generator deterministically.

## Slowly changing behavior to watch

The ingest cursor stops advancing once all 17 snapshot months are loaded.
From that point on, daily runs still retrain and republish (useful after
code changes) but the data stops moving. Swapping in the real Kaggle file
resets nothing by itself; clear state.json to replay the load from the
beginning.
