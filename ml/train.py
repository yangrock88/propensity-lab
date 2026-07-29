"""Train, backtest, score and publish artifacts.

This is the ML step of the daily refresh. It never talks to the
dashboard directly: it writes versioned artifacts to data/artifacts and
the Dash app reads only those. Order of operations:

1. walk-forward backtest of the full model suite (honest evaluation)
2. refit the suite on all loaded history
3. score every customer at the latest snapshot, keep top 7 per customer
4. attach a plain-language reason to each recommendation
5. run the adoption forecast
6. export the dashboard datasets and a summary of the run
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from ml import evaluate, features, forecast, models
from ml.features import PRODUCTS

LABELS = {p: p.replace("_", " ").title() for p in PRODUCTS}


def _reasons(cf: models.ItemItemCF, held: np.ndarray, product_ix: np.ndarray) -> list[str]:
    out = []
    for row_held, j in zip(held, product_ix):
        driver = cf.top_driver(row_held, j)
        if driver is None:
            out.append(f"broad uptake of {LABELS[PRODUCTS[j]]} across the book")
        else:
            out.append(f"customers holding {LABELS[PRODUCTS[driver]]} often add this next")
    return out


def _recommendations(suite: list, current: pd.DataFrame, champion_name: str) -> pd.DataFrame:
    champion = next(m for m in suite if m.name == champion_name)
    cf = next(m for m in suite if isinstance(m, models.ItemItemCF))

    scores = evaluate._masked_scores(champion, current)
    top = np.argsort(-scores, axis=1)[:, : config.TOP_K]
    held = features.holdings_matrix(current)

    rows = []
    for i, customer_id in enumerate(current["customer_id"]):
        for rank, j in enumerate(top[i], start=1):
            if not np.isfinite(scores[i, j]):
                break  # customer already holds everything rankable
            rows.append((customer_id, rank, PRODUCTS[j], float(scores[i, j]), i, j))
    rec = pd.DataFrame(
        rows, columns=["customer_id", "rank", "product", "score", "_i", "_j"]
    )
    rec["reason"] = _reasons(cf, held[rec["_i"]], rec["_j"].to_numpy())
    return rec.drop(columns=["_i", "_j"])


def _export_dashboard_tables() -> None:
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    con.execute(
        f"COPY (SELECT * FROM main_marts.agg_product_month) TO "
        f"'{(config.ARTIFACT_DIR / 'product_trends.parquet').as_posix()}' (FORMAT PARQUET)"
    )
    con.execute(
        f"COPY (SELECT * FROM main_marts.dim_customer) TO "
        f"'{(config.ARTIFACT_DIR / 'customers.parquet').as_posix()}' (FORMAT PARQUET)"
    )
    con.execute(
        f"COPY (SELECT snapshot_date, customer_id, product FROM "
        f"main_intermediate.int_holdings_long WHERE holds = 1) TO "
        f"'{(config.ARTIFACT_DIR / 'holdings_timeline.parquet').as_posix()}' (FORMAT PARQUET)"
    )
    con.close()


def run() -> dict:
    config.ensure_dirs()
    started = datetime.now(timezone.utc)

    wide = features.load_wide()
    enriched = features.enrich(wide)
    transitions = features.build_transitions(enriched)

    backtest = evaluate.walk_forward(transitions)
    lb = evaluate.leaderboard(backtest)
    champion_name = lb.iloc[0]["model"]

    suite = models.build_suite(transitions)
    current = features.current_state(enriched)
    recs = _recommendations(suite, current, champion_name)

    fc = forecast.run()
    next_month = fc[fc["kind"] == "forecast"]["month"].min()
    projected_adds = float(
        fc[(fc["kind"] == "forecast") & (fc["month"] == next_month)]["adds"].sum()
    )

    backtest.to_parquet(config.ARTIFACT_DIR / "backtest.parquet", index=False)
    recs.to_parquet(config.ARTIFACT_DIR / "recommendations.parquet", index=False)
    fc.to_parquet(config.ARTIFACT_DIR / "forecasts.parquet", index=False)
    lb.to_json(config.ARTIFACT_DIR / "leaderboard.json", orient="records", indent=2)
    _export_dashboard_tables()

    state = json.loads(config.STATE_PATH.read_text()) if config.STATE_PATH.exists() else {}
    last_run = (state.get("runs") or [{}])[-1]
    summary = {
        "run_ts": started.isoformat(timespec="seconds"),
        "duration_s": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        "source": last_run.get("source", "unknown"),
        "months_loaded": last_run.get("months_loaded"),
        "latest_month": last_run.get("latest_month"),
        "customers_scored": int(current["customer_id"].nunique()),
        "champion_model": champion_name,
        "champion_map_at_7": round(float(lb.iloc[0]["map_at_7"]), 4),
        "baseline_map_at_7": round(
            float(lb.loc[lb["model"] == "popularity_baseline", "map_at_7"].iloc[0]), 4
        ),
        "projected_adds_next_month": round(projected_adds),
    }
    (config.ARTIFACT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(
        f"train ok | champion={champion_name} map@7={summary['champion_map_at_7']} "
        f"(baseline {summary['baseline_map_at_7']}) recs={len(recs):,} "
        f"in {summary['duration_s']}s"
    )
    return summary


if __name__ == "__main__":
    run()
