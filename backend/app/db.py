"""DuckDB price store: one file, two tables, plain SQL.

`prices` holds half-hourly GB wholesale prices keyed by settlement date + period (the GB
clock day, which is what "a day" means for spreads and cycles). `runs` holds one row per
(day, battery) from the backtest. Analytics live in app/sql/*.sql and are run with `query`.

DuckDB is a single-file analytical database — no server, nothing to configure — so the
store is rebuilt from scratch with `python -m app.ingest` and is not committed.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "prices.duckdb"
SQL_DIR = Path(__file__).resolve().parent / "sql"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    settlement_date   DATE,
    settlement_period INTEGER,       -- 1..48 (46/50 on clock-change days)
    ts                TIMESTAMPTZ,   -- period start, UTC
    price             DOUBLE,        -- £/MWh
    fetched_at        TIMESTAMPTZ,
    PRIMARY KEY (settlement_date, settlement_period)
);

CREATE TABLE IF NOT EXISTS runs (
    settlement_date       DATE,
    power_mw              DOUBLE,
    capacity_mwh          DOUBLE,
    efficiency            DOUBLE,
    net_profit            DOUBLE,    -- £ for the day
    energy_discharged_mwh DOUBLE,
    cycles                DOUBLE,
    run_at                TIMESTAMPTZ,
    PRIMARY KEY (settlement_date, power_mw, capacity_mwh, efficiency)
);
"""


def connect(path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Open (or create) the store and make sure both tables exist. ':memory:' works too."""
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    return con


def query(con: duckdb.DuckDBPyConnection, name: str, **params) -> pd.DataFrame:
    """Run app/sql/<name>.sql with named parameters ($name in the SQL) and return a DataFrame."""
    sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
    return con.execute(sql, params).df()
