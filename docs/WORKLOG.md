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
