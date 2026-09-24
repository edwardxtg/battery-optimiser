"""Tests for turning Elexon rows into stored prices, including the zero-volume rule."""
from datetime import date, datetime, timezone

import pandas as pd

from app.db import connect
from app.ingest import parse_window, replace_window


def elexon_row(period: int, price: float, volume: float) -> dict:
    """One Elexon MID row for 1 Jan 2026 (UTC = UK time in winter)."""
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + pd.Timedelta(minutes=30 * (period - 1))
    return {"settlementDate": "2026-01-01", "settlementPeriod": period,
            "startTime": ts.isoformat(), "price": price, "volume": volume}


def test_parse_window_drops_zero_volume_periods():
    rows = [elexon_row(1, 80.0, 500.0), elexon_row(2, 0.0, 0.0), elexon_row(3, 75.0, 400.0)]
    df = parse_window(rows)
    assert list(df["settlement_period"]) == [1, 3]
    assert list(df.columns) == ["settlement_date", "settlement_period", "ts", "price"]


def test_parse_window_keeps_genuine_zero_price_with_volume():
    # A real trade at exactly £0 is a price, not missing data.
    df = parse_window([elexon_row(1, 0.0, 250.0)])
    assert len(df) == 1 and df["price"].iloc[0] == 0.0


def test_parse_window_keeps_rows_without_volume_field():
    row = elexon_row(1, 70.0, 100.0)
    del row["volume"]
    assert len(parse_window([row])) == 1


def test_replace_window_removes_stale_zero_price_rows():
    con = connect(":memory:")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 2, tzinfo=timezone.utc)
    # An earlier version of the code stored the zero-volume period as a £0 price.
    stale = parse_window([elexon_row(1, 80.0, 500.0), elexon_row(2, 60.0, 300.0)])
    stale.loc[stale["settlement_period"] == 2, "price"] = 0.0
    replace_window(con, stale, start, end)

    fresh = parse_window([elexon_row(1, 80.0, 500.0), elexon_row(2, 0.0, 0.0)])
    replace_window(con, fresh, start, end)
    replace_window(con, fresh, start, end)   # idempotent

    rows = con.execute("SELECT settlement_period, price FROM prices ORDER BY 1").fetchall()
    assert rows == [(1, 80.0)]
    assert con.execute("SELECT min(settlement_date) FROM prices").fetchone()[0] == date(2026, 1, 1)
