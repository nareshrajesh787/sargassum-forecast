import { pct } from "@/lib/colors";

/** Served probability (black mark), empirical 80% band (blue), climatology (orange tick), all on 0–100%. */
export default function ProbBar({ p, lo, hi, clim }: { p: number; lo: number; hi: number; clim: number }) {
  const x = (v: number) => `${Math.min(100, Math.max(0, v * 100))}%`;
  return (
    <div className="bar" aria-label={`Forecast ${pct(p)}; in 2025–2026, similar forecasts verified ${pct(lo)}–${pct(hi)} of the time; climatology ${pct(clim)}`} role="img">
      <div className="band" style={{ left: x(lo), width: `calc(${x(hi)} - ${x(lo)})` }} />
      <div className="clim" style={{ left: x(clim) }} title={`Climatology ${pct(clim)}`} />
      <div className="mark" style={{ left: `calc(${x(p)} - 2px)` }} title={`Forecast ${pct(p)}`} />
    </div>
  );
}
