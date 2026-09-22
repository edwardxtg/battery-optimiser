"""Pydantic request/response models for the API."""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class BatterySpec(BaseModel):
    capacity_mwh: float = Field(20.0, gt=0, description="Usable energy capacity")
    power_mw: float = Field(10.0, gt=0, description="Max charge/discharge power")
    efficiency: float = Field(0.88, gt=0, le=1, description="Round-trip efficiency")
    initial_soc_mwh: float = Field(0.0, ge=0, description="Current state of charge")
    soc_min_mwh: float = Field(0.0, ge=0, description="State-of-charge floor")
    cycle_cost_per_mwh: float = Field(5.0, ge=0, description="£/MWh throughput (wear + LP tie-breaker)")

    @model_validator(mode="after")
    def _floor_within_soc(self):
        # The floor can't be above where the battery starts; otherwise the first period
        # would be infeasible (it can't reach the floor in one step).
        if self.soc_min_mwh > self.initial_soc_mwh:
            raise ValueError(
                "soc_min_mwh must not exceed initial_soc_mwh "
                "(the battery cannot start below its floor)"
            )
        return self


class OptimiseRequest(BaseModel):
    battery: BatterySpec = BatterySpec()
    # Capped at 336 periods (one week of half-hourly data) to reject oversized payloads.
    prices: list[float] | None = Field(
        None, max_length=336,
        description="Half-hourly £/MWh series (max 336). If omitted, the backend sources it.",
    )


class OptimiseResponse(BaseModel):
    source: str                       # "client" | "live" | "synthetic"
    charge_mw: list[float]
    discharge_mw: list[float]
    soc_mwh: list[float]
    prices: list[float]
    net_profit: float                 # £ over the horizon (one day)
    cycles: float                     # full-equivalent cycles over the horizon
    gbp_per_mw_year: float            # net profit annualised per MW of rated power


class PricesResponse(BaseModel):
    source: str                       # "live" | "synthetic"
    prices: list[float]
    timestamps: list[str]
