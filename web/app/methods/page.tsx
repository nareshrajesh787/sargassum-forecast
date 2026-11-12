"use client";
import { useJson } from "@/lib/useJson";
import type { Results } from "@/lib/types";
import { num } from "@/lib/colors";
import { ErrorBox, Loading } from "@/components/State";

export default function Methods() {
  const res = useJson<Results>("/api/v1/results.json");
  return (
    <>
      <h1>Methods and model card</h1>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>What is forecast</h2>
        <p>
          The probability that each of 8 Broward County, Florida beaches has a moderate-or-worse sargassum day (water
          slightly or very brown, or the site smells) on a target day 1, 2, 3, 5 or 7 days ahead. Ground truth is FIU
          Sargassum Watch citizen-science reports (2019–2026), merged to one label per beach per day by taking the worst
          report. Severity rules were frozen before any model was trained.
        </p>
        <h2>Models</h2>
        <ul>
          <li><strong>B0 persistence</strong>: the beach&apos;s latest report up to 3 days old.</li>
          <li><strong>B1 climatology</strong>: each beach&apos;s smoothed day-of-year event rate (training seasons only).</li>
          <li><strong>B2 / B3</strong>: a SIR-style satellite (AFAI) anomaly index, alone and with onshore wind.</li>
          <li><strong>P1</strong>: Lagrangian drift (OpenDrift) of satellite-detected sargassum with Copernicus currents and 2% windage; arrivals within 5 km.</li>
          <li><strong>M1</strong>: LightGBM on all of the above plus waves, currents and tides. <strong>M2</strong>: M1 with isotonic calibration fit on 2024 — the model served on the map.</li>
          <li><strong>M1_fc / M2_fc</strong>: the same model using only data available when the forecast is issued.</li>
        </ul>
        <p>
          Training 2020–2023 (2019 used an older survey form), validation 2024, test 2025–2026 scored once after the models
          were frozen. Models marked &quot;upper bound&quot; were trained and tested with weather and ocean conditions observed on the
          target day; live forecasts use real forecasts of those conditions instead, so live skill is expected to be lower.
        </p>
      </div>
      <h2>Results on the held-out test seasons</h2>
      {res.state === "loading" && <Loading what="results" />}
      {res.state === "error" && <ErrorBox message={res.message} />}
      {res.state === "ready" && (
        <div className="card">
          <ul>
            {res.data.headline.rows.filter((r) => r.season === "2025-2026" && ["M2", "M1", "M1_fc", "B0", "P1"].includes(r.model)).map((r) => (
              <li key={r.model}>
                <strong>{r.model}</strong> ({r.upper_bound ? "upper bound" : "issue-time"}): Brier skill vs climatology {num(r.bss_vs_climatology)} [{num(r.bss_ci[0])}, {num(r.bss_ci[1])}]
              </li>
            ))}
          </ul>
          <h3>Does each input matter? (removing it from M1; Brier change, positive = worse)</h3>
          <ul>
            {res.data.ablation.rows.map((r) => (
              <li key={r.model}>{r.model}: {num(r.brier_minus_M1, 4)} [{num(r.ci[0], 4)}, {num(r.ci[1], 4)}], {r.verdict}</li>
            ))}
          </ul>
          <p className="muted" style={{ fontSize: 13 }}>Sources: {res.data.headline.source}, {res.data.ablation.source}. Built from commit {res.data.generated_from_commit}.</p>
        </div>
      )}
      <div className="card" style={{ marginTop: 16 }}>
        <h2 style={{ marginTop: 0 }}>Intended use and limits</h2>
        <ul>
          <li>Research and planning aid for beach crews; <strong>not a warning or public-health system</strong>.</li>
          <li>Validated only for these 8 Broward beaches, March–October. Other places and months are unvalidated.</li>
          <li>Citizen reports are noisy; a missing report is not a clean beach.</li>
          <li>The satellite record (MODIS AFAI) is expected to change in 2027; the pipeline alarms if inputs go stale.</li>
          <li>The crew backtest is simulated: it assumes crews are booked in advance and only considers beaches that reported.</li>
        </ul>
        <p>Full model card, data sources and code: <a href="https://github.com/nareshrajesh787/sargassum-forecast">GitHub repository</a>.</p>
      </div>
    </>
  );
}
