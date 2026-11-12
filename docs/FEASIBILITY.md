# FEASIBILITY — Phase 1 data spike (Gate G1)

Run date: 2026-11-10. Branch `phase-1-data-spike` (stacked on `phase-0-scaffold`).
Every number below comes from a committed file in `outputs/spike/` or `outputs/feasibility/`, produced by
`make spike` (scripts in `spike/`). File names are given next to each block. Raw data stays under `data/` (never committed).

## Go / no-go per source

| Source | Verdict | One-line reason | Evidence |
| --- | --- | --- | --- |
| FIU Sargassum Watch (labels) | **GO** (with caveats) | 8 sites, 2019–2026, 11,678 labeled site-days. 2019 used a different form, and 2019–2021 are sparse | `feasibility/fiu_*.{csv,json}`, `spike/s05`, `s06` |
| AOML/USF AFAI 1D + 3D (ERDDAP) | **GO** | Full box at native 0.015°, all 8 seasons, both products pulled in 294 s + 340 s. No coarsening needed | `feasibility/afai_throughput.{json,csv}`, `spike/s01` |
| Copernicus Marine SMOC | **GO for forecast + 2021+ archive (catalogue only); data access UNVERIFIED** | Catalogue: SMOC hourly 2020-11-01 → present + forecast. No credentials yet, so no data was pulled | `feasibility/copernicus_catalogue.{csv,json}` |
| Copernicus reanalysis for 2019–2020 | **PARTIAL** | Same 1/12° grid (GLORYS12V1) but daily means only, no tides, no Stokes drift | same |
| Open-Meteo marine (currents, waves) | **GO, coarse** | 2022–2026 complete once queried 2.5 km offshore. The snapped sea cells are 3.6–8.5 km (currents) and 9.0–22.8 km (waves) from the sites, so the 8 sites share 4 / 3 cells | `feasibility/openmeteo_coverage.{csv,json}`, `spike/s09` |
| Open-Meteo winds | **GO**, with a leakage caveat | Historical-forecast winds are complete for 2022–2026. *Lead-specific* archived forecasts exist only from 2024-01-19 | same |
| NOAA/USF SIR | **GO** (Phase 0) | History exists from 2025-07-01 (the SPEC says none). Archiver + local back-fill working | `spike/s10`, `feasibility/sir_archive.json` |

## 1. FIU Sargassum Watch → site-day labels

**Adapter** `pipeline/ingest/fiu.py`: pages the public export API (1,000 per page) into `data/raw/fiu/<fetch_utc>/`.
It is resumable and honours HTTP 429 / `Retry-After`. The API rate-limits bursts (the first unpaced pull got 429 on page 6),
so pages are paced. **Labels** `pipeline/labels/fiu_labels.py` (rules frozen; tested in `tests/test_labels.py`).

- Coverage: 14,298 public entries, 2019-03-03 → 2026-11-09 (`spike/s05_fiu_api.json`).
  11,813 reports were assigned to the 8 sites. The 2,485 unassigned reports are mostly other beaches: Key Biscayne 516, Playa del Carmen 148, …
- Site assignment: the name alias matches one site and GPS is missing or ≤ 2 km away, or there is no alias match and GPS is ≤ 0.3 km
  from a site. Site coordinates = median report GPS (`pipeline/sites.py`).
- Dates: the "Date of Observation" field is **DD/MM/YYYY**. 5 assigned reports with typo dates (e.g. a 2018 date on a
  June-2021 entry) are dropped (`feasibility/fiu_label_summary.json`).
- Latency: upload lag (upload day − observation day) for assigned reports: median 0, p90 0, p99 4 days (same file).
  Site-day `available_at` = the latest upload among that day's reports.
- **Severity precedence (clarification, not tuning).** The SPEC table does not say whether "No Sargassum Present" plus
  brown water is 0 or 2/3. `none_first` reproduces the spike's counts (None 203 = 203; see §5), so it is frozen.

Per season (Mar–Oct; `outputs/feasibility/fiu_season_stats.csv`; per site in `fiu_site_season_stats.csv`):

