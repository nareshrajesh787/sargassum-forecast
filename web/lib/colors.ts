// Sequential single-hue blue ramp (dataviz reference palette, steps 150→650); magnitude only, never identity.
const RAMP = ["#b7d3f6", "#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"];
const EDGES = [0.05, 0.1, 0.2, 0.3, 0.45];

export function probColor(p: number): string {
  let i = 0;
  while (i < EDGES.length && p >= EDGES[i]) i++;
  return RAMP[i];
}
export const PROB_LEGEND = [
  { label: "< 5%", color: RAMP[0] },
  { label: "5–10%", color: RAMP[1] },
  { label: "10–20%", color: RAMP[2] },
  { label: "20–30%", color: RAMP[3] },
  { label: "30–45%", color: RAMP[4] },
  { label: "≥ 45%", color: RAMP[5] },
];
// Categorical slots 1–3 (validated) for model series in charts.
export const SERIES = { B1: "#eb6834", M1_fc: "#1baf7a", M2: "#2a78d6" } as const;
export const pct = (x: number | null | undefined, d = 0) => (x == null ? "—" : `${(100 * x).toFixed(d)}%`);
export const num = (x: number | null | undefined, d = 3) => (x == null ? "—" : x.toFixed(d));
