"""Feature construction for the recommendation models.

Everything here is leakage-safe by construction: a transition row that
predicts adds in month t+1 only uses information available at month t
or earlier (holdings, add-recency, demographics). The target columns
are the 0 -> 1 product flips between t and t+1, matching the
fct_product_adds definition in the dbt layer.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config

PRODUCTS = list(config.PRODUCT_NAMES.values())

DEMOGRAPHICS = [
    "age", "tenure_months", "gross_income", "is_active", "gender",
    "segment", "held_product_count",
]


def load_wide() -> pd.DataFrame:
    """Certified customer-month snapshots from the dbt staging layer."""
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    cols = ", ".join(
        ["snapshot_date", "customer_id"] + DEMOGRAPHICS + PRODUCTS
    )
    df = con.execute(
        f"SELECT {cols} FROM main_staging.stg_customer_snapshots "
        "ORDER BY customer_id, snapshot_date"
    ).df()
    con.close()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.strftime("%Y-%m-%d")
    return df


def enrich(wide: pd.DataFrame) -> pd.DataFrame:
    """Add month index, held_<product> flags and add-recency features.

    Both the training transitions and the latest-month scoring frame
    are cut from this one enriched panel, so features are guaranteed to
    be computed identically in training and in production scoring.
    """
    months = sorted(wide["snapshot_date"].unique())
    order = {m: i for i, m in enumerate(months)}
    df = wide.copy()
    df["month_ix"] = df["snapshot_date"].map(order)
    for p in PRODUCTS:
        df[f"held_{p}"] = df[p].astype(np.int8)
    return _add_history_features(df)


def build_transitions(enriched: pd.DataFrame) -> pd.DataFrame:
    """One row per customer per consecutive month pair.

    Columns:
      target_month             month t+1 (the month being predicted)
      feature columns          state at month t
      y_<product>              1 if the product was added in t+1
      held_<product>           1 if already held at t (excluded from
                               candidates downstream)
    """
    months = sorted(enriched["snapshot_date"].unique())
    order = {m: i for i, m in enumerate(months)}
    nxt = enriched[["customer_id", "month_ix"] + PRODUCTS].copy()
    nxt["month_ix"] -= 1  # align month t+1 targets onto month t rows
    merged = enriched.merge(
        nxt, on=["customer_id", "month_ix"], suffixes=("", "_next"), how="inner"
    )

    for p in PRODUCTS:
        merged[f"y_{p}"] = ((merged[f"{p}_next"] == 1) & (merged[p] == 0)).astype(np.int8)
    merged = merged.drop(columns=[f"{p}_next" for p in PRODUCTS])

    merged["target_month"] = (merged["month_ix"] + 1).map(
        {i: m for m, i in order.items()}
    )
    return merged.drop(columns=["month_ix"])


def current_state(enriched: pd.DataFrame) -> pd.DataFrame:
    """Latest-month rows, ready for production scoring."""
    latest = enriched["month_ix"].max()
    return enriched[enriched["month_ix"] == latest].drop(columns=["month_ix"]).reset_index(drop=True)


def _add_history_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add-recency features computed from each customer's own past."""
    df = df.sort_values(["customer_id", "month_ix"]).reset_index(drop=True)
    add_any = np.zeros(len(df), dtype=np.int16)
    for p in PRODUCTS:
        prev = df.groupby("customer_id")[p].shift(1)
        add_any += ((df[p] == 1) & (prev == 0)).astype(np.int16)
    df["adds_this_month"] = add_any

    grp = df.groupby("customer_id")["adds_this_month"]
    df["adds_last_3m"] = (
        grp.rolling(3, min_periods=1).sum().reset_index(level=0, drop=True)
    )
    # months since the customer last added anything, capped at 12
    last_add_ix = np.where(df["adds_this_month"] > 0, df["month_ix"], np.nan)
    df["_last_add_ix"] = (
        pd.Series(last_add_ix).groupby(df["customer_id"]).ffill()
    )
    df["months_since_add"] = (df["month_ix"] - df["_last_add_ix"]).fillna(12).clip(0, 12)
    return df.drop(columns=["adds_this_month", "_last_add_ix"])


def feature_matrix(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Numeric design matrix for the gradient-boosting models."""
    X = pd.DataFrame(index=df.index)
    for p in PRODUCTS:
        X[f"holds_{p}"] = df[f"held_{p}"]
    X["held_product_count"] = df["held_product_count"]
    X["adds_last_3m"] = df["adds_last_3m"]
    X["months_since_add"] = df["months_since_add"]
    X["age"] = df["age"].fillna(df["age"].median())
    X["tenure_months"] = df["tenure_months"].fillna(0)
    X["log_income"] = np.log1p(df["gross_income"].fillna(df["gross_income"].median()))
    X["is_active"] = df["is_active"].astype(int)
    X["gender_flag"] = (df["gender"] == "V").astype(int)
    for seg in ("01 - TOP", "02 - PARTICULARES", "03 - UNIVERSITARIO"):
        X[f"seg_{seg[:2]}"] = (df["segment"] == seg).astype(int)
    return X.to_numpy(dtype=np.float32), list(X.columns)


def holdings_matrix(df: pd.DataFrame) -> np.ndarray:
    """Binary customer x product matrix from held_ columns."""
    return df[[f"held_{p}" for p in PRODUCTS]].to_numpy(dtype=np.float32)


def targets_matrix(df: pd.DataFrame) -> np.ndarray:
    return df[[f"y_{p}" for p in PRODUCTS]].to_numpy(dtype=np.int8)
