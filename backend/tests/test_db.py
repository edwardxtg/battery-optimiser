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
    # A day missing one half-hour (a zero-volume period dropped at ingest). It still has all
    # 24 hours, so only a 48-period rule excludes it. The £1 prices would dominate its spread.
    gappy = day_rows(date(2026, 1, 3), [1.0] * 4 + [50.0] * 40 + [200.0] * 4).drop(index=10)
    df = pd.concat([full, partial, gappy])
    con.execute("INSERT INTO prices SELECT * FROM df")
    return con


def test_upsert_is_idempotent(con):
    before = con.execute("SELECT count(*) FROM prices").fetchone()[0]
    df = day_rows(date(2026, 1, 1), [99.0] * 48)
    con.execute("INSERT OR REPLACE INTO prices SELECT * FROM df")
    after, price = con.execute(
        "SELECT count(*), max(price) FROM prices WHERE settlement_date = DATE '2026-01-01'"
    ).fetchone()
    assert before == 97 and after == 48
    assert price == 99.0


def test_tbx_spreads(con):
    tbx = query(con, "tbx")
    # Only the complete day survives: the partial and the one-gap day are excluded.
    assert list(pd.to_datetime(tbx["settlement_date"]).dt.date) == [date(2026, 1, 1)]
    row = tbx.iloc[0]
    assert row["tb1"] == pytest.approx(110 - 10)              # dearest hour − cheapest hour
    assert row["tb2"] == pytest.approx(2 * 110 - 2 * 10)      # two of each
    assert row["tb4"] == pytest.approx((2 * 110 + 2 * 50) - (2 * 10 + 2 * 50))


def test_backtest_and_benchmark(con):
    from app.backtest import benchmark, run_backtest
    from app.optimise import Battery

    # A 2-hour lossless battery on the fixture day: £10 for two hours, £110 for two hours.
    # A token cycle cost keeps the LP from wash-cycling (see MODEL.md) without moving profit.
    b = Battery(capacity_mwh=20.0, power_mw=10.0, efficiency=1.0, cycle_cost_per_mwh=0.01)
    assert run_backtest(con, b) == 1                 # only the complete day is run
    bench = benchmark(con, b)
    assert len(bench) == 1
    row = bench.iloc[0]
    assert row["tb_d"] == pytest.approx(200.0)       # TB2 = 2×110 − 2×10
    # Lossless, the LP captures the whole spread: 20 MWh × £100 / 10 MW.
    assert row["gbp_per_mw"] == pytest.approx(200.0, rel=1e-2)
    assert row["capture_rate"] == pytest.approx(1.0, rel=1e-2)
    assert row["cycles"] == pytest.approx(1.0, abs=0.01)


def test_backtest_clears_stale_runs(con):
    from app.backtest import run_backtest
    from app.optimise import Battery

    b = Battery(capacity_mwh=20.0, power_mw=10.0)
    # A stale result for a day that is no longer complete must not survive a rerun.
    con.execute("INSERT INTO runs VALUES (DATE '2026-01-03', 10.0, 20.0, 0.88, 999.0, 20.0, 1.0, now())")
    run_backtest(con, b)
    days = [d for (d,) in con.execute("SELECT settlement_date FROM runs ORDER BY 1").fetchall()]
    assert days == [date(2026, 1, 1)]