| Season | Labeled site-days | Missing-day rate | None | Present | Moderate | Heavy | Event (≥2) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2019 | 696 | 0.645 | 0.000 | 0.869 | 0.131 | 0.000 | 0.131 |
| 2020 | 719 | 0.633 | 0.046 | 0.828 | 0.110 | 0.017 | 0.127 |
| 2021 | 1,135 | 0.421 | 0.041 | 0.881 | 0.075 | 0.003 | 0.078 |
| 2022 | 1,716 | 0.125 | 0.066 | 0.728 | 0.181 | 0.025 | 0.206 |
| 2023 | 1,816 | 0.074 | 0.164 | 0.712 | 0.118 | 0.006 | 0.124 |
| 2024 (val) | 1,819 | 0.072 | 0.107 | 0.801 | 0.090 | 0.003 | 0.092 |
| 2025 (test) | 1,874 | 0.044 | 0.078 | 0.724 | 0.162 | 0.036 | 0.198 |
| 2026 (test) | 1,903 | 0.029 | 0.030 | 0.611 | 0.258 | 0.101 | 0.359 |
| Pooled | 11,678 | 0.255 | 0.076 | 0.746 | 0.149 | 0.029 | 0.177 |

(Missing-day rate = 1 − labeled site-days / (8 × 245). The 102 site-days with reports but unknown severity count as missing.)

**Failure modes / findings**
1. **2019 used a different form.** The water-colour question is blank on almost every 2019 report, and "No Sargassum
   Present" never occurs in 2019. Under the frozen rules a 2019 day can reach severity 2 only through smell and never 3.
   2019 labels therefore measure something narrower than 2020+ labels. (`feasibility/fiu_label_summary.json` →
   `form_check_by_obs_year_assigned_reports`: 2019 water blank on 789 of 791 reports, 0 "No Sargassum Present", 0 "Very Brown";
   from 2020 on, water is blank on ≤ 6 reports per year.)
2. **Sparse early seasons:** 64% / 63% / 42% of site-days are missing in 2019 / 2020 / 2021, versus ≤ 12.5% from 2022.
3. **Validation season is atypical:** 2024 event rate 0.092 (heavy 0.003) versus 0.198 / 0.359 in the test seasons. Persistence is
   much weaker in 2024: P(event | event yesterday) = 0.126 vs base 0.092, against 0.352 vs 0.140 in 2019–2023
   (`spike/s07_beach_persistence.json`, `non_test_seasons`). Isotonic calibration fit on 2024 will under-forecast
   record years. This is a Phase 4 risk, noted now.
4. Messy site names (typos, generic names). This is handled by aliases + GPS and covered by tests.

## 2. AFAI (ERDDAP griddap, netCDF)

**Adapter** `pipeline/ingest/afai.py`: month-by-month netCDF into `data/raw/afai/<dataset>/<box>/YYYY-MM.nc`. It is
idempotent and logs every request to `_throughput.csv`.

- Metadata (`spike/s01_afai_metadata.json`): 2016-06-18 → 2026-11-09, 1-day latency, 3,545 daily steps (0.934 of
  calendar days have a step), 0.015° grid over 0–38°N, 98–38°W. 1D and 3D have identical grids.
- **Throughput (measured, not extrapolated)** (`feasibility/afai_throughput.json`). Full box 23–28°N, 82–78°W (89,178 pixels/day),
  native 0.015°, Mar–Oct 2019–2026 = 64 monthly requests per product:

  | Product | Values | Wall time | Values/s (overall; month min–max) | Raw netCDF |
  | --- | --- | --- | --- | --- |
  | 1D | 173.5 M | 293.8 s | 590,674 (282,312 – 1,148,027) | 694.7 MB |
  | 3D | 173.5 M | 340.4 s | 509,774 (201,128 – 850,200) | 694.7 MB |

  The SPEC planned around ~30K values/min (CSV). netCDF is roughly 1,000× faster. **Plan: full box, native resolution, no
  coarsening.** The whole history for both products takes about 11 minutes, far inside the 12-hour budget. Phase 2 converts to compressed Zarr.
