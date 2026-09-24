# battery-optimiser

**Live demo: [battery-optimiser.vercel.app](https://battery-optimiser.vercel.app/)**

Optimise a grid-scale battery (BESS) to **arbitrage wholesale electricity prices** — buy
when power is cheap, sell when it's dear — within the battery's physical limits. Enter a
battery, press Optimise, and see the dispatch schedule, cycles and £/MW/year against live
GB prices.

This is the wholesale-energy core of a **BESS revenue model**. A full model stacks
ancillary services, cycling limits and degradation on top of it — see
[How this relates to a full BESS revenue model](#how-this-relates-to-a-full-bess-revenue-model).

> A deliberately simple, public-data demonstration of the model → API → UI loop behind a
> battery revenue product.

## Architecture

A monorepo with two independently deployed apps:

```
battery-optimiser/
├── backend/     FastAPI + linopy optimiser  →  Google Cloud Run (Docker, scales to zero)
└── frontend/    Next.js + Recharts (static) →  Vercel / any static host
```

Data flow:

1. The **frontend** fetches live GB prices directly in the browser on page load
   (Elexon BMRS), falling back to a backend proxy if CORS blocks the direct call.
2. On **Optimise**, it POSTs the battery spec + prices to the backend.
3. The **backend** solves the dispatch LP and returns the schedule, cycles and revenue.
4. The frontend renders price/dispatch, state-of-charge, and the revenue metrics.

Keeping data-fetching in the browser means page load never waits on a Cloud Run cold
start — the backend is only hit when you optimise.

## The optimisation

A linear program (linopy + HiGHS) over the 48 half-hourly periods of a day. It maximises
**arbitrage profit** — export revenue minus import cost — net of a per-MWh **cycle cost**,
subject to power, capacity, round-trip efficiency, a **state-of-charge floor**, and a
**no-net-drain** condition. It reports **cycles** (energy discharged ÷ capacity) and
**£/MW/year**, the units BESS revenues are quoted in. The full formulation, with the
reasoning behind each constraint, is in **[backend/MODEL.md](backend/MODEL.md)**.

**v1 assumes perfect foresight** (prices are treated as known). That's a deliberate
upper-bound benchmark: the forecaster is a future upstream component, and because the
optimiser takes prices as an input, it won't change when the forecast is added.

Wholesale arbitrage is only part of a GB battery's revenue — ancillary services are the
rest — so the £/MW/year shown here is a floor on the stack and a ceiling on the wholesale
layer, not a forecast of what an asset earns.

## Backtest & benchmark

The optimiser is only worth anything if it can be measured, so the backend also carries a
small **price store and backtest**:

```bash
make ingest      # pull 30 days of Elexon prices into backend/prices.duckdb
make backtest    # solve every stored day, benchmark against the available spread
```

- **`app/ingest.py`** walks Elexon's market-index endpoint back in 7-day windows (its
  per-request limit) and upserts half-hourly prices into a single-file
  [DuckDB](https://duckdb.org) store, keyed by settlement date + period. Re-running only
  adds what's new.
- **`app/sql/tbx.sql`** computes **TB1 / TB2 / TB4** per day — the sum of the X dearest
  hours minus the X cheapest, on hourly-average prices. TB2 is the standard proxy for what
  a 2-hour battery can earn per MW from one cycle a day.
- **`app/backtest.py`** runs the LP on each complete day (perfect foresight, state of
  charge reset daily) and writes revenue, throughput and cycles to a `runs` table.
- **`app/sql/benchmark.sql`** joins the two and reports the **capture rate**:
  realised £/MW/day ÷ TB<sub>D</sub> for a D-hour battery.

Result for the default 10 MW / 20 MWh, 88 % RTE battery over 24 Aug – 21 Sep 2026
(29 complete days):

| Metric | Value |
|---|---|
| Mean TB2 available | £232 /MW/day |
| Mean realised (perfect foresight) | £192 /MW/day ≈ **£70k /MW/yr** |
| **Capture rate vs TB2** | **76 %** |
| Cycles per day | 1.47 |

Two things the day-by-day table makes visible:

- **Capture rate falls on flat, expensive days.** On 28 Aug prices sat between £97 and
  £169; buying at ~£132 and selling at ~£166 nets only ~£16/MWh after the 12 % round-trip
  loss, because efficiency costs a share of the *price level*, not of the spread. TB2
  ignores losses, so capture drops to 23 %.
- **Capture rate exceeds 100 % on double-peak days.** TB2 assumes one cycle; the optimiser
  is free to cycle more, and on 12 Sep it did 1.44 cycles for 135 % of TB2. A daily cycle
  cap would make the comparison exact and is the obvious next constraint.

The SQL is deliberately plain — CTEs, window functions and a join — and lives in `.sql`
files rather than being built in Python, so each query can be read and run on its own.

## Run locally

```bash
# Backend (:8080)
make backend-install
make backend-test        # unit tests for the optimiser, API and SQL store
make backend-dev

# Frontend (:3000) — in another terminal
make frontend-install
make frontend-dev        # set NEXT_PUBLIC_API_URL=http://localhost:8080
```

## Deploy

**Backend → Cloud Run** (Python + Docker on GCP; scales to zero, so an idle demo costs ~£0):

```bash
cd backend
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
ALLOWED_ORIGINS="https://your-frontend-url" bash deploy/cloudrun.sh
```

**Frontend → Vercel** (or any static host): set the project's **Root Directory** to
`frontend/`, add env var `NEXT_PUBLIC_API_URL` = your Cloud Run URL. `output: "export"`
produces static files, so it can equally be hosted on your own website or Cloudflare
Pages / GitHub Pages for free.

## Security & access

The backend is a public, stateless calculator over public price data — there's nothing
sensitive behind it, so the goal is limiting **abuse and cost**, not true access control
(a static public frontend can't hold a secret, and real auth would break the open demo).
In place:

- **CORS restricted to your frontend.** Set `ALLOWED_ORIGINS` to your deployed frontend URL
  at deploy time (the `cloudrun.sh` script passes it through):
  ```bash
  ALLOWED_ORIGINS="https://your-site.example" bash deploy/cloudrun.sh
  ```
  This stops other *websites* using your API in a browser. It does **not** stop direct
  `curl`/script calls — CORS is a browser mechanism only.
- **Per-IP rate limit** of 1 request/second on `/optimise` and `/prices` (keyed off
  `X-Forwarded-For` so callers aren't lumped together behind Cloud Run). Excess returns HTTP 429.
- **Capped request payload** — the `prices` array is limited to 336 periods, so no one can
  POST a giant body.
- **Cost cap** — `cloudrun.sh` sets `--max-instances 3`, bounding compute (and spend) even
  under load. Add a small **GCP budget alert** as a backstop.

A determined caller can still hit the endpoint directly; that's expected and harmless here.

## How this relates to a full BESS revenue model

What's here is the wholesale-energy layer, kept small on purpose so every line is
explainable. The layers a production revenue model adds, and how each would slot in:

| Layer | Status here | How it would slot in |
|---|---|---|
| Wholesale arbitrage | ✅ | The LP in `optimise.py` |
| Cycle cost (degradation as £/MWh) | ✅ | Objective term |
| SoC floor / footroom | ✅ | Bound on `soc` |
| Cycles and £/MW/year reporting | ✅ | `DispatchResult` |
| Backtest and capture rate vs TBX spreads | ✅ | `backtest.py` + `sql/` |
| Daily cycling cap | ✗ | One constraint: `Σ discharge·Δt ≤ N·C` |
| Ancillary services (frequency response, reserve) | ✗ | Per-service commitment variables, headroom/footroom on `soc`, revenue term — co-optimised in the same LP |
| Imperfect foresight | ✗ | Re-solve each hour with true near-term prices and a smoothed view beyond; compare with perfect foresight to get a capture rate |
| Degradation over time | ✗ | Reduce capacity as cumulative cycles accrue |
| Annual cycling budget | ✗ | Post-process: drop the least profitable sub-cycles until under budget |
| Multi-day state of charge | ✗ | Carry `soc[-1]` into the next day's `initial_soc` |

## Possible extensions

- **Price forecasting.** Replace perfect foresight with a forecaster (statistical/ML, or a
  fundamentals model); the price input is designed to be swapped.
- **Receding-horizon re-optimisation** each settlement period, as a live dispatcher runs.
- **Other markets.** The LP is market-agnostic; only the price feed is GB-specific.

## Licence

MIT.
