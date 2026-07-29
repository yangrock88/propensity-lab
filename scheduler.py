"""Daily refresh orchestrator.

One run advances the warehouse by a month of data and rebuilds every
layer above it, in order:

1. ingest    - land the next monthly snapshot in DuckDB
2. dbt build - rebuild staging and mart models, run all schema tests
3. train     - backtest the model suite, rescore customers, forecast

If any step fails the run stops there, the failure is logged, and the
dashboard keeps serving yesterday's artifacts. A broken run never
publishes half-finished data.

Run by hand:            uv run python scheduler.py
Register the daily job: powershell -File register_task.ps1
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config

log = logging.getLogger("refresh")


def _setup_logging() -> None:
    config.ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_DIR / "refresh.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _step_ingest() -> dict:
    from pipeline import ingest

    return ingest.run()


def _step_dbt() -> dict:
    """Build all dbt models and run every schema test in one pass.

    dbt runs in a subprocess on purpose: its DuckDB adapter holds the
    warehouse file open for the life of the process, which would block
    the training step from connecting afterwards.
    """
    project_dir = config.PROJECT_ROOT / "dbt_project"
    env = os.environ.copy()
    # dbt resolves the profile's relative db path against the process
    # working directory, which Task Scheduler does not guarantee. Pin it.
    env["NEXTPRODUCT_DB"] = str(config.DUCKDB_PATH)

    proc = subprocess.run(
        [
            sys.executable, "-c", "from dbt.cli.main import cli; cli()", "build",
            "--project-dir", str(project_dir),
            "--profiles-dir", str(project_dir),
        ],
        capture_output=True, text=True, env=env,
        cwd=config.PROJECT_ROOT, timeout=900,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-8:])
        raise RuntimeError(f"dbt build failed (exit {proc.returncode}):\n{tail}")

    results_path = project_dir / "target" / "run_results.json"
    counts: dict[str, int] = {}
    for node in json.loads(results_path.read_text())["results"]:
        key = f"{node['unique_id'].split('.')[0]}_{node['status']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _step_train() -> dict:
    from ml import train

    return train.run()


def _record(status: str, detail: dict) -> None:
    """Append the outcome to the state file so the dashboard's health
    strip can show it without reading log files."""
    state = json.loads(config.STATE_PATH.read_text()) if config.STATE_PATH.exists() else {}
    runs = state.get("runs", [])
    if runs:
        runs[-1]["refresh_status"] = status
        runs[-1].update(detail)
    state["runs"] = runs[-30:]
    config.STATE_PATH.write_text(json.dumps(state, indent=2))


def run() -> int:
    _setup_logging()
    started = time.monotonic()
    log.info("refresh starting")

    try:
        info = _step_ingest()
        log.info("ingest done: months=%s rows=%s", info["months_loaded"], info["rows"])

        dbt_counts = _step_dbt()
        log.info("dbt build done: %s", dbt_counts)

        summary = _step_train()
        log.info(
            "train done: champion=%s map@7=%s",
            summary["champion_model"], summary["champion_map_at_7"],
        )
    except Exception:
        log.exception("refresh failed")
        _record("failed", {"failed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return 1

    elapsed = round(time.monotonic() - started, 1)
    _record("ok", {"dbt": dbt_counts, "refresh_s": elapsed})
    log.info("refresh complete in %ss", elapsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
