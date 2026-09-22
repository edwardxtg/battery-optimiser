"""Ingest half-hourly GB wholesale prices from Elexon into the DuckDB store.

    python -m app.ingest --days 30

Walks back from now in 7-day windows (the most Elexon serves per request) and upserts each
row keyed by settlement date + period, so re-running only adds what's new. This is the
"data feed" the backtest runs on.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from .data import ELEXON_MID_URL
from .db import DB_PATH, connect

MAX_WINDOW_DAYS = 7


def fetch_window(start: datetime, end: datetime, timeout: int = 30) -> pd.DataFrame:
    """One Elexon request → DataFrame(settlement_date, settlement_period, ts, price)."""
    resp = requests.get(
        ELEXON_MID_URL,
        params={
            "from": start.strftime("%Y-%m-%dT%H:%MZ"),
            "to": end.strftime("%Y-%m-%dT%H:%MZ"),
            "dataProviders": "APXMIDP",
            "format": "json",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    rows = resp.json().get("data", [])
    df = pd.DataFrame(rows, columns=["settlementDate", "settlementPeriod", "startTime", "price"])
    df = df.rename(columns={
        "settlementDate": "settlement_date", "settlementPeriod": "settlement_period",
        "startTime": "ts",
    })
    df["settlement_date"] = pd.to_datetime(df["settlement_date"]).dt.date
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["price"] = df["price"].astype(float)
    # Elexon occasionally returns a period twice; keep one row per key.
    return df.drop_duplicates(["settlement_date", "settlement_period"])


def ingest(days: int, db_path=DB_PATH) -> int:
    """Fetch the last `days` days in 7-day windows and upsert into `prices`. Returns row count."""
    con = connect(db_path)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    total = 0
    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=MAX_WINDOW_DAYS), end)
        df = fetch_window(cursor, window_end)
        if not df.empty:
            df["fetched_at"] = datetime.now(timezone.utc)
            con.execute("INSERT OR REPLACE INTO prices SELECT * FROM df")
            total += len(df)
        cursor = window_end
    con.close()
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=30, help="how many days back to fetch")
    ap.add_argument("--db", default=DB_PATH, help="path to the DuckDB file")
    args = ap.parse_args()
    n = ingest(args.days, args.db)
    con = connect(args.db)
    lo, hi, days = con.execute(
        "SELECT min(settlement_date), max(settlement_date), count(DISTINCT settlement_date) FROM prices"
    ).fetchone()
    print(f"upserted {n} rows; store now covers {lo} to {hi} ({days} days) at {args.db}")


if __name__ == "__main__":
    main()
