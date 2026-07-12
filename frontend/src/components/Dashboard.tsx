"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ComposedChart, AreaChart, Area, Bar, Line, XAxis, YAxis, Tooltip,
  Legend, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  BatterySpec, OptimiseResult, PriceSeries, fetchPrices, optimise,
} from "@/lib/api";
import { BATTERY_PRESETS } from "@/lib/batteries";

const DEFAULT_BATTERY: BatterySpec = {
  capacity_kwh: 13.5,
  power_kw: 5.0,
  efficiency: 0.9,
  initial_soc_kwh: 2.0,
  reserve_kwh: 1.0,
  degradation_cost_per_kwh: 0.005,
};

function money(x: number): string {
  return "£" + x.toFixed(2);
}
// Fallback label when no timestamp is available (index-based).
function label(i: number): string {
  const h = Math.floor(i / 2);
  const m = i % 2 ? "30" : "00";
  return `${String(h % 24).padStart(2, "0")}:${m}`;
}
// Real clock time (UTC) from an ISO timestamp, e.g. "14:30".
function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", {
    hour: "2-digit", minute: "2-digit", timeZone: "UTC",
  });
}
// Full date + time (UTC), e.g. "Mon 02 Jun, 14:30".
function fmtFull(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    weekday: "short", day: "2-digit", month: "short",
    hour: "2-digit", minute: "2-digit", timeZone: "UTC",
  });
}

const SOURCE_INFO: Record<string, { text: string; color: string }> = {
  direct: { text: "Live · Elexon BMRS (fetched in-browser)", color: "#2e7d32" },
  proxy: { text: "Live · Elexon BMRS (via backend proxy)", color: "#2e7d32" },
  synthetic: { text: "Synthetic demo data — Elexon unavailable", color: "#b7791f" },
};

