"""Ingestion: land monthly snapshots into the DuckDB warehouse.

Two sources, one contract:

* Real mode  - data/raw/train_ver2.csv downloaded from Kaggle by the
  owner (the license does not allow us to ship it).
* Demo mode  - the synthetic panel from pipeline.synth, same schema.

Each scheduled run advances a cursor by one month, which simulates a
warehouse receiving its nightly load. The raw table is rebuilt
idempotently from the months loaded so far: re-running a day never
duplicates rows.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from pipeline import synth


def _read_state() -> dict:
    if config.STATE_PATH.exists():
        return json.loads(config.STATE_PATH.read_text())
    return {"months_loaded": 0, "runs": []}


def _write_state(state: dict) -> None:
    config.STATE_PATH.write_text(json.dumps(state, indent=2))


def _advance_cursor(state: dict) -> int:
    total = len(config.SNAPSHOT_MONTHS)
    n = state["months_loaded"]
    n = config.INITIAL_MONTHS if n == 0 else min(n + 1, total)
    state["months_loaded"] = n
    return n


def _load_real(con: duckdb.DuckDBPyConnection, months: list[str]) -> None:
    cols = ", ".join(
        [
            "fecha_dato", "TRY_CAST(ncodpers AS BIGINT) AS ncodpers",
            "sexo", "TRY_CAST(TRIM(age) AS INTEGER) AS age", "fecha_alta",
            "TRY_CAST(TRIM(antiguedad) AS INTEGER) AS antiguedad",
            "canal_entrada", "nomprov",
            "TRY_CAST(ind_actividad_cliente AS INTEGER) AS ind_actividad_cliente",
            "TRY_CAST(renta AS DOUBLE) AS renta", "segmento",
        ]
        + [f"COALESCE(TRY_CAST({p} AS TINYINT), 0) AS {p}" for p in config.PRODUCT_COLS]
    )
    month_list = ", ".join(f"'{m}'" for m in months)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw.customer_snapshots AS
        SELECT {cols}
        FROM read_csv_auto('{config.KAGGLE_CSV.as_posix()}', all_varchar=true)
        WHERE fecha_dato IN ({month_list})
        """
    )


def _load_synth(con: duckdb.DuckDBPyConnection, months: list[str]) -> None:
    panel = synth.generate_panel()
    subset = panel[panel["fecha_dato"].isin(months)]
    con.register("panel_df", subset)
    con.execute(
        "CREATE OR REPLACE TABLE raw.customer_snapshots AS SELECT * FROM panel_df"
    )
    con.unregister("panel_df")


def run() -> dict:
    config.ensure_dirs()
    state = _read_state()
    n = _advance_cursor(state)
    months = config.SNAPSHOT_MONTHS[:n]
    source = "kaggle" if config.KAGGLE_CSV.exists() else "synthetic"

    con = duckdb.connect(str(config.DUCKDB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    if source == "kaggle":
        _load_real(con, months)
    else:
        _load_synth(con, months)

    rows = con.execute("SELECT COUNT(*) FROM raw.customer_snapshots").fetchone()[0]
    run_info = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "months_loaded": n,
        "latest_month": months[-1],
        "rows": rows,
    }
    con.execute("CREATE TABLE IF NOT EXISTS raw.load_log (info JSON)")
    con.execute("INSERT INTO raw.load_log VALUES (?)", [json.dumps(run_info)])
    con.close()

    state["runs"] = (state.get("runs", []) + [run_info])[-30:]
    _write_state(state)
    print(
        f"ingest ok | source={source} months={n}/{len(config.SNAPSHOT_MONTHS)} "
        f"latest={months[-1]} rows={rows:,}"
    )
    return run_info


if __name__ == "__main__":
    run()
