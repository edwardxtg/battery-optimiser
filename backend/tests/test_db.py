"""Tests for the DuckDB store and the SQL analytics, on a tiny in-memory fixture."""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from app.db import connect, query


def day_rows(d: date, prices: list[float]) -> pd.DataFrame:
    """One settlement day of half-hourly rows from a list of prices (one per period)."""
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return pd.DataFrame({
        "settlement_date": [d] * len(prices),
        "settlement_period": list(range(1, len(prices) + 1)),
        "ts": [start + timedelta(minutes=30 * i) for i in range(len(prices))],
        "price": prices,
        "fetched_at": [start] * len(prices),
    })


@pytest.fixture
def con():
    """In-memory store with one complete day and one partial day."""
    con = connect(":memory:")
    # Complete day: £10 in hours 0-1, £110 in hours 18-19, £50 elsewhere.
    prices = [50.0] * 48
    prices[0:4] = [10.0] * 4       # hours 0 and 1
    prices[36:40] = [110.0] * 4    # hours 18 and 19
    full = day_rows(date(2026, 1, 1), prices)
    # Partial day (only 2 periods) — must be excluded from spreads.
    partial = day_rows(date(2026, 1, 2), [5.0, 500.0])
    df = pd.concat([full, partial])
    con.execute("INSERT INTO prices SELECT * FROM df")
    return con


def test_upsert_is_idempotent(con):
    before = con.execute("SELECT count(*) FROM prices").fetchone()[0]
    df = day_rows(date(2026, 1, 1), [99.0] * 48)
    con.execute("INSERT OR REPLACE INTO prices SELECT * FROM df")
    after, price = con.execute(
        "SELECT count(*), max(price) FROM prices WHERE settlement_date = DATE '2026-01-01'"
    ).fetchone()
    assert before == 50 and after == 48
    assert price == 99.0


def test_tbx_spreads(con):
    tbx = query(con, "tbx")
    # Only the complete day survives the HAVING count(*) = 24 filter.
    assert list(pd.to_datetime(tbx["settlement_date"]).dt.date) == [date(2026, 1, 1)]
    row = tbx.iloc[0]
    assert row["tb1"] == pytest.approx(110 - 10)              # dearest hour − cheapest hour
    assert row["tb2"] == pytest.approx(2 * 110 - 2 * 10)      # two of each
    assert row["tb4"] == pytest.approx((2 * 110 + 2 * 50) - (2 * 10 + 2 * 50))
