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