- Missing days in season (calendar days with no time step): 0 for 2019–2021 and 2023; 1 for 2022; 4 for 2024; 9 for 2025; 1 for 2026
  (same file, `per_season`; counted from the cached files after trimming, see below).
- Licence (verbatim, ERDDAP `license` attribute): "The data may be used and redistributed for free but is not intended for
  legal use, since it may contain inaccuracies. Neither the data Contributor, ERD, NOAA, nor the United States Government,
  nor any of their employees or contractors, makes any warranty, express or implied, including warranties of
  merchantability and fitness for a particular purpose, or assumes any legal liability for the accuracy, completeness, or
  usefulness, of this information." (`spike/s01_afai_metadata.json` notes)

**Failure modes:** ERDDAP snaps request bounds to the *nearest* existing time step, so a month whose last day is missing
returns the next month's first day. 2024-07-01 appeared in both `2024-06.nc` and `2024-07.nc`. The adapter now trims every
file to its requested window (`afai.trim`; `out_of_window_steps_trimmed` = 1 per product in `afai_throughput.json`).
Small boxes are latency-bound (~5 s per request whatever the size), so fetch by month, not by day. AFAI is NaN
for cloud, glint and land alike: there is no separate land flag, so `pipeline/geo.py` (Natural Earth 10 m) supplies distance-to-coast.
Pixels within ~1.5 km of the coast are almost never valid (`spike/s02` → `valid_share_by_coast_distance_june2025_box`: 0.086
for 0–1.5 km vs 0.237 for 1.5–3 km and 0.412–0.459 for 3–15 km). The source sensor is not stated in the metadata, which keeps
the MODIS-end risk live.

## 3. Copernicus Marine (currents)

**Adapter** `pipeline/ingest/copernicus.py` (catalogue + `subset_smoc`). **No credentials are configured, so no data was
downloaded.** Forecast *access* and throughput are UNVERIFIED. Catalogue facts (`feasibility/copernicus_catalogue.{csv,json}`):

| Dataset | Time coverage | Step | Grid | Current variables |
| --- | --- | --- | --- | --- |
| `cmems_mod_glo_phy_anfc_merged-uv_PT1H-i` (SMOC) | 2020-11-01 → 2026-11-19 (≈ 9-day forecast) | 1 h | 1/12° | uo, vo, utide, vtide, vsdx, vsdy, utotal, vtotal |
| other ANFC current datasets (P1D, PT6H, PT1H-m) | 2022-06-01 → 2026-11-19/20 | 24 h / 6 h / 1 h | 1/12° | uo, vo |
| `cmems_mod_glo_phy_my_0.083deg_P1D-m` (GLORYS12V1) | 1993-01-01 → 2026-09-22 | 24 h | 1/12° | uo, vo |
| `cmems_mod_glo_wav_my_0.2deg_PT3H-i` (wave reanalysis) | 1980-01-01 → 2026-08-31 | 3 h | 0.2° | VSDX, VSDY (Stokes) |
| `cmems_obs-mob_glo_phy-cur_my_0.25deg_PT1H-i` (GlobCurrent) | 1993-01-01 → 2026-03-31 | 1 h | 0.25° | ue, ve, ugos, vgos |

**Answer to the open question.** Is a multi-year reanalysis available for 2019–2021 on the same grid? **Same grid: yes. Same product:
no.** GLORYS12V1 is on the same 1/12° grid, but only as daily means of uo/vo, with no tides and no Stokes drift (Stokes would come
from the 0.2° wave reanalysis). However, SMOC itself starts 2020-11-01, so **the 2021 season is covered by SMOC**. That
contradicts SPEC's "2-year rolling archive" and its fallback "physics features from 2022 only". So:
2021–2026 = SMOC hourly; 2019–2020 = GLORYS daily + wave-reanalysis Stokes (a different forcing, which must be flagged if used).

