"""Tests on the arbitrage optimiser's physical constraints and profitability."""
import numpy as np
import pytest

from app.optimise import Battery, optimise_dispatch


@pytest.fixture
def prices():
    # Cheap overnight, expensive evening — a clear arbitrage signal.
    p = np.full(48, 100.0)
    p[:12] = 20.0     # cheap night
    p[36:44] = 250.0  # expensive evening
    return p


def test_respects_power_and_capacity(prices):
    b = Battery(capacity_kwh=13.5, power_kw=5.0, efficiency=0.9, initial_soc_kwh=2.0)
    r = optimise_dispatch(b, prices)
    assert r.charge_kw.max() <= 5.0 + 1e-6
    assert r.discharge_kw.max() <= 5.0 + 1e-6
    assert r.soc_kwh.max() <= 13.5 + 1e-6


def test_respects_reserve_floor(prices):
    b = Battery(capacity_kwh=13.5, power_kw=5.0, initial_soc_kwh=6.0, reserve_kwh=3.0)
    r = optimise_dispatch(b, prices)
    assert r.soc_kwh.min() >= 3.0 - 1e-6


def test_no_net_drain(prices):
    b = Battery(capacity_kwh=13.5, power_kw=5.0, initial_soc_kwh=5.0)
    r = optimise_dispatch(b, prices)
    assert r.soc_kwh[-1] >= 5.0 - 1e-6


def test_profitable_and_buys_low_sells_high(prices):
    b = Battery(capacity_kwh=13.5, power_kw=5.0, initial_soc_kwh=2.0)
    r = optimise_dispatch(b, prices)
    assert r.net_profit > 0
    # Charging concentrates in the cheap block, discharging in the expensive block.
    assert np.where(r.charge_kw > 0.05)[0].min() < 12
    assert np.where(r.discharge_kw > 0.05)[0].max() >= 36


def test_flat_prices_no_trade():
    # With no price spread, arbitrage can't profit, so it shouldn't cycle.
    b = Battery(capacity_kwh=13.5, power_kw=5.0, initial_soc_kwh=2.0)
    r = optimise_dispatch(b, np.full(48, 100.0))
    assert r.net_profit <= 1e-6
    assert r.charge_kw.sum() < 1e-3
