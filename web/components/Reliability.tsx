"use client";
import { useState } from "react";
import { SERIES, pct } from "@/lib/colors";

type Bin = { model: string; p_mean: number; obs_freq: number; n: number };

/** Reliability diagram (single axis, 0–100% both ways). Hover or focus a point for its numbers. */
export default function Reliability({ bins, models }: { bins: Bin[]; models: (keyof typeof SERIES)[] }) {
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const W = 350, H = 300, P = 50, max = 0.7;
  const sx = (v: number) => P + (Math.min(v, max) / max) * (W - P - 12);
  const sy = (v: number) => H - P - (Math.min(v, max) / max) * (H - P - 12);
  const ticks = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7];
  return (
    <figure style={{ margin: 0, position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: 420 }} role="img" aria-label="Reliability diagram: forecast probability vs observed frequency on 2025–2026">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={sx(0)} x2={sx(max)} y1={sy(t)} y2={sy(t)} stroke="var(--grid)" strokeWidth={0.6} />
            <text x={P - 6} y={sy(t) + 4} fontSize={10} textAnchor="end" fill="var(--muted)">{pct(t)}</text>
            <text x={sx(t)} y={H - P + 14} fontSize={10} textAnchor="middle" fill="var(--muted)">{pct(t)}</text>
          </g>
        ))}
        <line x1={sx(0)} y1={sy(0)} x2={sx(max)} y2={sy(max)} stroke="var(--axis)" strokeWidth={1} />
        <text x={(W + P) / 2} y={H - 6} fontSize={11} textAnchor="middle" fill="var(--ink-2)">Forecast probability</text>
        <text x={12} y={(H - P) / 2} fontSize={11} textAnchor="middle" fill="var(--ink-2)" transform={`rotate(-90 12 ${(H - P) / 2})`}>Observed frequency</text>
        {models.map((m) => {
          const b = bins.filter((x) => x.model === m).sort((a, c) => a.p_mean - c.p_mean);
          return (
            <g key={m}>
              <polyline fill="none" stroke={SERIES[m]} strokeWidth={2} points={b.map((x) => `${sx(x.p_mean)},${sy(x.obs_freq)}`).join(" ")} />
              {b.map((x, i) => {
                const text = `${m}: forecast ${pct(x.p_mean, 1)}, observed ${pct(x.obs_freq, 1)} (n=${x.n})`;
                const show = () => setTip({ x: sx(x.p_mean), y: sy(x.obs_freq), text });
                return (
                  <circle key={i} cx={sx(x.p_mean)} cy={sy(x.obs_freq)} r={5} fill={SERIES[m]} stroke="var(--surface)" strokeWidth={2}
                    tabIndex={0} aria-label={text} onMouseEnter={show} onFocus={show} onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}>
                    <title>{text}</title>
                  </circle>
                );
              })}
              {b.length > 0 && (
                <text x={sx(b[b.length - 1].p_mean) + 7} y={sy(b[b.length - 1].obs_freq) + 4} fontSize={11} fill="var(--ink)">{m}</text>
              )}
            </g>
          );
        })}
      </svg>
      {tip && (
        <div role="tooltip" style={{ position: "absolute", left: `${(tip.x / W) * 100}%`, top: `${(tip.y / H) * 100}%`, transform: "translate(8px,-110%)",
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 8px", fontSize: 12, pointerEvents: "none", whiteSpace: "nowrap" }}>
          {tip.text}
        </div>
      )}
      <figcaption className="legend" style={{ marginTop: 4 }}>
        {models.map((m) => (<span key={m}><i style={{ background: SERIES[m] }} />{m}</span>))}
        <span>diagonal = perfectly calibrated</span>
      </figcaption>
    </figure>
  );
}
