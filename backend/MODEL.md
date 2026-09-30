# The optimisation model

This is the study sheet for the backend optimiser: the full linear program written out,
with the reasoning behind each part. If you can reproduce this on a whiteboard, you
understand the backend.

## What it does

Given a grid-scale battery (BESS) and the wholesale electricity price in each half-hour of
the day, decide how much to **charge** (buy from the grid) and **discharge** (sell to the
grid) in each period so as to make the most money from **arbitrage** — buy when cheap, sell
when dear — without violating the battery's physical limits.

It's a **linear program**: the objective and all constraints are linear in the decision
variables, so the problem is convex and the solver (HiGHS, via linopy) returns the global
optimum quickly.

## Setup

- The day is split into `T` half-hourly periods (`T = 48`). Each period has length
  `Δt = 0.5` h.
- `pₜ` — the price in period `t`, in £/MWh (known in advance in v1: perfect foresight).
- Battery parameters: capacity `C` (MWh), max power `P` (MW), round-trip efficiency `η`,
  starting charge `S₀` (MWh), state-of-charge floor `R` (MWh), cycle cost `d` (£/MWh cycled).

## Decision variables (for each period t = 0 … T−1)

| Variable | Meaning | Bounds |
|----------|---------|--------|
| `cₜ` | charge power (grid import) | `0 ≤ cₜ ≤ P` |
| `xₜ` | discharge power (grid export) | `0 ≤ xₜ ≤ P` |
| `sₜ` | state of charge at end of period | `R ≤ sₜ ≤ C` |

Energy in a period = power × `Δt`. So charging at `cₜ` MW for half an hour adds `cₜ·Δt`
MWh of grid import.

## Constraints

**1. State-of-charge balance** (links each period to the previous one):

```
sₜ = sₜ₋₁ + η·cₜ·Δt − xₜ·Δt        for t ≥ 1
s₀ = S₀   + η·c₀·Δt − x₀·Δt
```

Charging adds `η·cₜ·Δt` (round-trip losses are charged on the way in); discharging removes
`xₜ·Δt`. This is the only constraint that couples periods together, and it's what makes the
problem *temporal* rather than 48 independent decisions.

**2. Capacity and floor** (built into the bounds on `sₜ`): the battery never exceeds `C`
or drops below the floor `R`. In a fuller model the floor is where ancillary-service
*footroom* lives: energy held back so the battery can deliver if called.

**3. Power limits** (bounds on `cₜ`, `xₜ`): can't charge/discharge faster than `P`.

**4. No net drain:**

```
s_{T−1} ≥ S₀
```

Finish the day with at least as much energy as we started, so profit comes from genuine
arbitrage, not from quietly selling off the battery's stored energy.

## Objective

Maximise profit = export revenue − import cost − cycling cost:

```
maximise   Σₜ [ pₜ·xₜ·Δt  −  pₜ·cₜ·Δt  −  d·(cₜ + xₜ)·Δt ]
```

Price is £/MWh and power × `Δt` is MWh, so every term is already in £. (In code we minimise
the negative of this — linopy minimises by default.)

## Reported metrics

- **Cycles** = energy discharged ÷ rated capacity `C`. One cycle is one full capacity's
  worth of discharge, regardless of how it's split across the day — the convention used in
  battery warranties.
- **£/MW/year** = net profit ÷ `P`, annualised. Normalising by rated power is how BESS
  revenues are quoted and benchmarked, so a 10 MW and a 100 MW asset are comparable.

### The cycle-cost term does two jobs

`d·(cₜ + xₜ)·Δt` charges a small cost for every MWh pushed through the battery. Its obvious
role is **battery wear** — don't cycle for a wafer-thin margin. But it also serves as a
**tie-breaker that keeps the LP well-behaved**, and that's worth understanding:

With `d = 0`, the model is *degenerate*. The objective only depends on the **net** grid flow
`(cₜ − xₜ)` and the SoC balance only on `(η·cₜ − xₜ)`. In periods where the net position has
no marginal value, many `(cₜ, xₜ)` pairs give the identical objective, so the solver may
return one where **both are positive** — e.g. charge 5 MW while discharging 4.4 MW
(= 0.88 × 5). Because `η·cₜ = xₜ`, the state of charge doesn't move: it's a pure
wash-through that cancels out. It's mathematically optimal but physically silly, and the
efficiency loss on that wash happens to have no opportunity cost, so nothing penalises it.

A tiny `d > 0` breaks the tie: any simultaneous charge + discharge now incurs throughput
cost for no benefit, so the optimum never does it — giving a clean, unique dispatch **without
needing a binary "charge OR discharge" variable** (which would make this a slower MILP).

We default `d = £5/MWh`: small enough that genuine arbitrage (GB spreads of tens of £/MWh)
still goes ahead, large enough to regularise the solution. A cycle cost derived from capex
over a warranted cycle life would be higher (tens of £/MWh) and would reject the thinnest
spreads — that's the "cycle charge" a full revenue model uses to represent degradation.

## Why some things are *not* modelled (yet)

- **No binary "charge OR discharge" variable.** We avoid one by using the small cycle cost
  as a tie-breaker (see above), which keeps the problem a fast LP rather than a MILP.
- **No cycling cap.** A daily or annual cycle limit (warranty-driven) would add one
  constraint: `Σₜ xₜ·Δt ≤ N·C`. Today the cycle cost alone discourages over-cycling.
- **No ancillary services.** Frequency-response and reserve products are the other half of
  a GB battery's revenue. They'd add a per-period commitment variable per service, a
  headroom/footroom requirement on `sₜ`, and a revenue term — co-optimised with arbitrage in
  the same LP.
- **No degradation over time.** Capacity `C` is constant. A full model reduces `C` as
  cumulative cycles accrue.

## Honest limitations

- **Perfect foresight.** Real prices aren't known ahead; this gives the *upper bound* on
  achievable arbitrage. Replace `pₜ` with a forecast (and re-optimise each period) for a
  realistic figure — the optimiser code is unchanged, only its price input.
- **Single market, single day.** Wholesale energy only, and each day is solved in isolation.
  A real asset stacks markets and carries state of charge across days.
- **Price taker.** The battery's own dispatch doesn't move the price. Fine for a 10 MW asset;
  not for a fleet.
