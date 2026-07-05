"""Home-battery wholesale-price arbitrage as a linear program (linopy + HiGHS).

Given a battery and a known half-hourly price series for the day, choose when to import
(charge) and export (discharge) so as to maximise arbitrage profit — buy cheap, sell dear
— net of a small battery-degradation cost, subject to the battery's physical limits.

This is the simplest coherent model: one revenue idea, a handful of constraints, and no
third party. Grid-service revenue (e.g. an aggregator paying to export during grid
events) is a layer that could sit *on top* of this — see MODEL.md and "Possible extensions".

v1 assumes perfect foresight: the price series is treated as known. Because the optimiser
takes prices as an input, swapping in a forecast later changes nothing here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import linopy

DT_HOURS = 0.5          # half-hourly settlement periods
DAYS_PER_MONTH = 30.4   # for extrapolating a daily result to a monthly figure


@dataclass
class Battery:
    capacity_kwh: float
    power_kw: float
    efficiency: float = 0.90            # round-trip, applied on charging
    initial_soc_kwh: float = 0.0
    reserve_kwh: float = 0.0            # floor the battery won't go below
    # £/kWh of throughput. Small by design: models a little battery wear AND acts as a
    # tie-breaker that keeps the LP from returning degenerate charge+discharge in one period.
    degradation_cost_per_kwh: float = 0.005


@dataclass
class DispatchResult:
    charge_kw: np.ndarray    # grid import per period (kW)
    discharge_kw: np.ndarray  # grid export per period (kW)
    soc_kwh: np.ndarray      # state of charge at end of each period (kWh)
    prices: np.ndarray       # £/MWh used
    net_profit: float        # £ over the horizon

    @property
    def projected_monthly(self) -> float:
        days = len(self.prices) * DT_HOURS / 24.0
        return self.net_profit / max(days, 1e-9) * DAYS_PER_MONTH

    def summary(self) -> str:
        return (
            f"net £{self.net_profit:.2f} over {len(self.prices)} periods "
            f"(~£{self.projected_monthly:.2f}/month)"
        )


def optimise_dispatch(battery: Battery, prices: np.ndarray) -> DispatchResult:
    """Solve the arbitrage LP for a known half-hourly price series (£/MWh)."""
    prices = np.asarray(prices, dtype=float)
    n = len(prices)
    if n == 0:
        raise ValueError("prices must be non-empty")

    dt, eta = DT_HOURS, battery.efficiency
    periods = range(n)

    m = linopy.Model()
    charge = m.add_variables(lower=0, upper=battery.power_kw, coords=[periods], name="charge")
    discharge = m.add_variables(lower=0, upper=battery.power_kw, coords=[periods], name="discharge")
    soc = m.add_variables(lower=battery.reserve_kwh, upper=battery.capacity_kwh,
                          coords=[periods], name="soc")

    # State-of-charge balance: energy in (after round-trip losses) minus energy out.
    for t in periods:
        prev = soc.loc[t - 1] if t > 0 else battery.initial_soc_kwh
        m.add_constraints(
            soc.loc[t] - prev - eta * charge.loc[t] * dt + discharge.loc[t] * dt == 0,
            name=f"soc_balance_{t}",
        )
    # Don't end the day with less energy than we started (no selling off the reserve).
    m.add_constraints(soc.loc[n - 1] >= battery.initial_soc_kwh, name="no_net_drain")

    # Objective: minimise (import cost + wear − export revenue) = maximise profit.
    # price is £/MWh, energy is kWh, so divide by 1000 to get £.
    import_cost = (prices * dt / 1000.0 * charge).sum()
    export_revenue = (prices * dt / 1000.0 * discharge).sum()
    degradation = (battery.degradation_cost_per_kwh * dt * (charge + discharge)).sum()
    m.add_objective(import_cost + degradation - export_revenue)

    m.solve(output_flag=False)

    c = charge.solution.to_numpy()
    d = discharge.solution.to_numpy()
    s = soc.solution.to_numpy()
    net = float(
        np.sum(prices * (d - c) * dt) / 1000.0
        - battery.degradation_cost_per_kwh * dt * np.sum(c + d)
    )
    return DispatchResult(charge_kw=c, discharge_kw=d, soc_kwh=s, prices=prices, net_profit=net)
