# Sargassum Forecasting System — Audit, Spec & Build Plan

Nov 10, 2026 · @Naresh

## Bottom line

The core idea survives: predict sargassum at the beach, then use Costa's exact knapsack to plan crews, and prove the forecast helps with a backtest. Live-data tests changed four things. Each change makes the project more credible, not smaller.

1. **Validate against real beach observations in Southeast Florida.** FIU's public Sargassum Watch dataset has about daily reports from 8 fixed Broward County beaches from 2019 to 2026 (14,298 entries; the API works without a key). That replaces "satellite near-shore coverage as ground truth," which my tests showed is too noisy to be a label. Costa stays site-agnostic, so Fajardo still runs in forecast-only mode.
2. **Add a physics baseline and make the ML a hybrid on top of it.** Satellite pixels just offshore barely predict the beach (AUC 0.52 to 0.62). Yesterday's beach report does better (AUC 0.76 at 1 day). Skill above that has to come from transport: drifting detected sargassum with forecast currents plus wind drag. Operational systems at Météo-France, CLS and NOAA already work this way.
3. **Cut horizons to 1, 2, 3, 5 and 7 days. Make the deep model a stretch goal.** The 14-day horizon and a headline ConvLSTM are not supported by eight beaches and about five seasons of driver data.
4. **Build for sensor change and start the live track record now.** NASA plans to stop MODIS data collection in 2027. Ingest goes through an adapter, and a daily job freezes every forecast so the 2027 season (March to October) becomes a true out-of-sample test.

What makes it impressive: a forecast scored against real beach observations, a physics-versus-ML ablation, calibrated probabilities, a decision backtest, and a live public track record. Most student forecasting projects have none of these.

Your time: about 5 hours over 4 weeks, mostly 20-minute reviews at five gates. Agents build everything else.

## Audit of the original plan

Five items hold as written. One is a blocker (the ground truth), and the rest need fixing, cutting or moving.

| Original plan item | Verdict | What I found | Change |
| --- | --- | --- | --- |
| Ground truth = "AFAI-derived near-shore coverage" fallback | Blocker | Daily near-shore AFAI labels agree with the next observed day only 50–66% of the time (Cancún–Puerto Morelos, 2025). Persistence scores worse than monthly climatology. | Use FIU Broward beach observations as truth. AFAI becomes an input. |
| Target site "unknown" | Resolved | Costa defaults to Fajardo, PR, but its six zones are a schematic template with x/y map positions, not geocoded beaches. | Validate in Broward. Run Fajardo and any coordinates in forecast-only mode. |
| Live drivers "HYCOM or Copernicus, GFS" | Fix | HYCOM's GOFS 3.1 analysis ended Sept 2024; its successor (ESPC-D-V02) starts Aug 2024, so the record switches models mid-way. Open-Meteo serves Copernicus currents from Jan 2022 plus a 10-day forecast, with no key. | Copernicus Marine (gridded, for drift) and Open-Meteo (point features). |
| AFAI on ERDDAP as the training signal | Holds, with a risk | Daily product from 2016-06-18 to yesterday, 0.015° grid, free to use and redistribute. MODIS collection ends in 2027 and the source sensor is not stated. | Sensor-agnostic ingest. Daily staleness alarm. |
| SIR as an outside comparison | Fix | Today's SIR KMZ downloads (1.56 MB). Dated KMZ files for June 2022–2025 return 404, so there is no history at that path. CC0 licensing was not confirmed. | Archive SIR daily from day 1. Also reimplement the published SIR method as a baseline. |
| "About 70% accuracy within three days" (prior work) | Fix | Bernard et al. 2022 report 73.3% accuracy for beaching within 7 days (HYCOM), and 70.1% on a 2021 test year with a ±3-day window. | Cite it correctly. Compare with Brier and AUC, not accuracy. |
| 14-day horizon | Cut | Beach persistence AUC falls from 0.76 (1 day) to 0.65–0.67 (5–7 days). Multi-week outlooks are a separate seasonal problem. | Horizons 1, 2, 3, 5, 7 days. |
| M3 ConvLSTM as the "AI headline" | Demote | About 10K labeled site-days with drivers cannot support a deep beach model. Gridded AFAI could support a nowcast model. | Stretch goal: AFAI field nowcast used as a feature. |
| M2 LightGBM per lead | Holds | Right tool for about 10K tabular rows. | Keep, and add physics features. |
| Time-based splits, seeds, committed outputs | Holds |  | Keep, and add block-bootstrap confidence intervals. |
| Three-policy allocation backtest | Holds | Weak spot: "reactive" uses yesterday, so a 1-day forecast barely differs. | Add a scheduling lead: crews are booked 2 days ahead. |
| PR into Costa, teammates review | Holds |  | Keep. Costa reads `forecastRisk` from the new API through an adapter. |
| "Upgrade later" (Clarity, PeerPoint and others) | Out of scope | It belongs to the portfolio audit, not this build. | Removed from this plan. |