export default function Dashboard() {
  const [battery, setBattery] = useState<BatterySpec>(DEFAULT_BATTERY);
  const [preset, setPreset] = useState("Custom");
  const [series, setSeries] = useState<PriceSeries | null>(null);
  const [result, setResult] = useState<OptimiseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch live prices once on load (direct from the browser, proxy fallback).
  useEffect(() => {
    fetchPrices()
      .then(setSeries)
      .catch((e) => setError("Could not load prices: " + e.message));
  }, []);

  const runOptimise = useCallback(async () => {
    if (!series) return;
    if (battery.reserve_kwh > battery.initial_soc_kwh) {
      setError("Reserve can't be higher than the current state of charge (kWh).");
      setResult(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult(await optimise(battery, series.prices));
    } catch (e: any) {
      setError("Optimise failed: " + e.message);
    } finally {
      setLoading(false);
    }
  }, [battery, series]);

  const set = (k: keyof BatterySpec) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setBattery((b) => ({ ...b, [k]: Number(e.target.value) }));

  const applyPreset = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const p = BATTERY_PRESETS.find((x) => x.name === e.target.value)!;
    setPreset(p.name);
    setBattery((b) => ({ ...b, capacity_kwh: p.capacity_kwh, power_kw: p.power_kw }));
  };

  const chartData = useMemo(() => {
    if (!result) return [];
    const ts = series?.timestamps ?? [];
    return result.prices.map((p, i) => {
      const iso = ts[i];
      return {
        t: iso ? fmtTime(iso) : label(i),
        full: iso ? fmtFull(iso) + " UTC" : label(i),
        price: Math.round(p * 10) / 10,
        charge: Math.round(result.charge_kw[i] * 100) / 100,
        discharge: Math.round(result.discharge_kw[i] * 100) / 100,
        soc: Math.round(result.soc_kwh[i] * 100) / 100,
      };
    });
  }, [result, series]);

  const dateRange =
    series && series.timestamps.length
      ? `${fmtFull(series.timestamps[0])} → ${fmtFull(
          series.timestamps[series.timestamps.length - 1]
        )} UTC`
      : "";
  const tooltipLabel = (_: any, payload: any) =>
    payload?.[0]?.payload?.full ?? _;

  return (
    <>
      <div className="header">
        <h1>Battery Optimiser</h1>
        <p>
          Enter your home battery and optimise a day of dispatch to arbitrage wholesale
          electricity prices — buy low, sell high — within the battery&rsquo;s physical
          limits. v1 uses live GB prices with perfect foresight. Grid-service revenue via an
          aggregator (a virtual power plant) is one way this base could be extended.
        </p>
      </div>

      <div className="container">
        <div className="card">
          <div className="controls">
            <label className="field">
              Battery
              <select value={preset} onChange={applyPreset}>
                {BATTERY_PRESETS.map((p) => (
                  <option key={p.name} value={p.name}>{p.name}</option>
                ))}
              </select>
            </label>
            <label className="field">
              Capacity (kWh)
              <input type="number" step="0.5" value={battery.capacity_kwh} onChange={set("capacity_kwh")} />
            </label>
            <label className="field">
              Power (kW)
              <input type="number" step="0.5" value={battery.power_kw} onChange={set("power_kw")} />
            </label>
            <label className="field">
              Efficiency
              <input type="number" step="0.01" min="0.5" max="1" value={battery.efficiency} onChange={set("efficiency")} />
            </label>
            <label className="field">
              Current SoC (kWh)
              <input type="number" step="0.5" value={battery.initial_soc_kwh} onChange={set("initial_soc_kwh")} />
            </label>
            <label className="field">
              Reserve (kWh)
              <input type="number" step="0.5" value={battery.reserve_kwh} onChange={set("reserve_kwh")} />
            </label>
            <button className="primary" onClick={runOptimise} disabled={!series || loading}>
              {loading ? "Optimising…" : "Optimise"}
            </button>
          </div>
          {!series && !error && <p className="note">Loading live Elexon prices…</p>}
          {series && (
            <p className="note">
              <span style={{ color: SOURCE_INFO[series.source].color, fontWeight: 600 }}>
                ● {SOURCE_INFO[series.source].text}
              </span>
              <br />
              {series.prices.length} half-hourly settlement periods · {dateRange}
            </p>
          )}
          {error && <p className="note" style={{ color: "#b42318" }}>{error}</p>}
        </div>

        {result && (
          <>
            <div className="cards">
              <div className="card metric">
                <div className="k">Arbitrage profit (this day)</div>
                <div className="v green">{money(result.net_profit)}</div>
              </div>
              <div className="card metric">
                <div className="k">Projected monthly</div>
                <div className="v">{money(result.projected_monthly)}<span style={{ fontSize: 13 }}>/mo</span></div>
              </div>
              <div className="card metric">
                <div className="k">Data source</div>
                <div className="v" style={{ fontSize: 16 }}>
                  {series
                    ? series.source === "synthetic" ? "Synthetic" : "Live Elexon"
                    : result.source}
                </div>
              </div>
            </div>

            <div className="card chartcard">
              <h3>Price and optimised charging</h3>
              <ResponsiveContainer width="100%" height={280}>
                <ComposedChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="t" interval={5} fontSize={11} />
                  <YAxis yAxisId="l" fontSize={11} label={{ value: "£/MWh", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <YAxis yAxisId="r" orientation="right" fontSize={11} label={{ value: "kW", angle: 90, position: "insideRight", fontSize: 11 }} />
                  <Tooltip labelFormatter={tooltipLabel} />
                  <Legend />
                  <Bar yAxisId="r" dataKey="charge" name="Charge (kW)" fill="#1f4e79" opacity={0.75} />
                  <Bar yAxisId="r" dataKey="discharge" name="Discharge (kW)" fill="#2e7d32" opacity={0.75} />
                  <Line yAxisId="l" type="monotone" dataKey="price" name="Price (£/MWh)" stroke="#e67e22" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <div className="card chartcard">
              <h3>Battery state of charge</h3>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="t" interval={5} fontSize={11} />
                  <YAxis fontSize={11} label={{ value: "kWh", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <Tooltip labelFormatter={tooltipLabel} />
                  <Area type="monotone" dataKey="soc" name="State of charge (kWh)" stroke="#2e7d32" fill="#2e7d32" fillOpacity={0.12} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <p className="note">
              Perfect-foresight arbitrage on a single day, extrapolated to a month. Wholesale
              arbitrage alone is marginal — which is precisely why grid services and VPPs
              exist. Treat the monthly figure as an idealised ceiling.
            </p>
          </>
        )}
      </div>

      <div className="footer">
        Prices via Elexon BMRS (direct, backend proxy fallback); optimisation with linopy on
        Cloud Run. A public-data demonstration of price-aware home-battery dispatch.
      </div>
    </>
  );
}
