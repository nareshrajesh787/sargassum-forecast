"use client";
import { useMemo, useState } from "react";
import { useJson } from "@/lib/useJson";
import type { Forecast, Results } from "@/lib/types";
import { knapsackSelect } from "@/lib/knapsack.ts";
import { pct } from "@/lib/colors";
import { ErrorBox, Loading } from "@/components/State";

// Editable defaults, same as decision/backtest.py ZONE_HOURS (south → north site order of pipeline/sites.py).
const DEFAULT_HOURS: Record<string, number> = {
  bougainvillea_terrace: 2, mj_state_park: 3, the_palms: 4, commercial_pier: 3,
  sea_ranch_lakes: 2, atlantic_pier: 4, hillsboro_mile_1173: 3, county_line: 2,
};

export default function Planner() {
  const fc = useJson<Forecast>("/api/v1/forecast/latest.json");
  const res = useJson<Results>("/api/v1/results.json");
  const [budget, setBudget] = useState(8);
  const [booking, setBooking] = useState(2);
  const [hours, setHours] = useState<Record<string, number>>(DEFAULT_HOURS);
  const [weights, setWeights] = useState<Record<string, number>>({});

  const plan = useMemo(() => {
    if (fc.state !== "ready") return null;
    const rows = fc.data.sites.map((s) => {
      const l = s.leads.find((x) => x.lead_days === booking)!;
      const w = weights[s.id] ?? 1;
      return { s, l, w, h: hours[s.id] ?? 3 };
    });
    const pick = (key: "probability" | "climatology") =>
      knapsackSelect(rows.map((r, i) => ({ id: String(i), value: r.l[key] * r.w, hours: r.h })), budget);
    return { rows, forecast: pick("probability"), clim: pick("climatology") };
  }, [fc, booking, budget, hours, weights]);

  if (fc.state === "loading") return <Loading what="forecast" />;
  if (fc.state === "error") return <ErrorBox message={fc.message} />;
  if (!plan) return null;
  const chosen = new Set(plan.forecast.ids.map(Number));
  const climChosen = new Set(plan.clim.ids.map(Number));
  const bt = res.state === "ready" ? res.data.backtest.rows.filter((r) => r.budget_hours === budget) : [];

  return (
    <>
      <h1>Crew planner</h1>
      {res.state === "ready" && (() => {
        const m2 = res.data.headline.rows.find((r) => r.season === "2025-2026" && r.model === "M2");
        return m2 ? (
          <p className="notice">
            Experimental, not a warning system. The served forecast had Brier skill {m2.bss_vs_climatology?.toFixed(3)} [
            {m2.bss_ci[0]?.toFixed(3)}, {m2.bss_ci[1]?.toFixed(3)}] versus climatology on the 2025–2026 test seasons (negative = worse).
          </p>
        ) : null;
      })()}
      <p className="muted">
        Exact 0/1 knapsack (ported from the Costa project): pick the beaches that maximise expected sargassum days covered
        (forecast probability × weight) within the crew-hour budget, for crews booked {booking} day{booking > 1 ? "s" : ""} ahead.
      </p>
      <div className="controls">
        <label htmlFor="budget">Budget: <strong>{budget} crew-hours</strong></label>
        <input id="budget" type="range" min={4} max={16} step={1} value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
        <label htmlFor="booking">Booking lead</label>
        <select id="booking" value={booking} onChange={(e) => setBooking(Number(e.target.value))}>
          {[1, 2, 3].map((d) => (<option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>))}
        </select>
      </div>
      <div className="card table-wrap">
        <table>
          <caption className="muted" style={{ textAlign: "left", paddingBottom: 6 }}>
            Plan for {plan.rows[0]?.l.target_date}: the forecast plan sends crews to {plan.forecast.ids.length} beaches using{" "}
            {plan.forecast.hours} of {budget} crew-hours; a plan from climatology alone would send them to {plan.clim.ids.length}{" "}
            beaches ({plan.clim.hours} hours). The two plans score their picks with different probabilities, so their values
            are not compared here; the backtest below compares them against what actually happened.
          </caption>
          <thead>
            <tr><th>Beach</th><th className="num">Forecast</th><th className="num">Climatology</th><th>Hours</th><th>Weight</th><th>Forecast plan</th><th>Climatology plan</th></tr>
          </thead>
          <tbody>
            {plan.rows.map((r, i) => (
              <tr key={r.s.id}>
                <td>{r.s.name}</td>
                <td className="num">{pct(r.l.probability, 1)}</td>
                <td className="num">{pct(r.l.climatology, 1)}</td>
                <td>
                  <select aria-label={`Crew-hours for ${r.s.name}`} value={r.h} onChange={(e) => setHours({ ...hours, [r.s.id]: Number(e.target.value) })}>
                    {[2, 3, 4].map((h) => (<option key={h} value={h}>{h}</option>))}
                  </select>
                </td>
                <td>
                  <input aria-label={`Weight for ${r.s.name}`} type="number" min={0} max={3} step={0.5} value={r.w} style={{ width: 60 }}
                    onChange={(e) => setWeights({ ...weights, [r.s.id]: Math.max(0, Number(e.target.value)) })} />
                </td>
                <td>{chosen.has(i) ? <strong>✓ send crew</strong> : <span className="muted">—</span>}
                  {chosen.has(i) && <div className="muted" style={{ fontSize: 12 }}>value {(r.l.probability * r.w).toFixed(3)} for {r.h} h</div>}</td>
                <td>{climChosen.has(i) ? "✓" : <span className="muted">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>Does planning from the forecast help?</h2>
      {res.state === "ready" ? (
        <div className="card table-wrap">
          <p className="muted" style={{ marginTop: 0 }}>
            {res.data.backtest.label} backtest on the 2025–2026 test seasons, {budget} crew-hours, crews booked {res.data.backtest.booking_lead_days} days
            ahead: share of the events an all-knowing planner would have covered (95% CI). Source: {res.data.backtest.source}.
          </p>
          <table>
            <thead><tr><th>Policy</th><th className="num">Share of oracle</th><th className="num">95% CI</th><th>vs climatology (paired)</th></tr></thead>
            <tbody>
              {bt.map((r) => (
                <tr key={r.policy}>
                  <td>{r.policy}</td>
                  <td className="num">{pct(r.share_of_oracle, 1)}</td>
                  <td className="num">{pct(r.ci[0], 1)}–{pct(r.ci[1], 1)}</td>
                  <td>{r.verdict_vs_climatology ? `${r.verdict_vs_climatology} (${r.minus_climatology! >= 0 ? "+" : ""}${pct(r.minus_climatology, 1)} [${pct(r.minus_climatology_ci![0], 1)}, ${pct(r.minus_climatology_ci![1], 1)}])` : "reference"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(() => {
            const s = res.data.backtest.all_leads_and_budgets_vs_climatology;
            const f = s["forecast"], fc = s["forecast_fc"];
            return f && fc ? (
              <p style={{ marginBottom: 0 }}>
                <strong>Answer: no.</strong> Across all {f.cells} combinations of budget (4–16 h) and booking lead (1–3 days), planning
                from the forecast was better than planning from climatology in {f.better} and worse in {f.worse}; the issue-time
                model was better in {fc.better} and worse in {fc.worse}.
              </p>
            ) : null;
          })()}
          <p className="muted" style={{ fontSize: 13 }}>
            "forecast" uses the served model with target-day weather (an upper bound); "forecast_fc" uses only issue-time data. See Methods.
          </p>
        </div>
      ) : res.state === "error" ? <ErrorBox message={res.message} /> : <Loading what="backtest" />}
    </>
  );
}
