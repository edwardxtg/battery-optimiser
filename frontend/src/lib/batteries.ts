// Indicative specs for common GB home-battery brands, as form presets.
// Figures are representative single-unit values for quick selection, not exact
// per-model specs — users can adjust after picking.

export interface Preset {
  name: string;
  capacity_kwh: number;
  power_kw: number;
}

export const BATTERY_PRESETS: Preset[] = [
  { name: "Custom", capacity_kwh: 13.5, power_kw: 5.0 },
  { name: "GivEnergy (9.5 kWh)", capacity_kwh: 9.5, power_kw: 3.6 },
  { name: "Fox ESS (10.4 kWh)", capacity_kwh: 10.4, power_kw: 3.7 },
  { name: "SolaX (11.6 kWh)", capacity_kwh: 11.6, power_kw: 4.6 },
  { name: "Sigenergy (8 kWh)", capacity_kwh: 8.0, power_kw: 5.0 },
  { name: "Solis (10 kWh)", capacity_kwh: 10.0, power_kw: 3.6 },
  { name: "SolarEdge (10 kWh)", capacity_kwh: 10.0, power_kw: 5.0 },
];
