# The optimisation model

This is the study sheet for the backend optimiser: the full linear program written out,
with the reasoning behind each part. If you can reproduce this on a whiteboard, you
understand the backend.

## What it does

Given a home battery and the electricity price in each half-hour of the day, decide how
much to **charge** (buy from the grid) and **discharge** (sell to the grid) in each period
so as to make the most money from **arbitrage** — buy when cheap, sell when dear — without
violating the battery's physical limits.

It's a **linear program**: the objective and all constraints are linear in the decision
variables, so the problem is convex and the solver (HiGHS, via linopy) returns the global
optimum quickly.

## Setup

- The day is split into `T` half-hourly periods (`T = 48`). Each period has length
  `Δt = 0.5` h.
- `pₜ` — the price in period `t`, in £/MWh (known in advance in v1: perfect foresight).
- Battery parameters: capacity `C` (kWh), max power `P` (kW), round-trip efficiency `η`,
  starting charge `S₀` (kWh), reserve floor `R` (kWh), degradation cost `d` (£/kWh cycled).

## Decision variables (for each period t = 0 … T−1)

| Variable | Meaning | Bounds |
|----------|---------|--------|
| `cₜ` | charge power (grid import) | `0 ≤ cₜ ≤ P` |
| `xₜ` | discharge power (grid export) | `0 ≤ xₜ ≤ P` |
| `sₜ` | state of charge at end of period | `R ≤ sₜ ≤ C` |

Energy in a period = power × `Δt`. So charging at `cₜ` kW for half an hour adds `cₜ·Δt`
kWh of grid import.

## Constraints

**1. State-of-charge balance** (links each period to the previous one):

```
sₜ = sₜ₋₁ + η·cₜ·Δt − xₜ·Δt        for t ≥ 1
s₀ = S₀   + η·c₀·Δt − x₀·Δt
```

Charging adds `η·cₜ·Δt` (round-trip losses are charged on the way in); discharging removes
`xₜ·Δt`. This is the only constraint that couples periods together, and it's what makes the
problem *temporal* rather than 48 independent decisions.

**2. Capacity and reserve** (built into the bounds on `sₜ`): the battery never exceeds `C`
or drops below the homeowner's reserve `R`.

**3. Power limits** (bounds on `cₜ`, `xₜ`): can't charge/discharge faster than `P`.

**4. No net drain:**

```
s_{T−1} ≥ S₀
```

Finish the day with at least as much energy as we started, so profit comes from genuine
arbitrage, not from quietly selling off the battery's stored energy.

## Objective

Maximise profit = export revenue − import cost − degradation:

```
maximise   Σₜ [ pₜ·xₜ·Δt/1000  −  pₜ·cₜ·Δt/1000  −  d·(cₜ + xₜ)·Δt ]
```

The `/1000` converts £/MWh × kWh to £. (In code we minimise the negative of this — linopy
minimises by default.)

### The degradation term does two jobs

`d·(cₜ + xₜ)·Δt` charges a small cost for every kWh pushed through the battery. Its obvious
role is **battery wear** — don't cycle for a wafer-thin margin. But it also serves as a
**tie-breaker that keeps the LP well-behaved**, and that's worth understanding:

With `d = 0`, the model is *degenerate*. The objective only depends on the **net** grid flow
`(cₜ − xₜ)` and the SoC balance only on `(η·cₜ − xₜ)`. In periods where the net position has
no marginal value, many `(cₜ, xₜ)` pairs give the identical objective, so the solver may
return one where **both are positive** — e.g. charge 3.7 kW while discharging 3.33 kW
(= 0.9 × 3.7). Because `η·cₜ = xₜ`, the state of charge doesn't move: it's a pure
wash-through that cancels out. It's mathematically optimal but physically silly, and the
efficiency loss on that wash happens to have no opportunity cost, so nothing penalises it.

A tiny `d > 0` breaks the tie: any simultaneous charge + discharge now incurs throughput
cost for no benefit, so the optimum never does it — giving a clean, unique dispatch **without
needing a binary "charge OR discharge" variable** (which would make this a slower MILP).

We default `d = 0.005 £/kWh`: small enough that genuine arbitrage (wholesale spreads of tens
of £/MWh) still goes ahead, large enough to regularise the solution. Realistic wear costs are
higher (~2–5p/kWh), but at those levels raw wholesale arbitrage rarely pays at all — which is
itself the honest reason grid services exist.

## Why some things are *not* modelled (yet)

- **No binary "charge OR discharge" variable.** We avoid one by using the small degradation
  cost as a tie-breaker (see above), which keeps the problem a fast LP rather than a MILP.
- **No home-load profile.** v1 trades purely against the grid; adding household consumption
  would need a demand time-series.
- **No grid-service / event revenue.** That's the layer an aggregator / virtual power plant
  adds on top: paying the battery to export during grid-stress events. It slots in as an extra
  revenue term over selected periods, on top of this arbitrage base — a natural extension.

## Honest limitations

- **Perfect foresight.** Real prices aren't known ahead; this gives the *upper bound* on
  achievable arbitrage. Replace `pₜ` with a forecast (and re-optimise each period) for a
  realistic figure — the optimiser code is unchanged, only its price input.
- **Arbitrage is marginal.** GB wholesale spreads are tens of £/MWh, so a home battery
  earns little from arbitrage alone. That's the real-world reason grid services and VPPs
  exist — and the reason this base model is only step one.
