"""Grid-scale battery (BESS) wholesale-price arbitrage as a linear program (linopy + HiGHS).

Given a battery and a known half-hourly price series for the day, choose when to import
(charge) and export (discharge) so as to maximise arbitrage revenue — buy cheap, sell dear
— net of a per-MWh cycling cost, subject to the battery's physical limits.

This is the simplest coherent BESS revenue model: one revenue stream (wholesale energy),
a handful of constraints, and no market interactions. A full revenue model stacks ancillary
services, cycling caps and degradation on top — see MODEL.md and the README.

v1 assumes perfect foresight: the price series is treated as known. Because the optimiser
takes prices as an input, swapping in a forecast later changes nothing here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import linopy

SETTLEMENT_PERIOD_HOURS = 0.5  # each GB settlement period is half an hour
HOURS_PER_YEAR = 8760.0


@dataclass
class Battery:
    capacity_mwh: float
    power_mw: float
    efficiency: float = 0.88            # round-trip, applied on charging
    initial_soc_mwh: float = 0.0
    soc_min_mwh: float = 0.0            # state-of-charge floor the battery won't go below
    # £/MWh of throughput. Small by design: models a little battery wear AND acts as a
    # tie-breaker that keeps the LP from returning degenerate charge+discharge in one period.
    cycle_cost_per_mwh: float = 5.0


@dataclass
class DispatchResult:
    charge_mw: np.ndarray     # grid import per period (MW)
    discharge_mw: np.ndarray  # grid export per period (MW)
    soc_mwh: np.ndarray       # state of charge at end of each period (MWh)
    prices: np.ndarray        # £/MWh used
    net_profit: float         # £ over the horizon
    power_mw: float           # rated power, for the per-MW figure below
    capacity_mwh: float       # rated capacity, for the cycle count below

    @property
    def hours(self) -> float:
        return len(self.prices) * SETTLEMENT_PERIOD_HOURS

    @property
    def energy_discharged_mwh(self) -> float:
        return float(self.discharge_mw.sum() * SETTLEMENT_PERIOD_HOURS)

    @property
    def cycles(self) -> float:
        """Full-equivalent cycles: energy discharged as a multiple of rated capacity."""
        return self.energy_discharged_mwh / self.capacity_mwh

    @property
    def gbp_per_mw_year(self) -> float:
        """Net profit annualised and normalised by rated power — the standard BESS metric."""
        return self.net_profit / self.power_mw / max(self.hours, 1e-9) * HOURS_PER_YEAR

    def summary(self) -> str:
        return (
            f"net £{self.net_profit:,.0f} over {len(self.prices)} periods "
            f"({self.cycles:.2f} cycles, ~£{self.gbp_per_mw_year:,.0f}/MW/yr)"
        )


def optimise_dispatch(battery: Battery, prices: np.ndarray) -> DispatchResult:
    """Solve the arbitrage LP for a known half-hourly price series (£/MWh)."""
    prices = np.asarray(prices, dtype=float)
    n = len(prices)
    if n == 0:
        raise ValueError("prices must be non-empty")
    if battery.soc_min_mwh > battery.initial_soc_mwh:
        # Otherwise the first period is infeasible: it can't reach the floor in one step.
        raise ValueError("soc_min_mwh cannot exceed initial_soc_mwh")

    dt = SETTLEMENT_PERIOD_HOURS
    periods = range(n)

    m = linopy.Model()
    charge = m.add_variables(lower=0, upper=battery.power_mw, coords=[periods], name="charge")
    discharge = m.add_variables(lower=0, upper=battery.power_mw, coords=[periods], name="discharge")
    soc = m.add_variables(lower=battery.soc_min_mwh, upper=battery.capacity_mwh,
                          coords=[periods], name="soc")

    # State-of-charge balance: energy in (after round-trip losses) minus energy out.
    for t in periods:
        soc_prev = soc.loc[t - 1] if t > 0 else battery.initial_soc_mwh
        m.add_constraints(
            soc.loc[t] - soc_prev - battery.efficiency * charge.loc[t] * dt + discharge.loc[t] * dt == 0,
            name=f"soc_balance_{t}",
        )
    # Don't end the day with less energy than we started (no selling off stored energy).
    m.add_constraints(soc.loc[n - 1] >= battery.initial_soc_mwh, name="no_net_drain")

    # Objective: minimise (import cost + cycling cost − export revenue) = maximise profit.
    # price is £/MWh and power × dt is MWh, so the products are already in £.
    import_cost = (prices * dt * charge).sum()
    export_revenue = (prices * dt * discharge).sum()
    cycling = (battery.cycle_cost_per_mwh * dt * (charge + discharge)).sum()
    m.add_objective(import_cost + cycling - export_revenue)

    m.solve(output_flag=False)

    c = charge.solution.to_numpy()
    d = discharge.solution.to_numpy()
    s = soc.solution.to_numpy()
    net = float(
        np.sum(prices * (d - c) * dt)
        - battery.cycle_cost_per_mwh * dt * np.sum(c + d)
    )
    return DispatchResult(
        charge_mw=c, discharge_mw=d, soc_mwh=s, prices=prices, net_profit=net,
        power_mw=battery.power_mw, capacity_mwh=battery.capacity_mwh,
    )
