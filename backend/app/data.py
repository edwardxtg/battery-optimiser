"""Price data: an Elexon proxy (fallback for browser CORS) and a synthetic generator.

The frontend normally fetches prices directly in the browser. This module gives the
backend a `GET /prices` proxy for when that direct fetch is blocked by CORS, plus a
synthetic series so the optimiser can be exercised with no network access.

Parsing is separated from the HTTP call (`_parse_elexon_mid`) so it can be unit-tested.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

SETTLEMENT_PERIODS_PER_DAY = 48
ELEXON_MID_URL = "https://data.elexon.co.uk/bmrs/api/v1/balancing/pricing/market-index"


def synthetic_prices(days: int = 1, seed: int = 42) -> pd.Series:
    """A GB-flavoured half-hourly price series (£/MWh): peaks am/pm, midday solar dip."""
    rng = np.random.default_rng(seed)
    n = days * SETTLEMENT_PERIODS_PER_DAY
    idx = pd.date_range(
        datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
        periods=n, freq="30min", name="ts",
    )
    hour = idx.hour + idx.minute / 60.0
    shape = (
        60
        + 35 * np.exp(-((hour - 8) ** 2) / 4)
        + 55 * np.exp(-((hour - 18) ** 2) / 5)
        - 25 * np.exp(-((hour - 13) ** 2) / 8)
        - 20 * np.exp(-((hour - 3) ** 2) / 6)
    )
    return pd.Series(np.clip(shape + rng.normal(0, 8, n), -50, None), index=idx, name="price")


def _parse_elexon_mid(payload: dict) -> pd.Series:
    """Parse an Elexon Market Index Data response into a half-hourly £/MWh series."""
    rows = payload.get("data", payload if isinstance(payload, list) else [])
    recs = []
    for r in rows:
        ts = r.get("startTime") or r.get("start")
        price = r.get("price")
        if ts is None or price is None:
            continue
        recs.append((pd.to_datetime(ts, utc=True), float(price)))
    if not recs:
        raise ValueError("No usable rows in Elexon MID response")
    s = pd.Series(dict(recs)).sort_index()
    s.index.name = "ts"
    return s.groupby(level=0).mean()


def fetch_prices(days_back: int = 1, timeout: int = 20) -> pd.Series:
    """Fetch recent half-hourly GB reference prices from Elexon BMRS (raises on failure)."""
    import requests

    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days_back)
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
    return _parse_elexon_mid(resp.json())


def get_prices(days_back: int = 1) -> tuple[pd.Series, str]:
    """Return (prices, source) — live Elexon if reachable, else synthetic."""
    try:
        return fetch_prices(days_back=days_back), "live"
    except Exception:  # noqa: BLE001 - any failure => synthetic fallback
        return synthetic_prices(days=max(days_back, 1)), "synthetic"
