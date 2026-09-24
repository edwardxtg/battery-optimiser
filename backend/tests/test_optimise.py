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
    b = Battery(capacity_mwh=20.0, power_mw=10.0, efficiency=0.88, initial_soc_mwh=2.0)
    r = optimise_dispatch(b, prices)
    assert r.charge_mw.max() <= 10.0 + 1e-6
    assert r.discharge_mw.max() <= 10.0 + 1e-6
    assert r.soc_mwh.max() <= 20.0 + 1e-6


def test_respects_soc_floor(prices):
    b = Battery(capacity_mwh=20.0, power_mw=10.0, initial_soc_mwh=6.0, soc_min_mwh=3.0)
    r = optimise_dispatch(b, prices)
    assert r.soc_mwh.min() >= 3.0 - 1e-6


def test_no_net_drain(prices):
    b = Battery(capacity_mwh=20.0, power_mw=10.0, initial_soc_mwh=5.0)
    r = optimise_dispatch(b, prices)
    assert r.soc_mwh[-1] >= 5.0 - 1e-6


def test_profitable_and_buys_low_sells_high(prices):
    b = Battery(capacity_mwh=20.0, power_mw=10.0, initial_soc_mwh=2.0)
    r = optimise_dispatch(b, prices)
    assert r.net_profit > 0
    # Charging concentrates in the cheap block, discharging in the expensive block.
    assert np.where(r.charge_mw > 0.05)[0].min() < 12
    assert np.where(r.discharge_mw > 0.05)[0].max() >= 36


def test_cycles_and_per_mw_metrics(prices):
    # A 2-hour battery with one clear spread should do about one full cycle.
    b = Battery(capacity_mwh=20.0, power_mw=10.0, initial_soc_mwh=0.0)
    r = optimise_dispatch(b, prices)
    assert 0.9 <= r.cycles <= 1.1
    # One day of profit, annualised per MW: net_profit / 10 MW × 365.
    assert r.gbp_per_mw_year == pytest.approx(r.net_profit / 10.0 * 365, rel=1e-6)


def test_floor_above_soc_raises(prices):
    # Starting below the SoC floor is infeasible; the optimiser should refuse it cleanly.
    b = Battery(capacity_mwh=20.0, power_mw=10.0, initial_soc_mwh=2.0, soc_min_mwh=5.0)
    with pytest.raises(ValueError):
        optimise_dispatch(b, prices)


def test_flat_prices_no_trade():
    # With no price spread, arbitrage can't profit, so it shouldn't cycle.
    b = Battery(capacity_mwh=20.0, power_mw=10.0, initial_soc_mwh=2.0)
    r = optimise_dispatch(b, np.full(48, 100.0))
    assert r.net_profit <= 1e-6
    assert r.charge_mw.sum() < 1e-3