**Leakage-relevant:** the catalogue holds a best-analysis time series, not past forecast runs. For every historical season
the drift model can only be forced with *analysed* currents, i.e. a perfect-prognosis upper bound. (Licence: Copernicus Marine
Service licence, attribution required, free account. The licence text was not fetched in this spike.)

## 4. Open-Meteo (point currents, waves, winds), 8 sites, 2022-01-01 → 2026-10-31

**Adapter** `pipeline/ingest/openmeteo.py`. Pulls on 2026-11-10 (including the marine re-pull below): 240 requests,
≈ 6,051 weighted calls (estimate, under the 10,000/day limit), 320.6 s (`feasibility/openmeteo_coverage.json`). Per-feed coverage is in `feasibility/openmeteo_coverage.csv`:

- Currents (`meteofrance_currents`) and waves (`meteofrance_wave`): Mar–Oct non-null share 1.0 every season 2022–2026,
  except currents 0.9796 in 2024 and wave period 0.9964 in 2023. SST starts 2022-11-23.
- Winds (`gfs_seamless`, Historical Forecast API): complete 2022–2026. This series stitches the latest run for each hour, so it is a
  short-lead forecast close to an analysis, **not** a lead-L forecast.
- **Lead-specific archived winds** (Previous Runs API, `*_previous_dayN`): first non-null 2024-01-19 (day 1) … 2024-01-25 (day 7).
  Seasons 2022–2023 have 0% coverage, and 2024–2026 have 100%.
- Snapped grid cells: currents 3.6–8.5 km from the sites (4 distinct cells for the 8 sites); waves 9.0–22.8 km (3 cells);
  winds 1.2–3.6 km (7 cells).
- Spike check (`spike/s09_openmeteo.json`): live 10-day current forecast returned 240 hours, June-2022 currents and 2022 winds
  are 100% non-null.
- Terms: CC BY 4.0, non-commercial, < 10,000 calls/day.

**Failure modes:** with the beach coordinate itself, `cell_selection=sea` snapped Commercial Pier, Sea Ranch Lakes and
Atlantic Pier to a cell *west* of the shoreline (26.208°N, 80.125°W) that returned 100% nulls for waves. The adapter now queries
0.025° (~2.5 km) east of each beach and warns on any all-null chunk. Other failure modes: coarse marine cells (near-identical "per-site" marine features; waves come from cells 9–23 km away);
lead-specific winds are missing before 2024; Open-Meteo's own call weighting is approximated, not reported by the API.

## 5. Spike reruns (`outputs/spike/comparison.csv`)

55 metrics have a spike value and 12 differ by more than the tolerance (absolute 0.03 for proportions and AUCs, 3% relative
for counts). The flagged metrics:

| Script | Metric | Spike | Rerun | Why |
| --- | --- | --- | --- | --- |
| s02 | first ocean pixel valid days (first pixel off the coastline) | 3 | 0 | Definition. The pixel 0.6 km out is permanently masked. The first pixel ≥ 1.5 km out gives **3** (not flagged) |
| s02 | pixels 3–15 km valid days min / max | 9 / 14 | 10 / 13 | ±1 day. Single-row transect and coastline precision |
| s03 | Progreso positive pixels (AFAI > 0) | 0 | 40 (of 1,242 valid pixel-days) | "Positive" is undefined in the SPEC. The mean AFAI matches (−0.0017 vs −0.0018) |
| s04 | Cancún–PM agreement min / max | 0.50 / 0.66 | 0.544 / 0.981 | Label definition unrecorded. Balanced variants (1D, ≥ 25% / ≥ 50% positive) give 0.615 / 0.544, inside the spike range. The valid share matches (0.441 vs 0.44) |
| s04 | persistence BSS vs monthly clim min / max | −0.21 / −0.07 | −1.083 / −0.015 | Same definition gap. The conclusion holds: BSS < 0 in all 10 variants |
| s06 | unknown-severity reports among latest 3,775 | 0 | 5 | Blank condition with no elevating answer → NaN by rule |
| s08 | persistence AUC, lead 7 | 0.67 | 0.635 | Δ 0.035. Leads 1–5 match within 0.026 |
| s08 | n days | 215 | 231 | No "≥ N sites reported" rule gives 215 (N=7 → 231, N=8 → 175). The day filter is not recorded in the SPEC |
| s10 | earliest SIR KMZ | none | 2025-07-01 | **SPEC is wrong**: about 16 months of history is online (rolling window, presumably) |

