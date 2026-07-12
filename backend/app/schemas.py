"""Pydantic request/response models for the API."""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class BatterySpec(BaseModel):
    capacity_kwh: float = Field(13.5, gt=0, description="Usable capacity")
    power_kw: float = Field(5.0, gt=0, description="Max charge/discharge power")
    efficiency: float = Field(0.90, gt=0, le=1, description="Round-trip efficiency")
    initial_soc_kwh: float = Field(0.0, ge=0, description="Current state of charge")
    reserve_kwh: float = Field(0.0, ge=0, description="Floor the battery won't go below")
    degradation_cost_per_kwh: float = Field(0.005, ge=0, description="£/kWh throughput (wear + LP tie-breaker)")

    @model_validator(mode="after")
    def _reserve_within_soc(self):
        # The reserve is a floor for arbitrage, so it can't be above where the battery starts;
        # otherwise the first period would be infeasible (it can't reach the floor in one step).
        if self.reserve_kwh > self.initial_soc_kwh:
            raise ValueError(
                "reserve_kwh must not exceed initial_soc_kwh "
                "(the battery cannot start below its reserve)"
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
    charge_kw: list[float]
    discharge_kw: list[float]
    soc_kwh: list[float]
    prices: list[float]
    net_profit: float                 # £ over the horizon (one day)
    projected_monthly: float          # net_profit extrapolated to a month


class PricesResponse(BaseModel):
    source: str                       # "live" | "synthetic"
    prices: list[float]
    timestamps: list[str]
