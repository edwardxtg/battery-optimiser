# battery-optimiser

**Live demo: [battery-optimiser.vercel.app](https://battery-optimiser.vercel.app/)**

Optimise a home battery to **arbitrage wholesale electricity prices** — buy when power is
cheap, sell when it's dear — within the battery's physical limits. Enter your battery,
press Optimise, and see the dispatch schedule and projected earnings against live GB prices.

Grid-service revenue — an aggregator (a virtual power plant) paying the battery to export
during grid-stress events — is one layer that could sit *on top* of this arbitrage base
(see [Possible extensions](#possible-extensions)).

> A deliberately simple, public-data demonstration of the optimise → serve loop behind a
> demand-side flexibility platform.

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
3. The **backend** derives grid-stress events, solves the dispatch LP, and returns the
   schedule + earnings breakdown.
4. The frontend renders price/charging, state-of-charge, and the earnings.

Keeping data-fetching in the browser means page load never waits on a Cloud Run cold
start — the backend is only hit when you optimise.

## The optimisation

A linear program (linopy + HiGHS) over the 48 half-hourly periods of a day. It maximises
**arbitrage profit** — export revenue minus import cost — net of a small per-kWh
**degradation cost**, subject to power, capacity, round-trip efficiency, a homeowner
**reserve floor**, and a **no-net-drain** condition. The full formulation, with the reasoning
behind each constraint, is in **[backend/MODEL.md](backend/MODEL.md)**.

**v1 assumes perfect foresight** (prices are treated as known). That's a deliberate
upper-bound benchmark: the forecaster is a future upstream component, and because the
optimiser takes prices as an input, it won't change when the forecast is added.

Wholesale arbitrage alone is marginal — GB spreads are tens of £/MWh — so a home battery
earns little from it. That's exactly why grid services and VPPs exist, and why they'd be a
natural extension rather than the starting point.

## Run locally

```bash
# Backend (:8080)
make backend-install
make backend-test        # unit tests for the optimiser + API
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

## Possible extensions

Directions this could be taken — illustrative, not commitments:

- **Grid-service revenue (the VPP layer).** Payment for exporting during grid-stress events
  on top of the arbitrage base — the layer where an aggregator / VPP adds value.
- **Price forecasting.** Replace perfect foresight with a forecaster (statistical/ML, or a
  PyPSA fundamentals model); the price input is designed to be swapped.
- **Receding-horizon re-optimisation** each settlement period, as a live dispatcher runs.
- **Fleet endpoint** aggregating many batteries into total dispatchable MW (the VPP view).
- **Household load** so the battery also optimises self-consumption, not just grid trades.

## Licence

MIT.