Reproduced within tolerance: AFAI metadata (all 10 metrics); FIU entries 14,298; base-rate counts 203 / 2,509 / 797 / 261 vs
203 / 2,508 / 805 / 259 and event share 0.280; next-day agreement 0.704 (0.70); P(e|e) 0.475 (0.47); base rate 0.279 (0.28);
persistence AUC 0.762 / 0.730 / 0.726 / 0.637 at leads 1/2/3/5 (0.76 / 0.73 / 0.70 / 0.65); offshore-AFAI AUC 0.540 / 0.601 /
0.600 / 0.637 / 0.587 (0.52 / 0.58 / 0.58 / 0.62 / 0.57); Open-Meteo (3/3); SIR size and 404s.

**Rule tension, disclosed.** `s06`, `s07` and `s08` read 2025–2026 Broward labels (`"touches_test_seasons": true`).
KICKOFF Phase 1 and Gate G2 explicitly ask for these reproductions, but CLAUDE.md rule 4 says not to score on 2025–2026 before G4.
They compute only the pre-registered spike metrics with fixed rules (nothing fitted, tuned or selected), and the same metrics for
2019–2024 are stored alongside. `data/test_lock/` was not created or read.

## 6. SPEC conflicts found (also in WORKLOG)

1. SIR history exists from 2025-07-01 (SPEC: none). The local back-fill (`data/raw/sir/`, `feasibility/sir_archive.json`) covers
   2025-06-28 → 2026-11-09: all 3 files on 494 of 500 days, 12.47 MB/day on average, ≈ 4.55 GB per 365 days, 6.2 GB in total.
   This supersedes the Phase 0 WORKLOG estimate (7.4 MB/day, measured on one November day).
2. SMOC archive starts 2020-11-01 (SPEC: 2-year rolling, physics from 2022). 2021 can have SMOC physics.
3. Copernicus keeps no past forecast runs, and lead-specific winds start 2024-01-19. "Archived forecasts rather than
   reanalysis wherever possible" therefore means: currents = analysis for every historical season; winds = lead-L forecasts
   only for 2024–2026.
4. 2019 labels come from a form without the water-colour question (frozen rules, different instrument).
5. ERDDAP throughput is about 1,000× the SPEC estimate. No coarsening is needed.
6. `SPEC.md` lived at the repo root; it was moved to `docs/SPEC.md` (content unchanged) in Phase 0.

## 7. Decision needed at G1

**Driver policy for historical seasons.** Recommended: *perfect-prognosis* training and evaluation. Use analysed SMOC currents
(2021+) and historical-forecast winds for every season, label P1/M1 historical skill as an upper bound with respect to
driver error, and on 2024 (validation) measure how much skill drops when the winds are swapped for true lead-L
`previous_dayN` forecasts. The 2027 live season is the real-forecast check. The alternative is forecast-only drivers:
lead-L winds exist only for 2024+, and currents have no forecast archive at all, so P1 could not be scored leakage-free
before 2027.

Secondary choices, each with a default the agent will follow unless told otherwise:
(a) 2019 labels: keep them in the store, flag them `form_2019`, and train on 2020–2023 by default, reporting 2019-included as a sensitivity run;
(b) 2019–2020 physics: none (P1 from 2021), since GLORYS daily forcing is a different physics.

Owner actions (not decisions): merge PR #1; add Copernicus credentials (env + GitHub secrets) so forecast access can be
verified; confirm the FIU courtesy email was sent; after merge, dispatch `sir-archive` with a long look-back to preserve the
2025-07+ SIR history as release assets.
