// Data fetching + backend calls.
//
// Strategy (agreed design): fetch prices directly in the browser for snappiness, and
// fall back to the backend proxy only if the direct call is blocked by CORS. The
// optimise call always goes to the Cloud Run backend.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8080";

const ELEXON_URL =
  "https://data.elexon.co.uk/bmrs/api/v1/balancing/pricing/market-index";

export interface BatterySpec {
  capacity_kwh: number;
  power_kw: number;
  efficiency: number;
  initial_soc_kwh: number;
  reserve_kwh: number;
  degradation_cost_per_kwh: number;
}

export interface PriceSeries {
  prices: number[];
  timestamps: string[];
  source: "direct" | "proxy" | "synthetic";
}

export interface OptimiseResult {
  source: string;
  charge_kw: number[];
  discharge_kw: number[];
  soc_kwh: number[];
  prices: number[];
  net_profit: number;
  projected_monthly: number;
}

function isoHour(d: Date): string {
  return d.toISOString().slice(0, 14) + "00Z";
}

// Try Elexon directly from the browser. Throws if blocked (CORS) or empty.
async function fetchElexonDirect(): Promise<PriceSeries> {
  const to = new Date();
  const from = new Date(to.getTime() - 24 * 3600 * 1000);
  const url =
    `${ELEXON_URL}?from=${isoHour(from)}&to=${isoHour(to)}` +
    `&dataProviders=APXMIDP&format=json`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Elexon HTTP ${res.status}`);
  const json = await res.json();
  const rows: any[] = json.data ?? [];
  const parsed = rows
    .map((r) => ({ t: r.startTime ?? r.start, p: r.price }))
    .filter((r) => r.t != null && r.p != null)
    .sort((a, b) => (a.t < b.t ? -1 : 1));
  if (parsed.length === 0) throw new Error("Elexon returned no rows");
  return {
    prices: parsed.map((r) => Number(r.p)),
    timestamps: parsed.map((r) => r.t),
    source: "direct",
  };
}

// Backend proxy fallback (server-to-server, no CORS).
async function fetchViaProxy(): Promise<PriceSeries> {
  const res = await fetch(`${API_URL}/prices?days_back=1`);
  if (!res.ok) throw new Error(`Proxy HTTP ${res.status}`);
  const json = await res.json();
  return {
    prices: json.prices,
    timestamps: json.timestamps,
    source: json.source === "live" ? "proxy" : "synthetic",
  };
}

export async function fetchPrices(): Promise<PriceSeries> {
  try {
    return await fetchElexonDirect();
  } catch {
    return await fetchViaProxy();
  }
}

export async function optimise(
  battery: BatterySpec,
  prices: number[]
): Promise<OptimiseResult> {
  const res = await fetch(`${API_URL}/optimise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ battery, prices }),
  });
  if (!res.ok) throw new Error(`Optimise HTTP ${res.status}`);
  return res.json();
}
