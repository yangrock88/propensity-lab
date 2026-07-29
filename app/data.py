"""Artifact access for the dashboard.

The app never queries the warehouse and never trains anything. It reads
the parquet and json artifacts published by the pipeline, cached in
memory and invalidated by file modification time, so a daily refresh
shows up without restarting the server.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config

_cache: dict[str, tuple[float, object]] = {}


def _load(name: str, reader) -> object:
    path = config.ARTIFACT_DIR / name
    mtime = path.stat().st_mtime
    hit = _cache.get(name)
    if hit and hit[0] == mtime:
        return hit[1]
    value = reader(path)
    _cache[name] = (mtime, value)
    return value


def summary() -> dict:
    return _load("summary.json", lambda p: json.loads(p.read_text()))


def leaderboard() -> pd.DataFrame:
    return _load("leaderboard.json", lambda p: pd.read_json(p))


def recommendations() -> pd.DataFrame:
    return _load("recommendations.parquet", pd.read_parquet)


def forecasts() -> pd.DataFrame:
    return _load("forecasts.parquet", pd.read_parquet)


def product_trends() -> pd.DataFrame:
    return _load("product_trends.parquet", pd.read_parquet)


def customers() -> pd.DataFrame:
    return _load("customers.parquet", pd.read_parquet)


def holdings_timeline() -> pd.DataFrame:
    return _load("holdings_timeline.parquet", pd.read_parquet)


def run_log() -> list[dict]:
    if not config.STATE_PATH.exists():
        return []
    return json.loads(config.STATE_PATH.read_text()).get("runs", [])


def customer_options(limit: int = 800) -> list[dict]:
    """A browsable subset of customers, busiest first."""
    df = customers().sort_values("lifetime_product_adds", ascending=False)
    ids = df["customer_id"].head(limit)
    return [{"label": f"Customer {c}", "value": int(c)} for c in ids]
