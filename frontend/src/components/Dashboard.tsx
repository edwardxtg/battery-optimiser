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
  capacity_mwh: 20.0,
  power_mw: 10.0,
  efficiency: 0.88,
  initial_soc_mwh: 2.0,
  soc_min_mwh: 1.0,
  cycle_cost_per_mwh: 5.0,
};

function money(x: number): string {
  return "£" + Math.round(x).toLocaleString("en-GB");
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
    if (battery.soc_min_mwh > battery.initial_soc_mwh) {
      setError("SoC floor can't be higher than the current state of charge (MWh).");
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
    setBattery((b) => ({ ...b, capacity_mwh: p.capacity_mwh, power_mw: p.power_mw }));
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
        charge: Math.round(result.charge_mw[i] * 100) / 100,
        discharge: Math.round(result.discharge_mw[i] * 100) / 100,
        soc: Math.round(result.soc_mwh[i] * 100) / 100,
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
        <h1>BESS Dispatch Optimiser</h1>
        <p>
          Enter a grid-scale battery and optimise a day of dispatch to arbitrage GB wholesale
          electricity prices — buy low, sell high — within the battery&rsquo;s physical
          limits. v1 uses live prices with perfect foresight, so the result is the
          upper bound on wholesale-only revenue. Ancillary services and cycling limits are
          the next layers of a full revenue model.
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
              Capacity (MWh)
              <input type="number" step="1" value={battery.capacity_mwh} onChange={set("capacity_mwh")} />
            </label>
            <label className="field">
              Power (MW)
              <input type="number" step="1" value={battery.power_mw} onChange={set("power_mw")} />
            </label>
            <label className="field">
              Efficiency
              <input type="number" step="0.01" min="0.5" max="1" value={battery.efficiency} onChange={set("efficiency")} />
            </label>
            <label className="field">
              Current SoC (MWh)
              <input type="number" step="1" value={battery.initial_soc_mwh} onChange={set("initial_soc_mwh")} />
            </label>
            <label className="field">
              SoC floor (MWh)
              <input type="number" step="1" value={battery.soc_min_mwh} onChange={set("soc_min_mwh")} />
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
                <div className="k">Annualised</div>
                <div className="v">{money(result.gbp_per_mw_year)}<span style={{ fontSize: 13 }}>/MW/yr</span></div>
              </div>
              <div className="card metric">
                <div className="k">Cycles (this day)</div>
                <div className="v">{result.cycles.toFixed(2)}</div>
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
                  <YAxis yAxisId="r" orientation="right" fontSize={11} label={{ value: "MW", angle: 90, position: "insideRight", fontSize: 11 }} />
                  <Tooltip labelFormatter={tooltipLabel} />
                  <Legend />
                  <Bar yAxisId="r" dataKey="charge" name="Charge (MW)" fill="#1f4e79" opacity={0.75} />
                  <Bar yAxisId="r" dataKey="discharge" name="Discharge (MW)" fill="#2e7d32" opacity={0.75} />
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
                  <YAxis fontSize={11} label={{ value: "MWh", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <Tooltip labelFormatter={tooltipLabel} />
                  <Area type="monotone" dataKey="soc" name="State of charge (MWh)" stroke="#2e7d32" fill="#2e7d32" fillOpacity={0.12} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <p className="note">
              Perfect-foresight arbitrage on a single day, annualised per MW. Real assets
              capture less than this (they don&rsquo;t know tomorrow&rsquo;s prices) and earn
              more than this (they stack ancillary services on top). Treat the figure as the
              wholesale-only ceiling for this day&rsquo;s spread.
            </p>
          </>
        )}
      </div>

      <div className="footer">
        Prices via Elexon BMRS (direct, backend proxy fallback); optimisation with linopy on
        Cloud Run. A public-data demonstration of a BESS dispatch model.
      </div>
    </>
  );
}
