# KICKOFF.md — run this phase by phase

Paste into Claude Code in an empty repo `sargassum-forecast` with `CLAUDE.md` and `docs/SPEC.md`
(the spec doc exported as Markdown) already committed. Follow CLAUDE.md at all times.
Use high effort for Phases 1, 3 and 4 (subtle wrong answers are likeliest there); medium elsewhere.

---

## Phase 0 — Scaffold and archivers (day 1)

1. Python project (`uv`), ruff, mypy, pytest; `Makefile` with the targets in CLAUDE.md.
2. `.github/workflows/ci.yml` (tests on PR), `.claude/settings.json` with a Stop hook running
   `make test` and deny rules for `git push --force`, `git push origin main`, and writes to `data/test_lock/`.
3. `pipeline/ingest/sir_archive.py` + `.github/workflows/sir_archive.yml` (daily): download
   `https://cwcgom.aoml.noaa.gov/SIR/KMZ/sargassum_risk_YYYYMMDD.kmz` and the matching
   `Sargassum_risk_currents_FA_YYYYMMDD.kmz` and PDF; store under `archive/sir/` (Git LFS or a release
   asset if size grows). Missing day → log, do not fail the run.
4. `pipeline/ingest/fiu.py` + weekly snapshot job: page through
   `https://five.epicollect.net/api/export/entries/sargassum-watch?per_page=1000&page=N`, save raw JSON
   snapshots with a fetch timestamp. Never commit photo files.
5. `docs/WORKLOG.md`, `docs/DATA_SOURCES.md` stubs.

Done when CI is green and the SIR archiver has committed today's files. Stop and report.

## Phase 1 — Data spike → `docs/FEASIBILITY.md` (days 1–3) — GATE G1

For each source in SPEC "Data spec": write the adapter, pull a sample, record coverage, latency,
throughput, license text and failure modes.

- AFAI: `noaa_aoml_atlantic_oceanwatch_AFAI_1D` (and `_3D`) via ERDDAP griddap netCDF, month by month,
  box 23–28N, 82–78W. Measure values/second; extrapolate the full 2019–2026 Mar–Oct pull; choose the
  coarsening/box plan that finishes in under 12 hours.
- FIU labels: build site-day severity for all 8 Broward sites, 2019–2026. Report site-days per season,
  missing-day rate, severity distribution per season.
- Currents: Copernicus Marine `GLOBAL_ANALYSISFORECAST_PHY_001_024` (SMOC hourly). Confirm forecast access
  and archive depth. Answer the open question: is the multi-year reanalysis available for 2019–2021 at the
  same grid? If not, record "physics features from 2022 only".
- Open-Meteo marine (currents, waves) and historical-forecast winds for each site, 2022–2026.
- Rerun every spike number in SPEC "Feasibility tests" as `spike/*.py` with committed outputs; flag any
  number that differs by more than 0.03.

Gate G1: summary + go/no-go per source + the one decision needed.

## Phase 2 — Dataset and baselines (days 4–8) — GATE G2

- `pipeline/labels/`: frozen severity rules; event = severity ≥ 2; heavy = 3; missing stays missing.
- `pipeline/features/`: every feature with `available_at`; AFAI coastal band (1.5–10 km) and upstream
  corridor stats; onshore wind component per site (shore-normal from site geometry); waves; tide phase;
  day-of-season. Parquet, versioned.
- `models/baselines.py`: B0 persistence (latest report ≤ 3 days old, calibrated conditional rate from
  train), B1 site × day-of-season climatology (smoothed, train only), B2 SIR-style index (Trinanes et al.:
  AFAI anomaly vs multi-day baseline within 50 km of each site), B3 = B2 + onshore wind (logistic, train).
- `eval/`: Brier, BSS vs B0 and B1, ROC-AUC, PR-AUC, reliability bins, skill vs lead (1, 2, 3, 5, 7),
  weekly block bootstrap (1,000), paired bootstrap for differences. Validation season only at this point.

Gate G2: `make results` regenerates the validation table from scratch.

## Phase 3 — Physics P1 (days 8–13) — GATE G3

- `physics/drift.py`: OpenDrift `OceanDrift` with Copernicus SMOC reader and wind reader. Seed particles
  from AFAI-positive pixels in the upstream domain, weighted by AFAI above background. Run 7 days forward
  from each issue date; stranding on land counts as arrival.
- `physics/arrivals.py`: per site and lead, count particles arriving within 5 km → arrival index.
- Windage sweep 0–3% (and with/without explicit Stokes drift) on the 2024 validation season only.
- Cache runs; the daily run must finish in under 15 minutes on a GitHub runner.

Gate G3: P1 scored alone vs B0/B1 on validation. If it does not beat B1 at any lead, say so plainly and continue.

## Phase 4 — Hybrid, calibration, freeze (days 12–16) — GATE G4

- M1 LightGBM (lead as a feature) on B0–B3, P1, AFAI, winds, waves, tide, season. Hyperparameters tuned
  on validation with a small budget (≤ 50 trials). M2 = isotonic calibration fit on validation.
- Ablations: M1 without P1, without AFAI, without wind.
- Run `leakage-cop`. Then, once, unlock test: score every model on 2025 and 2026 separately and pooled.
  Commit `outputs/results_test.csv`, reliability plots, skill-vs-lead plot, failure gallery (10 worst
  misses with AFAI map, particles, winds and the beach report). Freeze: tag `v0.1-test-frozen`.
- Run `honesty-cop` on a draft results section.

Gate G4: results summary with CIs. No further model changes after this gate.

## Phase 5 — Decision layer (days 14–17)

- `decision/knapsack.py`: port Costa's `knapsack_select` (credit the Costa repo and its authors); keep
  the brute-force equality test; add a property test (more budget never lowers value).
- `decision/backtest.py`: 8 sites as zones, editable hours (2–4) and weights (1); budget 4–16; booking
  lead L = 2 (also 1 and 3); policies reactive, climatology, forecast-aware (M2), oracle. Metrics:
  event site-days covered per crew-hour, share of oracle, regret; bootstrap CIs. Label as simulated.
- `web/lib/knapsack.ts` port, tested against the Python version on 1,000 random cases.

## Phase 6 — Ops, API, app (days 16–24) — GATE G5 (run in a parallel worktree with Phase 5)

- `.github/workflows/daily.yml`: ingest → P1 → M2 → freeze `outputs/forecasts/YYYY-MM-DD.json` (append-only,
  with model version and input hashes) → score matured forecasts into `track_record.json` → publish static
  API files → open an issue if any input is stale > 3 days.
- Static API exactly as SPEC "Application, API and operations". Optional Vercel function `/point`.
- Next.js app on Vercel: forecast map (MapLibre + OSM), lead slider, drift overlay, crew planner,
  track record, methods + model card. Loading/empty/error states; keyboard navigation; mobile.
- Costa PR: `ForecastProvider` filling `forecastRisk` per zone from the nearest site or `/point`,
  keeping Costa's scenario/live labeling. Open the PR; do not merge.

Gate G5: live URL, one successful unattended daily run, PR link.

## Phase 7 — Docs and release (days 24–28)

README (problem, architecture diagram, results table from `outputs/`, limitations, attribution),
`docs/MODEL_CARD.md`, `docs/DATA_SOURCES.md`, LICENSE (MIT for code), demo GIF. Run `honesty-cop`.
A clean clone + `make data results` must reproduce every table.

Final report to owner: what shipped, headline numbers with CIs, known weaknesses, and the cold-email
line filled from `outputs/` only.
