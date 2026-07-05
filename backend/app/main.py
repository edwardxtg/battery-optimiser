"""FastAPI service: /optimise (the core) and /prices (Elexon proxy fallback).

Public demo, so it carries light abuse protection: per-IP rate limiting, a capped
request payload (see schemas), CORS restricted to the configured frontend origin, and
(at deploy) a Cloud Run max-instances cap. None of this is true access control — the
endpoint is an open, stateless calculator over public data — it just limits abuse and cost.
"""
from __future__ import annotations

import os

import numpy as np
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .data import get_prices
from .optimise import Battery, optimise_dispatch
from .schemas import OptimiseRequest, OptimiseResponse, PricesResponse

RATE_LIMIT = "1/second"


def client_ip(request: Request) -> str:
    """Real client IP. Behind Cloud Run the peer is the load balancer, so prefer the
    first hop of X-Forwarded-For; otherwise every caller would share one rate-limit bucket."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)
app = FastAPI(title="battery-optimiser", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Restrict CORS to the frontend origin in production. Set ALLOWED_ORIGINS to a
# comma-separated list of URLs at deploy; defaults to "*" for local dev.
_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/prices", response_model=PricesResponse)
@limiter.limit(RATE_LIMIT)
def prices(request: Request, days_back: int = 1) -> PricesResponse:
    """Proxy recent GB prices from Elexon (fallback for when the browser hits CORS)."""
    series, source = get_prices(days_back=days_back)
    return PricesResponse(
        source=source,
        prices=[float(x) for x in series.to_numpy()],
        timestamps=[t.isoformat() for t in series.index],
    )


@app.post("/optimise", response_model=OptimiseResponse)
@limiter.limit(RATE_LIMIT)
def optimise(request: Request, req: OptimiseRequest) -> OptimiseResponse:
    """Optimise battery dispatch to maximise wholesale-price arbitrage."""
    if req.prices is not None:
        prices_arr = np.array(req.prices, dtype=float)
        source = "client"
    else:
        series, source = get_prices(days_back=1)
        prices_arr = series.to_numpy()

    b = req.battery
    battery = Battery(
        capacity_kwh=b.capacity_kwh,
        power_kw=b.power_kw,
        efficiency=b.efficiency,
        initial_soc_kwh=min(b.initial_soc_kwh, b.capacity_kwh),
        reserve_kwh=min(b.reserve_kwh, b.capacity_kwh),
        degradation_cost_per_kwh=b.degradation_cost_per_kwh,
    )
    r = optimise_dispatch(battery, prices_arr)

    return OptimiseResponse(
        source=source,
        charge_kw=r.charge_kw.tolist(),
        discharge_kw=r.discharge_kw.tolist(),
        soc_kwh=r.soc_kwh.tolist(),
        prices=r.prices.tolist(),
        net_profit=r.net_profit,
        projected_monthly=r.projected_monthly,
    )
