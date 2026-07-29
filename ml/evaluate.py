"""Walk-forward backtesting for the recommendation suite.

No random splits. For each cutoff month m in the most recent folds, the
suite trains only on transitions whose target month is before m, then
predicts the adds that actually happened in m. That mirrors exactly how
the system is used in production: score today, get judged next month.

Metrics:
  MAP@7        mean average precision over customers who added at least
               one product in the target month (the metric used by the
               original Kaggle competition)
  precision@7  share of the top 7 recommendations that were added
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
from ml import features, models
from ml.features import PRODUCTS


def _masked_scores(model, rows: pd.DataFrame) -> np.ndarray:
    """Raw model scores with already-held products pushed to -inf."""
    scores = model.score(rows).astype(np.float64)
    held = features.holdings_matrix(rows) == 1
    scores[held] = -np.inf
    return scores


def _ap_at_k(pred: np.ndarray, actual: set[int], k: int) -> float:
    hits, score = 0, 0.0
    for i, p in enumerate(pred[:k]):
        if p in actual:
            hits += 1
            score += hits / (i + 1)
    return score / min(len(actual), k)


def score_fold(model, eval_rows: pd.DataFrame, k: int = config.TOP_K) -> dict:
    scores = _masked_scores(model, eval_rows)
    top = np.argsort(-scores, axis=1)[:, :k]
    Y = features.targets_matrix(eval_rows)

    aps, precs = [], []
    for i in range(len(eval_rows)):
        actual = set(np.nonzero(Y[i])[0])
        if not actual:
            continue  # MAP is defined over customers with adds
        aps.append(_ap_at_k(top[i], actual, k))
        precs.append(len(set(top[i]) & actual) / k)

    return {
        "map_at_7": float(np.mean(aps)) if aps else 0.0,
        "precision_at_7": float(np.mean(precs)) if precs else 0.0,
        "customers_with_adds": len(aps),
    }


def walk_forward(transitions: pd.DataFrame,
                 folds: int = config.BACKTEST_FOLDS) -> pd.DataFrame:
    """Backtest every model across the last `folds` target months."""
    months = sorted(transitions["target_month"].unique())
    cutoffs = months[-folds:]
    results = []

    for cutoff in cutoffs:
        train = transitions[transitions["target_month"] < cutoff]
        eval_rows = transitions[transitions["target_month"] == cutoff]
        if train["target_month"].nunique() < 2 or eval_rows.empty:
            continue
        suite = models.build_suite(train)
        for model in suite:
            metrics = score_fold(model, eval_rows)
            results.append({"model": model.name, "cutoff_month": cutoff, **metrics})

    df = pd.DataFrame(results)
    return df


def leaderboard(backtest: pd.DataFrame) -> pd.DataFrame:
    """Average metrics per model across folds, best first."""
    lb = (
        backtest.groupby("model")
        .agg(
            map_at_7=("map_at_7", "mean"),
            precision_at_7=("precision_at_7", "mean"),
            folds=("cutoff_month", "nunique"),
        )
        .sort_values("map_at_7", ascending=False)
        .reset_index()
    )
    base = lb.loc[lb["model"] == "popularity_baseline", "map_at_7"]
    baseline = float(base.iloc[0]) if len(base) else np.nan
    lb["lift_vs_baseline"] = (lb["map_at_7"] / baseline).round(3)
    return lb