## Feasibility tests run on live data

Every data source the plan depends on answered a real request, and the system is buildable. The tests also showed where skill will and will not come from. I queried AOML's ERDDAP, the FIU Epicollect API, Open-Meteo and the SIR site directly on Nov 10, 2026.

| Test | Result | What it means |
| --- | --- | --- |
| AFAI 1-day product metadata | 2016-06-18 to 2026-11-09 (about 1-day latency); 3,545 daily steps; 0.015° grid over 0–38°N, 98–38°W | Ten years of history, and live use works |
| Near-shore data availability, Puerto Morelos, June 2025 | First ocean pixel valid on 3 of 30 days; pixels 3–15 km out valid on 9–14 of 30 days (clouds) | Pixels within about 1.5 km of shore are masked. Use a 1.5–10 km band. |
| Artifact check at a control coast (Progreso, Gulf side), June 2025 | No positive pixels; mean AFAI about −0.0018 | The positive near-shore signal at Puerto Morelos is real sargassum, not a coastal artifact |
| AFAI as a label, Cancún–Puerto Morelos band, all of 2025 | 44% of band pixels valid per day on average; consecutive observed days agree 50–66%; persistence Brier skill vs monthly climatology −0.07 to −0.21 | Too noisy to be ground truth. 3-day composites help only at a 1-day lead. |
| FIU Sargassum Watch API | 14,298 public entries. 8 fixed Broward sites reported about daily, March–October, 2019–2026. Fields: GPS, presence, freshness, water color, smell, wind, up to 4 photos | A beach-level ground truth that overlaps the AFAI record |
| Broward label base rates (latest 3,775 site reports) | None 203; present 2,508; moderate (brown water or smell) 805; heavy (very brown) 259. Event (moderate or worse) = 28% | A forecastable target: not rare, not constant |
| Beach persistence, Broward 2025–2026 seasons | Same-site next-day agreement 0.70; P(event \| event yesterday) = 0.47 vs 0.28 base rate | A strong baseline to beat |
| Can satellite pixels just offshore predict the beach? 2025, 215 days, event = 3+ of 8 sites | Beach persistence AUC 0.76 / 0.73 / 0.70 / 0.65 / 0.67 at 1 / 2 / 3 / 5 / 7 days. AFAI 3–8 km offshore: 0.52 / 0.58 / 0.58 / 0.62 / 0.57 | Offshore pixels alone are weak. Their best lead is about 5 days, which points to transport. Hence the physics layer. |
| Open-Meteo currents and winds at Broward | 10-day current forecast returned; currents for June 2022 returned; archived wind forecasts for 2022 returned; no key | Training and live drivers come from one source, from 2022 on |
| SIR archive | Today's KMZ: 1.56 MB. KMZ for June 15 of 2022–2025: HTTP 404 | Start archiving now. Reimplement the method for history. |

These are spike numbers from one season, with in-sample conditional rates and coarse labels. They show direction, not results. Agent A1 reruns them as committed, versioned scripts in Phase 1.

## Revised system design

The system is a daily pipeline: four free data feeds go in, and calibrated beach-level probabilities come out. Those feed a static API, a crew planner and Costa. The physics layer is the main addition to your plan.

