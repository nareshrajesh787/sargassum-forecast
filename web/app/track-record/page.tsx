"use client";
import { useState } from "react";
import { useJson } from "@/lib/useJson";
import type { Results, TrackRecord } from "@/lib/types";
import { num, pct } from "@/lib/colors";
import HeadlineTable from "@/components/HeadlineTable";
import Reliability from "@/components/Reliability";
import { ErrorBox, Loading } from "@/components/State";

export default function TrackRecordPage() {
  const tr = useJson<TrackRecord>("/api/v1/track_record.json");
  const res = useJson<Results>("/api/v1/results.json");
  const [season, setSeason] = useState("2025-2026");
  return (
    <>
      <h1>Track record</h1>
      <h2>Live forecasts (frozen daily, scored as beach reports arrive)</h2>
      {tr.state === "loading" && <Loading what="live track record" />}
      {tr.state === "error" && <ErrorBox message={tr.message} />}
      {tr.state === "ready" && (
        <div className="card">
          {tr.data.n === 0 ? (
            <p style={{ margin: 0 }}>No live forecast has matured yet. {tr.data.note}</p>
          ) : (
            <table>
              <tbody>
                <tr><th>Scored site-days</th><td className="num">{tr.data.n}</td></tr>
                <tr><th>Brier (served model)</th><td className="num">{num(tr.data.brier, 4)}</td></tr>
                <tr><th>Brier (climatology)</th><td className="num">{num(tr.data.brier_climatology, 4)}</td></tr>
                <tr><th>Brier skill vs climatology</th><td className="num">{num(tr.data.bss_vs_climatology)}</td></tr>
                <tr><th>ROC-AUC</th><td className="num">{num(tr.data.auc ?? null)}</td></tr>
                <tr><th>Observed event rate</th><td className="num">{pct(tr.data.event_rate, 1)}</td></tr>
              </tbody>
            </table>
          )}
          <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>Updated {tr.data.updated_utc}. {tr.data.n > 0 && tr.data.note}</p>
        </div>
      )}
      <h2>Held-out test seasons (scored once, models frozen)</h2>
      {res.state === "loading" && <Loading what="test results" />}
      {res.state === "error" && <ErrorBox message={res.message} />}
      {res.state === "ready" && (
        <>
          <p className="muted">
            Test seasons unlocked {res.data.test_unlocked_utc}; intervals are 95% weekly block bootstrap. A difference counts
            only if its interval excludes zero. Source: {res.data.headline.source}.
          </p>
          <div className="controls" role="radiogroup" aria-label="Season">
            {["2025-2026", "2025", "2026"].map((s) => (
              <label key={s}><input type="radio" name="season" value={s} checked={season === s} onChange={() => setSeason(s)} /> {s === "2025-2026" ? "Both seasons" : s}</label>
            ))}
          </div>
          <div className="card"><HeadlineTable rows={res.data.headline.rows} season={season} /></div>
          <h2>Reliability, 2025–2026</h2>
          <div className="grid2">
            <div className="card"><Reliability bins={res.data.reliability.bins} models={["B1", "M1_fc", "M2"]} /></div>
            <div className="card">
              <p style={{ marginTop: 0 }}>
                Points above the diagonal mean the model forecast too low. The served model (M2) was calibrated on the quiet
                2024 season and under-forecast the high-sargassum 2025–2026 seasons (2026 had the highest event rate on record). The 80% band shown on the map comes from this
                test data.
              </p>
              <p className="muted" style={{ fontSize: 13 }}>Source: {res.data.reliability.source}</p>
            </div>
          </div>
        </>
      )}
    </>
  );
}
