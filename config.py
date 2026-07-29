"""Central configuration for the pipeline, warehouse and app.

Every path flows from PROJECT_ROOT so the project can be cloned anywhere
and still run. Nothing here needs editing for a default local install.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
ARTIFACT_DIR = DATA_DIR / "artifacts"
LOG_DIR = PROJECT_ROOT / "logs"

DUCKDB_PATH = DATA_DIR / "warehouse.duckdb"
STATE_PATH = DATA_DIR / "state.json"
SYNTH_CACHE = DATA_DIR / "synth_panel.parquet"

# Real Kaggle file, if the owner has downloaded it. Optional.
KAGGLE_CSV = RAW_DIR / "train_ver2.csv"

# Snapshot calendar mirrors the public Santander dataset: 17 monthly
# snapshots dated on the 28th, January 2015 through May 2016.
SNAPSHOT_MONTHS = [
    f"{y}-{m:02d}-28"
    for y, months in ((2015, range(1, 13)), (2016, range(1, 6)))
    for m in months
]

# How many snapshots the very first run loads, so models have history
# from day one. Each later run loads one more month until caught up.
INITIAL_MONTHS = 8

# Synthetic panel size. 20k customers x 17 months keeps a full refresh
# under a few minutes on a laptop while leaving room for real signal.
SYNTH_CUSTOMERS = 20_000
SYNTH_SEED = 20260728

# The 24 product flags from the source schema, in canonical order.
PRODUCT_COLS = [
    "ind_ahor_fin_ult1", "ind_aval_fin_ult1", "ind_cco_fin_ult1",
    "ind_cder_fin_ult1", "ind_cno_fin_ult1", "ind_ctju_fin_ult1",
    "ind_ctma_fin_ult1", "ind_ctop_fin_ult1", "ind_ctpp_fin_ult1",
    "ind_deco_fin_ult1", "ind_deme_fin_ult1", "ind_dela_fin_ult1",
    "ind_ecue_fin_ult1", "ind_fond_fin_ult1", "ind_hip_fin_ult1",
    "ind_plan_fin_ult1", "ind_pres_fin_ult1", "ind_reca_fin_ult1",
    "ind_tjcr_fin_ult1", "ind_valo_fin_ult1", "ind_viv_fin_ult1",
    "ind_nomina_ult1", "ind_nom_pens_ult1", "ind_recibo_ult1",
]

# Plain-English names used from the staging layer onward.
PRODUCT_NAMES = {
    "ind_ahor_fin_ult1": "savings_account",
    "ind_aval_fin_ult1": "guarantee",
    "ind_cco_fin_ult1": "checking_account",
    "ind_cder_fin_ult1": "derivatives",
    "ind_cno_fin_ult1": "payroll_account",
    "ind_ctju_fin_ult1": "junior_account",
    "ind_ctma_fin_ult1": "particular_plus_account",
    "ind_ctop_fin_ult1": "particular_account",
    "ind_ctpp_fin_ult1": "premium_account",
    "ind_deco_fin_ult1": "short_term_deposit",
    "ind_deme_fin_ult1": "medium_term_deposit",
    "ind_dela_fin_ult1": "long_term_deposit",
    "ind_ecue_fin_ult1": "e_account",
    "ind_fond_fin_ult1": "investment_fund",
    "ind_hip_fin_ult1": "mortgage",
    "ind_plan_fin_ult1": "pension_plan",
    "ind_pres_fin_ult1": "personal_loan",
    "ind_reca_fin_ult1": "tax_payment_service",
    "ind_tjcr_fin_ult1": "credit_card",
    "ind_valo_fin_ult1": "securities",
    "ind_viv_fin_ult1": "home_account",
    "ind_nomina_ult1": "payroll_deposit",
    "ind_nom_pens_ult1": "pension_deposit",
    "ind_recibo_ult1": "direct_debit",
}

# Demographic and account columns carried into the warehouse.
CUSTOMER_COLS = [
    "fecha_dato", "ncodpers", "sexo", "age", "fecha_alta", "antiguedad",
    "canal_entrada", "nomprov", "ind_actividad_cliente", "renta",
    "segmento",
]

# Backtest: how many of the most recent loaded months serve as
# walk-forward evaluation cutoffs.
BACKTEST_FOLDS = 3

# Forecast horizon in months for product adoption projections.
FORECAST_HORIZON = 6

TOP_K = 7  # recommendations per customer, matches the MAP@7 convention


def ensure_dirs() -> None:
    for d in (DATA_DIR, RAW_DIR, ARTIFACT_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
