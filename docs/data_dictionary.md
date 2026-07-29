# Data Dictionary

Maintainer: Rocky Yang
Last reviewed: 2026-07-28
Scope: every table and artifact the pipeline produces, from raw landing to
the files the dashboard reads.

Conventions used below:

- Grain is stated for every table. If a row count ever disagrees with the
  stated grain, treat it as an incident (see data_quality.md).
- Types are DuckDB types for warehouse tables and pandas/parquet types for
  artifacts.
- "Source" names the single upstream that feeds the column. No column has
  two sources.

---

## 1. raw.customer_snapshots

Landing table. One row per customer per monthly snapshot, in the original
Santander schema with Spanish column names. Rebuilt in full on every
pipeline run from the months loaded so far; the load is idempotent and
re-running a day never duplicates rows.

Grain: (fecha_dato, ncodpers)

| Column | Type | Meaning |
|---|---|---|
| fecha_dato | VARCHAR | Snapshot date, always the 28th of the month |
| ncodpers | BIGINT | Customer identifier |
| sexo | VARCHAR | Gender code, H or V |
| age | INTEGER | Age in years |
| fecha_alta | VARCHAR | Date the customer joined the bank |
| antiguedad | INTEGER | Tenure in months; negative values occur in the real file and are floored at 0 in staging |
| canal_entrada | VARCHAR | Acquisition channel code |
| nomprov | VARCHAR | Province name |
| ind_actividad_cliente | INTEGER | 1 if the bank considers the customer active |
| renta | DOUBLE | Gross household income; missing for a large share of real records |
| segmento | VARCHAR | Commercial segment: 01 - TOP, 02 - PARTICULARES, 03 - UNIVERSITARIO |
| ind_*_ult1 (24 columns) | TINYINT | Product ownership flags, 1 = held at this snapshot |

Source: either data/raw/train_ver2.csv (downloaded from Kaggle by the
owner; the competition license does not allow committing it) or the demo
generator in pipeline/synth.py, which emits the identical schema. The
pipeline picks the real file automatically whenever it exists.

## 2. main_staging.stg_customer_snapshots

The certified staging model. This is the only place where source columns
are renamed, typed and cleaned. Nothing downstream may reference the raw
schema.

Grain: (snapshot_date, customer_id), enforced by a uniqueness test on
snapshot_customer_key.

| Column | Type | Meaning | Cleaning applied |
|---|---|---|---|
| snapshot_date | DATE | Snapshot month | cast from fecha_dato |
| customer_id | BIGINT | Customer identifier | rows with null ncodpers are dropped |
| snapshot_customer_key | VARCHAR | Surrogate key for the grain test | concatenation |
| gender | VARCHAR | H or V | empty strings become null |
| age | INTEGER | Age in years | none |
| customer_since | DATE | Join date | cast |
| tenure_months | INTEGER | Months as a customer | floored at 0 |
| join_channel | VARCHAR | Acquisition channel | empty strings become null |
| province | VARCHAR | Province | empty strings become null |
| is_active | BOOLEAN | Active flag | null treated as inactive |
| gross_income | DOUBLE | Gross household income | none; nulls handled at feature time |
| segment | VARCHAR | Commercial segment | empty strings become null; accepted values tested |
| 24 product columns | TINYINT | Ownership flags, business names (see mapping) | none |
| held_product_count | INTEGER | Sum of the 24 flags | computed here so every consumer agrees on it |

Product name mapping (source flag -> business name): the full 24-row
mapping lives in config.py as PRODUCT_NAMES and is the canonical list.
Examples: ind_cco_fin_ult1 -> checking_account, ind_nomina_ult1 ->
payroll_deposit, ind_tjcr_fin_ult1 -> credit_card.

## 3. main_intermediate.int_holdings_long

Unpivoted holdings. One row per customer per product per month, with a
holds flag. Exists so that marts and exports never repeat the 24-column
unpivot logic.

Grain: (snapshot_date, customer_id, product)

## 4. main_marts.fct_product_adds

The core fact. One row per add event. An add means a product flag flipped
from 0 to 1 between two consecutive snapshots for the same customer. The
first loaded month produces no events because there is no prior month to
compare against.

Grain: (add_month, customer_id, product)

| Column | Type | Meaning |
|---|---|---|
| add_month | DATE | Month in which the product first appeared |
| customer_id | BIGINT | Who added it |
| product | VARCHAR | Business product name; accepted values tested against the canonical list |

This table is the training target for the recommender and the input
series for the adoption forecast. If its definition ever changes, both
models and all dashboard numbers change with it, so treat the definition
as frozen and version any change.

## 5. main_marts.dim_customer

Latest known attributes per customer plus a lifetime add count.

Grain: customer_id, enforced by a uniqueness test.

| Column | Meaning |
|---|---|
| customer_id | Identifier |
| gender, age, segment, province, join_channel | Latest snapshot values |
| tenure_months, gross_income, is_active | Latest snapshot values |
| held_product_count | Products held at the latest snapshot |
| lifetime_product_adds | Add events observed for this customer in the loaded window |

## 6. main_marts.agg_product_month

Product-month rollup used for trend charts and forecasting.

Grain: (snapshot_date, product)

| Column | Meaning |
|---|---|
| holders | Customers holding the product at the snapshot |
| adds | Customers who added it that month; zero in the first loaded month by construction |
| drops | Customers who dropped it that month |
| net_change | adds minus drops |

## 7. Published artifacts (data/artifacts/)

The dashboard reads only these files. They are the product contract: the
app never queries the warehouse and never trains anything.

| File | Grain / shape | Producer | Contents |
|---|---|---|---|
| summary.json | single object | ml/train.py | run timestamp, months loaded, champion model and MAP@7, baseline MAP@7, customers scored, projected adds next month |
| leaderboard.json | one row per model | ml/train.py | mean MAP@7 and precision@7 across backtest folds, lift vs baseline |
| backtest.parquet | one row per model per fold | ml/train.py | per-cutoff metrics behind the leaderboard |
| recommendations.parquet | one row per customer per rank (top 7) | ml/train.py | product, score, plain-language reason |
| forecasts.parquet | one row per product per month | ml/forecast.py | history and six months of forecast with an 80% band and backcast MAPE |
| product_trends.parquet | (snapshot_date, product) | export of agg_product_month | trend chart input |
| customers.parquet | one row per customer | export of dim_customer | lookup dropdown and context |
| holdings_timeline.parquet | (snapshot_date, customer_id, product) where held | export of int_holdings_long | customer timeline chart |

## 8. Operational state

| File | Purpose |
|---|---|
| data/state.json | Ingest cursor (months loaded) and the last 30 run outcomes, including dbt test counts and refresh status |
| logs/refresh.log | Append-only log of every scheduled refresh |
| data/warehouse.duckdb | The warehouse itself; safe to delete and rebuild from scratch |
| data/synth_panel.parquet | Cache of the demo generator output so every run sees the same panel |
