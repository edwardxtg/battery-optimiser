// Duration presets for a grid-scale BESS. GB fleet assets are mostly 1–2 hours today,
// with 4-hour builds becoming common; power is fixed at 10 MW so the presets differ
// only in energy capacity. Users can adjust after picking.

export interface Preset {
  name: string;
  capacity_mwh: number;
  power_mw: number;
}

export const BATTERY_PRESETS: Preset[] = [
  { name: "Custom", capacity_mwh: 20.0, power_mw: 10.0 },
  { name: "1-hour (10 MW / 10 MWh)", capacity_mwh: 10.0, power_mw: 10.0 },
  { name: "2-hour (10 MW / 20 MWh)", capacity_mwh: 20.0, power_mw: 10.0 },
  { name: "4-hour (10 MW / 40 MWh)", capacity_mwh: 40.0, power_mw: 10.0 },
];
