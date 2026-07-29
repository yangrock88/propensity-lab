"""Product adoption forecasting.

Projects monthly add counts per product using damped-trend exponential
smoothing. The method is deliberately conservative: with under two
years of monthly history there is no support for seasonal terms or
heavier models, and damping keeps short-history trends from running
away. Each product is validated by backcasting the last three months
before refitting on the full series.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config

VALIDATION_MONTHS = 3
MIN_HISTORY = 6  # below this, fall back to the trailing mean


def load_series() -> pd.DataFrame:
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    df = con.execute(
        """
        SELECT snapshot_date, product, adds
        FROM main_marts.agg_product_month
        ORDER BY product, snapshot_date
        """
    ).df()
    con.close()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    # the first loaded month has no prior snapshot, so its adds are zero
    # by construction; drop it rather than teach the model a fake dip
    first = df["snapshot_date"].min()
    return df[df["snapshot_date"] > first].reset_index(drop=True)


def _fit_ets(y: np.ndarray, horizon: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(
            y, trend="add", damped_trend=True, initialization_method="estimated"
        ).fit()
        return np.asarray(model.forecast(horizon))


def _forecast_one(y: np.ndarray, horizon: int) -> tuple[np.ndarray, float, np.ndarray]:
    """Returns (forecast, backcast mape, residual std per step)."""
    if len(y) < MIN_HISTORY or y.std() == 0:
        mean = float(y[-3:].mean()) if len(y) else 0.0
        fc = np.full(horizon, mean)
        return fc, np.nan, np.full(horizon, max(y.std(), 1.0))

    v = VALIDATION_MONTHS
    train, holdout = y[:-v], y[-v:]
    try:
        back = _fit_ets(train, v)
    except Exception:
        back = np.full(v, train.mean())
    denom = np.clip(np.abs(holdout), 1.0, None)
    mape = float(np.mean(np.abs(back - holdout) / denom))

    try:
        fc = _fit_ets(y, horizon)
    except Exception:
        fc = np.full(horizon, y[-3:].mean())
    resid_std = float(np.std(back - holdout)) or float(y.std())
    band = resid_std * np.sqrt(np.arange(1, horizon + 1))
    return np.clip(fc, 0, None), mape, band


def run(horizon: int = config.FORECAST_HORIZON) -> pd.DataFrame:
    """Forecast every product. Output has history and future rows."""
    series = load_series()
    frames = []
    for product, grp in series.groupby("product"):
        grp = grp.sort_values("snapshot_date")
        y = grp["adds"].to_numpy(dtype=float)
        fc, mape, band = _forecast_one(y, horizon)

        hist = pd.DataFrame(
            {
                "product": product,
                "month": grp["snapshot_date"],
                "adds": y,
                "kind": "actual",
                "lo": np.nan,
                "hi": np.nan,
                "backcast_mape": mape,
            }
        )
        last = grp["snapshot_date"].max()
        future_months = pd.DatetimeIndex(
            [last + pd.DateOffset(months=i) for i in range(1, horizon + 1)]
        )
        fut = pd.DataFrame(
            {
                "product": product,
                "month": future_months,
                "adds": fc,
                "kind": "forecast",
                "lo": np.clip(fc - 1.28 * band, 0, None),
                "hi": fc + 1.28 * band,
                "backcast_mape": mape,
            }
        )
        frames.append(pd.concat([hist, fut], ignore_index=True))
    return pd.concat(frames, ignore_index=True)
