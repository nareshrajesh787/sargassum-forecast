# WORKLOG

Append-only. One entry per session: what was done, what failed, what is unverified, next step.

## 2026-11-10 — Phase 0 (scaffold + archivers), branch `phase-0-scaffold`

**Done**
- uv project (Python 3.12, `uv.lock`), ruff, mypy, pytest; `Makefile` targets from CLAUDE.md
  (`labels/features/results/backtest` are placeholders that exit 1 until their phase).
- `.github/workflows/ci.yml` (PR → `make test`), `.claude/settings.json` (Stop hook runs `make test`;
  deny force-push, push to main, npm/vercel publish, writes to `data/test_lock/`).
- `pipeline/ingest/sir_archive.py` + `sir_archive.yml` (daily 19:30 UTC, 7-day look-back, missing day → log).
- `pipeline/ingest/fiu.py` + `fiu_snapshot.yml` (weekly). Full local snapshot pulled: 14,298 unique entries.
- Moved `SPEC.md` → `docs/SPEC.md` (content unchanged) to match CLAUDE.md/KICKOFF.md paths.

**Deviations / conflicts (for owner)**
- SIR storage: files are ~7.4 MB/day (risk KMZ 1.56 MB + currents KMZ 3.6 MB + PDF 2.3 MB) ≈ 2.7 GB/year,
  beyond plain git and free LFS (1 GB). The archiver keeps bytes out of git, commits
  `archive/sir/manifest.csv` (sha256 per file) and uploads bytes to monthly prereleases `sir-archive-YYYY-MM`.
- SPEC says SIR has no history ("June 2022–2025 → 404"). Reality on 2026-11-10: SIR serves every day from
  **2025-07-01** onward (binary search + 71 weekly samples, 0 gaps); 2025-06-15 and earlier → 404 for KMZ.
  Looks like a rolling window, so the 2025 test season's SIR files may disappear. A full local copy is being
  saved to `data/raw/sir/` (not committed, not uploaded).
- FIU raw snapshots are not committed or uploaded anywhere (public repo + data-courtesy rule); the weekly job
  commits only a summary row to `archive/fiu/manifest.csv`. Durable raw storage = local `data/raw/fiu/`.
- FIU API rate limit: `X-RateLimit-Limit: 5`; bursts get HTTP 429. Adapter paces 13 s/page, honours
  `Retry-After`, resumes `.partial` snapshots. Full pull ≈ 3.5 min.

**Failed / blocked**
- Creating the `sir-archive-2026-11` GitHub release from this machine was blocked by the session's permission
  classifier, so "SIR archiver has committed today's files" is only satisfied after merge, when the scheduled
  (or manually dispatched) workflow runs on `main`. Archiver verified locally (no upload).

**Unverified**: the Actions workflows have not run yet (scheduled/dispatch workflows only run from `main`).
`ci.yml` is verified by this PR. FIU courtesy-email status unknown to the agent.

**Next**: owner merges → dispatch `sir-archive` (optionally `days=500` to capture the full 2025-07-01+ window
as release assets) → Phase 1.

## 2026-11-10 — Phase 1 (data spike), branch `phase-1-data-spike` (stacked on `phase-0-scaffold`)

**Done**
- Adapters: `pipeline/ingest/afai.py` (ERDDAP netCDF, month by month, throughput log),
  `pipeline/ingest/copernicus.py` (catalogue + `subset_smoc`), `pipeline/ingest/openmeteo.py` (marine currents/waves,
  historical-forecast winds, previous-runs lead-L winds), `pipeline/geo.py` (Natural Earth distance-to-coast),
  `pipeline/sites.py` (8 sites, median-GPS coordinates + name aliases), `pipeline/labels/fiu_labels.py` (frozen rules).
- Cached locally: AFAI 1D + 3D, full box 23–28N 82–78W at 0.015°, Mar–Oct 2019–2026 (all seasons, not just one);
  Open-Meteo 2022-01-01 → 2026-10-31 for 8 sites; FIU snapshot; SIR back-fill from 2025-06-28 (`data/raw/sir/`).
- `make spike` regenerates `outputs/spike/*.json`, `outputs/spike/comparison.csv` and `outputs/feasibility/*` from cache.
- `docs/FEASIBILITY.md` with go/no-go per source; `docs/DATA_SOURCES.md` updated; 49 offline tests.