&#91;embedded content: system architecture · 4 inputs, 1 daily pipeline, 3 model layers, 3 outputs\]

The baselines and the physics model each work alone, so the ablations can show what each layer adds. Only M2's output reaches users.

## Data spec

All inputs are free. One needs an account (Copernicus Marine). One needs a courtesy email before use (FIU). Every source sits behind an adapter with a cached, versioned output.

| Role | Source and ID | Coverage | Access | License / terms | Status |
| --- | --- | --- | --- | --- | --- |
| Ground truth | [FIU Sargassum Watch (Epicollect5)](https://five.epicollect.net/project/sargassum-watch), API `/api/export/entries/sargassum-watch` | 2019–2026, Mar–Oct; 8 Broward sites about daily, plus scattered FL/Caribbean | Public JSON API, 1,000 per page | FIU's lab asks users of its Epicollect data to email Dr. Lowell Iporac (stated on its EZ Sargassum project); no explicit license | Tested |
| Satellite sargassum | [AOML ERDDAP `noaa_aoml_atlantic_oceanwatch_AFAI_1D`](https://cwcgom.aoml.noaa.gov/erddap/info/noaa_aoml_atlantic_oceanwatch_AFAI_1D/index.html) (also `_3D`, `_7D`) | 2016-06-18 to present, 0.015°, daily | griddap / OPeNDAP, no key | Free use and redistribution; "not intended for legal use" | Tested |
| Currents (gridded, drift model) | Copernicus Marine `GLOBAL_ANALYSISFORECAST_PHY_001_024`; hourly merged surface currents (SMOC: tides + Stokes drift) | 1/12°; 10-day forecast daily; 2-year rolling archive | `copernicusmarine` toolbox, free account | Copernicus Marine licence (attribution) | Documented, not yet pulled |
| Currents, waves, SST (point features) | [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api) (Météo-France SMOC, MFWAM) | Currents from Jan 2022; waves from Oct 2021; 10-day forecast | No key | Non-commercial, under 10,000 calls/day, CC BY 4.0 | Tested |
| Winds | [Open-Meteo Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api) and Forecast API; ERA5 archive for older seasons | Archived forecasts from about 2021–2022; live up to 16 days | No key | Same as above | Tested |
| Tides | NOAA CO-OPS (Costa already calls it) | Predictions | No key | Public domain | In Costa |
| Outside benchmark | [NOAA/USF SIR v1.5](https://cwcgom.aoml.noaa.gov/SIR/index.php), `KMZ/sargassum_risk_YYYYMMDD.kmz` | Daily; history not available as KMZ | Download daily from now on | Experimental; NOAA/USF credit required | Tested (today only) |
| Costa zones | `nareshrajesh787/Costa` `backend/app/data/zones.py` | 6 template zones | Repo | Shared project | Read |

**Older-season drivers.** The drift model needs gridded currents for 2019–2021. Copernicus' 2-year rolling archive does not reach that far. Phase 1 checks the Copernicus multi-year reanalysis. Fallback: physics features only from 2022, persistence and satellite features for all seasons.

**Volume.** The AFAI box for Broward plus its upstream (23–28°N, 82–78°W) is about 89,000 pixels a day. ERDDAP was slow in testing (about 30K values a minute as CSV). Pull netCDF month by month, coarsen to 0.03° outside the coastal band, and cache to Zarr. Phase 1 measures real throughput before committing to the full history.

## Targets, labels and model suite

The target is the probability that each Broward beach has a moderate-or-worse sargassum day at a lead of 1, 2, 3, 5 or 7 days. Every model outputs that same number, so they all share one evaluation.

**Labels (per site-day, from FIU reports).** Same-day duplicates are merged by taking the worst report.

| Severity | Rule | Share of recent reports |
| --- | --- | --- |
| 0 None | Condition = "No Sargassum Present" | 5% |
| 1 Present | Sargassum present, water unchanged, no smell | 66% |
| 2 Moderate | Water "slightly brown" or site smells | 21% |
| 3 Heavy | Water "very brown" | 7% |

Primary event: severity 2 or higher. Secondary event: severity 3 (heavy), reported but not tuned on. Missing days stay missing and are never filled as zero. The thresholds are frozen before any model is trained and written into the spec.

**Stretch: photo-graded labels.** Each report has up to 4 photos. A vision model grades beach coverage on a 0–3 scale. You hand-check 200 of its grades, and the measured agreement is published. This turns citizen photos into a sharper label, and is only done if FIU agrees and the spend cap allows.

**Model suite.** B = baseline, P = physics, M = machine learning.

| ID | Model | Inputs | Why it is there |
| --- | --- | --- | --- |
| B0 | Persistence | The site's latest report, up to 3 days old | The floor. AUC 0.76 at 1 day in the spike. |
| B1 | Climatology | Site × day-of-season rate, smoothed, training years only | The second floor |
| B2 | SIR-style index | Reimplemented from Trinanes et al.: AFAI anomaly within 50 km of the coast | Stand-in for NOAA's product over the past |
| B3 | SIR-style index + onshore wind | B2 plus the forecast onshore wind component | A published finding says adding wind improves SIR's match with beach reports |
| P1 | Lagrangian drift | Particles seeded from AFAI detections, moved by SMOC currents plus windage with OpenDrift; arrivals counted within 5 km of each site, per lead | The transport signal the spike says is missing |
| M1 | LightGBM hybrid | B0–B3 and P1 outputs, upstream AFAI, winds, waves, tide phase, season; lead as a feature | Expected best model |
| M2 | Calibrated M1 | Isotonic calibration fit on the validation season | So that "40%" means about 40% |
| M3 (stretch) | AFAI nowcast U-Net | Gridded AFAI, currents, wind | Gap-fills clouds; adds a feature to M1. Kept only if it improves M1 on validation. |

**Physics details.** Windage is swept from 0% to 3% of wind speed on the validation season only. Published estimates put the total wind effect near 3%, with pure windage near 2% and about a 10° deflection (Podlejski et al. 2023). Using SMOC, which already contains Stokes drift, risks double-counting the wave effect, so the sweep tests both. Particles that hit land are stranded and counted. The run takes minutes on a small domain, so it fits in the daily GitHub Action.

## Evaluation and decision backtest

The main claim is a skill number with a confidence interval, measured on seasons no model saw and then confirmed live in 2027. Everything else supports that claim.

**Splits (by season, never shuffled).**

| Split | Seasons (Mar–Oct) | Use |
| --- | --- | --- |
| Train | 2019–2023 (physics features from 2022 unless reanalysis is confirmed) | Fit models |
| Validation | 2024 | Tune windage, hyperparameters, calibration |
| Test | 2025–2026 | Touched once, after the Gate 4 freeze. Both are record years, so report them separately. |
| Live | 2027 onward | Forecasts frozen daily before observations arrive, scored automatically |

**Metrics.** Brier score and Brier skill versus B0 and B1. ROC-AUC and PR-AUC. Reliability diagram. Skill versus lead time. Each is reported per site, per season and pooled. Confidence intervals come from a weekly block bootstrap (1,000 resamples), because neighboring days are not independent. Model comparisons use paired bootstraps, and a difference only counts if its interval excludes zero.

**Ablations.** M1 without P1, without AFAI, and without wind. This answers "does the physics matter?" with a number, whichever way it comes out.

**Failure gallery.** The ten worst misses on test, each with an AFAI map, the drift particles, the winds and the beach report. Each gets a one-line cause: cloud gap, wind shift, local accumulation, or label noise.

**Leakage rules.** Features at issue time use only data available then: AFAI with its 1-day latency, archived forecasts rather than reanalysis for drivers wherever possible, and beach reports up to the day before. A test checks every feature's timestamp against the issue time.

**Decision backtest (simulated, labeled as such).**

- Zones: the 8 Broward sites. Each has an editable crew-hour cost (default 2–4 h) and weight (default 1). The equity caveat from Costa's README carries over.
- Each day, a budget of B crew-hours (swept 4–16) is allocated by Costa's exact 0/1 knapsack. Crews are booked L days ahead (default 2), which is the real reason to forecast.
- Policies: **reactive** (where events were last reported), **climatology**, **forecast-aware** (M2 probability × weight), and **oracle** (perfect knowledge, the ceiling).
- Metrics: event site-days covered per crew-hour; share of the oracle's coverage captured; regret versus oracle. All with bootstrap intervals.
- The knapsack keeps its brute-force equality test. A property test also checks that more budget never lowers the value.

## Application, API and operations

The whole system can run for $0 a month: a daily GitHub Action computes forecasts and publishes static JSON, and a Vercel site reads it. No server stays up, so nothing breaks while you are at school.

**Daily job (`.github/workflows/daily.yml`, about 10:00 UTC).**

1. Pull yesterday's AFAI, the new SIR KMZ, the latest Copernicus and Open-Meteo forecasts, and new FIU reports.
2. Run P1 drift, then M2, for every site and lead.
3. Freeze today's forecast as `forecasts/YYYY-MM-DD.json` with a model version and input hashes. It is append-only and never edited.
4. Score any past forecast whose verifying observation has now arrived. Update `track_record.json`.
5. Publish static files to the site. Open a GitHub issue if any input is stale for more than 3 days (the MODIS-end alarm).

**Public API (static, versioned).**

| Endpoint | Returns |
| --- | --- |
| `/api/v1/forecast/latest.json` | Per site: lat, lon, and for each lead: probability, 80% interval, model version, issue time |
| `/api/v1/forecast/{date}.json` | The frozen forecast for that issue date |
| `/api/v1/track_record.json` | Live scores: Brier, BSS, AUC, reliability bins, n |
| `/api/v1/sites.json` | Site metadata, data sources, attribution |
| `/api/v1/point?lat=&lon=` (optional Vercel function) | Forecast-only for any coordinates, such as Costa's Fajardo, clearly marked unvalidated |

**Web app (Next.js on Vercel, MapLibre with OpenStreetMap tiles).**

- **Forecast map:** beaches colored by probability, a lead-time slider, a drift-particle overlay, and uncertainty shown as a band rather than one hard color.
- **Crew planner:** enter a budget and booking lead; the knapsack runs in the browser (TypeScript port, tested against the Python version) and explains each pick.
- **Track record:** live 2027 scores next to the test-season results, with a reliability plot. This is the page that earns trust.
- **Methods and model card:** data, splits, ablations, failure gallery, intended use, the not-a-warning-system disclaimer, and NOAA/USF/FIU/Copernicus/Open-Meteo attribution.
- Loading, empty and error states; keyboard navigation; works on a phone.

**Costa integration.** A pull request to Costa adds a `ForecastProvider` that fills each zone's `forecastRisk` from the nearest site, or from `/point`. It keeps Costa's "scenario vs live" labeling. Your teammates review it, and nothing merges without their sign-off.

## Agentic implementation plan

One Claude Code session runs each phase from `KICKOFF.md` and stops at each gate for a 20-minute review from you. Phases 5 and 6 run in parallel worktrees. Expected calendar time is about 4 weeks; your total time is about 5 hours.

| Phase | Days | What the agent builds | Gate: done when | Your time |
| --- | --- | --- | --- | --- |
| 0. Scaffold + archivers | 1 | Repo, CI, `CLAUDE.md` rules, Stop hook (tests + lint), SIR daily archiver, FIU snapshot job | CI green; the archiver commits today's SIR | 30 min: decisions below, create Copernicus account, send FIU email |
| 1. Data spike | 1–3 | Adapters for all sources; throughput test; reruns of every spike number as scripts; `FEASIBILITY.md` with go/no-go | **G1:** labels for 2019–2026 pulled; one AFAI season cached; drivers confirmed; reanalysis question answered | 20 min |
| 2. Dataset + baselines | 4–8 | Label builder, feature store (Parquet), B0–B3, metrics harness, one command `make results` | **G2:** results table regenerates from scratch; B0 reproduces the spike's persistence AUC (about 0.76 at 1 day, 2025, 3+ of 8 sites) | 20 min |
| 3. Physics | 8–13 | OpenDrift runner, seeding from AFAI, arrival index per site and lead, windage sweep (validation only) | **G3:** P1 scored on validation. If it does not beat B1 at any lead, the agent reports that and continues. | 20 min |
| 4. Hybrid ML + freeze | 12–16 | M1, M2, ablations, bootstrap intervals, failure gallery; then one test-set run | **G4:** test table committed and frozen; the honesty review passes | 30 min: read the results |
| 5. Decision layer | 14–17 | Knapsack ported with attribution; TypeScript port; backtest with booking lead | Backtest table committed; brute-force and property tests pass | (with G5) |
| 6. Ops + API + app | 16–24 | Daily workflow, static API, Next.js app, Costa `ForecastProvider` PR | **G5:** app live on Vercel and usable on a phone; one unattended daily run succeeded | 45 min: use the app, review the PR |
| 7. Docs + release | 24–28 | README with diagram and results, model card, `DATA_SOURCES.md`, license, attribution, demo GIF | A stranger can clone and run `make results` | 60 min: final read, record a 90-second demo |
| Stretch | After launch | S1 photo-graded labels · S2 AFAI nowcast U-Net · S3 second site (Quintana Roo, if the state shares its daily beach map archive) · S4 Puerto Rico via CARICOOS | Each is gated on beating validation | Optional |

**Agent setup (same pattern as your edgar-facts-mcp build).**

- `docs/SPEC.md`: this doc, exported as Markdown. It is authoritative, and agents never edit it without your approval.
- `CLAUDE.md`: the rules. Never push to `main`; no secrets in the repo; every number in docs comes from a committed output file; time-based splits only; seeds fixed; stop and report before any paid call; keep `WORKLOG.md` current; do not touch the test seasons before G4.
- `KICKOFF.md`: one prompt that runs the phases in order and stops at each gate with a short summary for you.
- Subagents: `data-verifier` (checks adapters against live sources), `leakage-cop` (audits feature timestamps and splits), `honesty-cop` (checks every claim in the README and app against outputs).
- Hooks: a Stop hook that runs `pytest` plus lint. Deny rules for `git push --force`, publishing commands, and writes to `data/test_lock/`.

**Repo layout.**

```
sargassum-forecast/
  pipeline/ingest/   afai.py  fiu.py  copernicus.py  openmeteo.py  sir_archive.py
  pipeline/labels/   pipeline/features/
  physics/           drift.py (OpenDrift)  arrivals.py
  models/            baselines.py  gbm.py  calibrate.py
  eval/              metrics.py  bootstrap.py  ablations.py  gallery.py
  decision/          knapsack.py (from Costa, attributed)  backtest.py
  web/               Next.js app + ts knapsack
  outputs/           committed results tables, figures, forecasts/, track_record.json
  docs/              SPEC.md  MODEL_CARD.md  DATA_SOURCES.md  FEASIBILITY.md  WORKLOG.md
  .github/workflows/ ci.yml  daily.yml  sir_archive.yml
  CLAUDE.md  KICKOFF.md  Makefile
```

## Risks and fallbacks

The biggest risk is that nothing beats persistence by a margin that survives the confidence interval. That is still a publishable, honest result, and the plan reports it either way.

| Risk | Likelihood | Fallback |
| --- | --- | --- |
| No model clearly beats B0 at 1–2 days | Medium | The headline becomes the lead where forecasting does add skill (the spike hints at about 5 days), plus the decision backtest with a 2-day booking lead |
| MODIS ends (NASA: Terra Feb 2027, Aqua Sept 2027), and AOML's AFAI feed changes or stops | Medium | Adapter interface; staleness alarm; switch to USF SaWS VIIRS/OLCI/PACE products; recalibrate the threshold on the overlap period |
| FIU declines or asks for limits | Low | Use only derived daily labels, never raw photos; credit FIU; if refused, drop to 2 seasons of SIR archive plus AFAI-band labels and say so |
| Copernicus reanalysis is not reachable for 2019–2021 | Medium | Physics features from 2022 only; earlier seasons train baselines |
| ERDDAP throughput too slow for the full box | Medium | Narrow the box to the upstream corridor; coarsen; pull in a one-time overnight job |
| Citizen labels are noisy or biased | High (inherent) | Severity rules frozen up front; per-site analysis; S1 photo audit measures label noise |
| Record years (2025–2026) in test only | Certain | Report the test seasons separately; the 2027 live season is the real check |

## Decisions (settled Nov 10, 2026)

| Decision | Choice |
| --- | --- |
| Validation site | Broward County, FL (8 FIU sites). Fajardo and any other coordinates run forecast-only, marked unvalidated. |
| Repo and license | `sargassum-forecast`, MIT for code. Data keeps each source's terms. |
| Spend cap | $0 recurring (static hosting). Up to $25 one-time for S1 photo grading, only after FIU agrees. |
| FIU email | You send the courtesy request from your own address before Phase 1 uses the labels. |
| Public contact email | nareshrajesh787@gmail.com (repo, model card, app footer) |

## Cold-email line (fill only from committed outputs)

> I built a sargassum beaching forecast for 8 Broward County beaches, validated against FIU's 2019–2026 citizen-science observations. It combines NOAA/USF satellite detections with a Lagrangian drift model and a calibrated gradient-boosting layer. On the held-out 2025–2026 seasons it reaches \[Brier skill, 95% CI\] over persistence at \[lead\] days, and a crew-scheduling backtest captures \[x%\] of oracle coverage versus \[y%\] for reactive planning. It has been forecasting live since \[date\]: \[link\].

Natural recipients: USF's Optical Oceanography Lab (which runs SaWS and is building a South Florida beaching forecast), FIU's Marine Macroalgae Research Lab, FAU, and NOAA AOML.

## Sources

- [AOML ERDDAP: 1-day USF AFAI metadata](https://cwcgom.aoml.noaa.gov/erddap/info/noaa_aoml_atlantic_oceanwatch_AFAI_1D/index.html) and [7-day](https://cwcgom.aoml.noaa.gov/erddap/info/noaa_aoml_atlantic_oceanwatch_AFAI_7D/index.html)
- [NOAA/USF Daily Sargassum Inundation Risk (SIR v1.5)](https://cwcgom.aoml.noaa.gov/SIR/index.php)
- [FIU Sargassum Watch, Epicollect5](https://five.epicollect.net/project/sargassum-watch) and [EZ Sargassum terms of use](https://five.epicollect.net/project/ez-sargassum)
- [NASA LAADS: MODIS to VIIRS transition](https://ladsweb.modaps.eosdis.nasa.gov/learn/modis-to-viirs-transition/)
- [NASA Earth Observatory: Sizing Up the Sargassum Belt (SaWS now uses MODIS, VIIRS and PACE OCI)](https://science.nasa.gov/earth/earth-observatory/sizing-up-the-sargassum-belt/)
- [HYCOM data server (GOFS 3.1 ended; ESPC-D-V02 from Aug 2024)](https://www.hycom.org/dataserver)
- [Copernicus Marine GLOBAL\_ANALYSISFORECAST\_PHY\_001\_024 user manual](https://documentation.marine.copernicus.eu/PUM/CMEMS-GLO-PUM-001-024.pdf)
- [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api) and [terms](https://open-meteo.com/en/terms)
- [Bernard et al. 2022, Ocean Science 18:915](https://os.copernicus.org/articles/18/915/2022/)
- [Trinanes et al. 2023, SIR method, J. Operational Oceanography](https://www.aoml.noaa.gov/monitoring-pelagic-sargassum-inundation-potential-for-coastal-communities-2023/)
- [Podlejski et al. 2023, windage from MODIS feature tracking](https://openpolar.no/Record/ftarchimer:oai:archimer.ifremer.fr:93349)
- [Marsh et al. 2022, review of sargassum forecasting methods (Frontiers)](https://www.frontiersin.org/articles/10.3389/fmars.2022.914501/full)
- [OpenDrift](https://opendrift.github.io/gallery)
- [Costa repository](https://github.com/nareshrajesh787/Costa)
