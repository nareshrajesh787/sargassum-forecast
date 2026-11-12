"use client";
import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useJson } from "@/lib/useJson";
import type { Forecast } from "@/lib/types";
import { PROB_LEGEND, pct } from "@/lib/colors";
import ProbBar from "@/components/ProbBar";
import { ErrorBox, Loading, Empty } from "@/components/State";

const ForecastMap = dynamic(() => import("@/components/ForecastMap"), { ssr: false, loading: () => <Loading what="map" /> });
const LEADS = [1, 2, 3, 5, 7];

export default function Home() {
  const fc = useJson<Forecast>("/api/v1/forecast/latest.json");
  const drift = useJson<GeoJSON.FeatureCollection>("/api/v1/drift/latest.geojson");
  const [leadIdx, setLeadIdx] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [showDrift, setShowDrift] = useState(true);
  const lead = LEADS[leadIdx];

  const sites = fc.state === "ready" ? fc.data.sites : [];
  const sorted = useMemo(() => [...sites].sort((a, b) => b.lat - a.lat), [sites]);

  if (fc.state === "loading") return <Loading what="today's forecast" />;
  if (fc.state === "error") return <ErrorBox message={fc.message} />;
  const f = fc.data;
  if (!f.sites?.length) return <Empty>No forecast has been published yet.</Empty>;
  const anyLead = f.sites[0].leads.find((l) => l.lead_days === lead);

  return (
    <>
      <h1>Sargassum beaching forecast</h1>
      <p className="muted">
        Chance of a moderate-or-worse sargassum day (brown water or smell) at each beach. Issued {f.issue_date} (model{" "}
        {f.model_version}); target date {anyLead?.target_date}.
      </p>
      <p className="notice">
        {f.disclaimer}
        {anyLead && !anyLead.in_validated_season && " This date is outside the validated March–October season."}
        {f.preview && ` ${f.preview_note}`}
      </p>
      <div className="controls">
        <label htmlFor="lead">
          Lead: <strong>{lead} day{lead > 1 ? "s" : ""}</strong>
        </label>
        <input id="lead" type="range" min={0} max={LEADS.length - 1} step={1} value={leadIdx}
          aria-valuetext={`${lead} days ahead`} onChange={(e) => setLeadIdx(Number(e.target.value))} />
        <label>
          <input type="checkbox" checked={showDrift} onChange={(e) => setShowDrift(e.target.checked)} /> Drift particles (P1){" "}
          {drift.state === "error" && <span className="muted">(unavailable)</span>}
        </label>
        <span className="muted" style={{ fontSize: 13 }}>Drift model: {f.p1_status}</span>
      </div>
      <div className="grid2">
        <div>
          <ForecastMap sites={f.sites} lead={lead} selected={selected} onSelect={setSelected}
            drift={drift.state === "ready" ? drift.data : null} showDrift={showDrift} />
          <div className="legend" style={{ marginTop: 8 }} aria-label="Probability colour legend">
            {PROB_LEGEND.map((l) => (<span key={l.label}><i style={{ background: l.color }} />{l.label}</span>))}
            <span>outer ring = upper end of 80% band</span>
          </div>
        </div>
        <section className="card" aria-label="Sites">
          <h2 style={{ marginTop: 0 }}>Beaches (north → south)</h2>
          <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
            Black mark: forecast. Blue band: how often similar forecasts verified in 2025–2026 (80% range). Orange tick: climatology.
          </p>
          <ul className="sites">
            {sorted.map((s) => {
              const l = s.leads.find((x) => x.lead_days === lead);
              if (!l) return null;
              return (
                <li key={s.id}>
                  <button aria-pressed={selected === s.id} onClick={() => setSelected(s.id)}>
                    <div className="row"><strong>{s.name}</strong><span>{pct(l.probability)}</span></div>
                    <ProbBar p={l.probability} lo={l.interval_80[0]} hi={l.interval_80[1]} clim={l.climatology} />
                    <div className="row muted" style={{ fontSize: 12, marginTop: 4 }}>
                      <span>80% band {pct(l.interval_80[0])}–{pct(l.interval_80[1])}</span>
                      <span>climatology {pct(l.climatology)}</span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </>
  );
}