**Conflicts with SPEC (raised at G1; SPEC not edited)**
1. SIR history is online from 2025-07-01 (SPEC: none).
2. Copernicus SMOC hourly starts 2020-11-01 (SPEC: 2-year rolling, physics from 2022). GLORYS12 (same grid) is daily-only.
3. No historical forecast archive for currents. Lead-specific winds only from 2024-01-19. The leakage rule "archived forecasts
   wherever possible" can be met only for winds, 2024+.
4. 2019 FIU form had no water-colour question → 2019 severity cannot reach 3 (frozen rules unchanged).
5. Severity precedence was not specified; `none_first` chosen because it reproduces the spike counts (definition, not tuning).
6. ERDDAP ≈ 590K values/s (SPEC assumed ~30K/min), so no coarsening.

**Rule tension**: `spike/s06`, `s07`, `s08` read 2025–2026 labels because KICKOFF Phase 1 / G2 require reproducing the spike
numbers. Only the pre-registered fixed-rule metrics are computed; nothing fitted. Flagged in the outputs (`touches_test_seasons`).

**Failed / fixed during the session**
- FIU API 429 after 5 quick pages → paced + resumable.
- Open-Meteo `cell_selection=sea` snapped 3 sites to a land-side wave cell returning only nulls → marine feeds now query
  0.025° offshore and warn on all-null chunks. Re-pulled both marine feeds.
- Creating GitHub releases from this machine was blocked by the permission classifier (Phase 0 SIR upload).

**Unverified**: Copernicus data access/throughput (no credentials); Copernicus licence text not fetched; Open-Meteo call
weights are my estimate; spike definitions for s02/s03/s04/s08 were not recorded in SPEC, so some differences may be
definition gaps (see FEASIBILITY §5); FIU courtesy-email status.

**Next**: G1 decision (driver policy) → Phase 2 (labels into the feature store with `available_at`, Zarr AFAI, B0–B3).

## 2026-11-10 — Phase 2 (dataset + baselines), branch `phase-2-dataset-baselines` (stacked on `phase-1-data-spike`)

**G1 decision not answered.** The owner pasted Phases 2–3 without replying on the driver policy, so the defaults stated in
FEASIBILITY §7 were applied: perfect-prog drivers (flagged) + lead-L forecast-wind sensitivity; train 2020–2023
(2019-included sensitivity); P1 from 2021.

**Done**
- `pipeline/ingest/tides.py` (NOAA CO-OPS 8722956 hi/lo predictions); February AFAI cached for 30-day baselines.
- `pipeline/features/afai_grid.py`: block-median background, anomaly, detection (Wang & Hu 2016 threshold 1.79e-4,
  not tuned) → `data/interim/afai/{1D,3D}.zarr` + daily region stats. Seasons 2019–2024 only. Verified that the 3D
  product is the trailing composite d−2..d (3D-valid pixels ⊆ union of 1D valid pixels for d−2..d, 0 exceptions).
- `pipeline/features/build.py`: feature store v1 (39,505 rows × 61 features, seasons 2019–2024) with an `avail_<group>` column
  per group. Perfect-prog groups (wind_pp, waves_pp, curr_pp) are declared and tested as the only groups whose data is
  newer than the issue time. Lead-L forecast winds (wind_fc) are leakage-safe (2024 only).
- `models/baselines.py` (B0–B3, plus B3_fc = B3 fed lead-L forecast winds), `eval/` (metrics, weekly block bootstrap with
  1,000 resamples, paired Brier and AUC differences), `eval/run_val.py` → `outputs/results_val*.csv`,
  `outputs/reliability_val.csv`, `outputs/wind_pp_vs_fc_val.csv`, `outputs/figures/*.png`.
- G2 check: `rm -rf data/interim data/features && make results` rebuilt everything in 1 min 40 s, and the results CSVs were
  byte-identical to the previous run.

**Results (validation 2024 only; `outputs/results_val.csv`, `results_val_paired.csv`)**
- No baseline beats B1 or B0 on Brier with a CI excluding zero (leads pooled). B3 is significantly *worse* than B0 on Brier
  (miscalibrated: trained on 2022–23, event rates 0.206 / 0.124, vs 0.092 in 2024). B3_fc is significantly worse than both.
- B3 *discriminates*: AUC 0.648 [0.601, 0.693]. The paired AUC difference vs B0 is +0.144 [0.091, 0.200] and vs B1 +0.097 [0.014, 0.188].
- Persistence is uninformative in 2024: B0 AUC 0.504 [0.479, 0.525].

**Fixed during the session**
- ERDDAP nearest-time snapping put 2024-07-01 into both the June and July files → `afai.trim`, cache repaired (1 step per
  product); `f01` now counts steps from files. FEASIBILITY numbers updated (2024 missing days 3 → 4; s08 AFAI AUCs moved
  by ≤ 0.0035 because February is now cached).
- Open-Meteo currents are served in km/h → converted to m/s. All-null columns arrive as object dtype → coerced.
- Dropped `pandas-stubs` (46 of 54 mypy errors were stub-union noise).

**Found / unverified**
- `gfs_seamless` mixes a high-resolution short-range model with GFS: lead-1 forecast onshore wind averages 1.85 m/s, leads 2–7
  average 3.15–3.83 m/s, and perfect-prog averages 2.65 m/s (`wind_pp_vs_fc_val.csv`). B3_fc's degradation is partly a model/resolution
  switch, not forecast error alone. Fix: re-pull wind_hf + wind_prev pinned to one model (GFS only). Deferred because today's
  Open-Meteo usage was already ≈ 6k of 10k calls.
- AFAI 1-day latency (available at d+1.5 d) follows the SPEC and has not been checked against ERDDAP publication times.
- Coastal-band detection fractions are high (0.28–0.45 vs 0.09–0.14 offshore) → likely near-shore AFAI bias; B2
  uses a temporal anomaly to cancel it. Phase 3 seeding must not trust near-shore pixels.
- SIR back-fill finished: 2025-06-28 → 2026-11-09, 6.2 GB local (`feasibility/sir_archive.json`).

**Next**: Phase 3 (P1 drift) needs Copernicus credentials (`copernicusmarine login`).

## 2026-11-10 — Phase 3 (physics P1), branch `phase-3-physics` (stacked on `phase-2-dataset-baselines`) — BLOCKED

**Blocked:** no Copernicus Marine credentials (no env vars, no `~/.copernicusmarine`), so SMOC currents and L4 winds cannot be
downloaded, and P1 cannot be run or scored. Gate G3 is not reached.

**Done (all testable without Copernicus data)**
- OpenDrift 1.14.11 added. `physics/forcing.py` (SMOC → CF currents in two modes: `total` = utotal incl. Stokes, `no_stokes`
  = uo+utide; Copernicus L4 hourly 0.125° winds; season download), `physics/seed.py` (3D AFAI field of day I−1, detections
  ≥ 3 km offshore, sampled ∝ anomaly above threshold), `physics/drift.py` (OceanDrift, stranding, all windage groups 0–3% in
  one run, cached arrival tables), `physics/arrivals.py` (first entry within 5 km per site, lead windows (24L−6, 24L+18] h
  after the I−1 18:00 seed), `physics/score.py` (sweep by 2024 AUC → mapping fit on 2021–2023 → paired bootstrap vs B0/B1).
- Gridded winds: Copernicus `WIND_GLO_PHY_L4_MY_012_006` covers 2007 → 2026-06-20 and NRT covers 2024-06-13 → present
  (catalogue, same account). Open-Meteo is point-only and would cost ~6k calls per season for a wind grid.
- Measured: one run with 8,000 particles (2,000 × 4 windages) × 186 h took 8.4 s on synthetic forcing with real AFAI seeds (2024-06-15,
  370 seed pixels). Projection: 2024 sweep ≈ 252 issue days × 2 modes ≈ 70 min; the daily job is far under 15 min. Synthetic
  forcing, so real-reader interpolation time is unverified.
- Found: OpenDrift stores `wind_drift_factor` as float32 (0.03 → 0.0299999993); arrivals now round in float64.
- 69 tests pass, including an end-to-end OpenDrift run (onshore flow strands at The Palms; higher windage arrives no later).

**Choices to review at G3**: seed time 18:00 UTC on I−1; seeds ≥ 3 km offshore; 2,000 particles per windage group;
diffusivity 10 m²/s (fixed); config chosen by 2024 AUC (8 configurations → optimistic 2024 AUC for P1, to be disclosed);
P1 is perfect-prog (analysed currents and winds after the issue time).

**Next (owner)**: `! uv run copernicusmarine login`, then `make physics MODE=<best> WINDAGE=<best>` and `make p1-score`.
