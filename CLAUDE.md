# CLAUDE.md — sargassum-forecast

You are building a sargassum beaching forecast for 8 Broward County, FL beaches, validated against
FIU Sargassum Watch citizen-science reports, with a physics (OpenDrift) layer, a calibrated LightGBM
hybrid, a crew-allocation backtest using Costa's exact knapsack, and a static daily API + web app.

`docs/SPEC.md` is authoritative. Read it before every phase. Never edit it without the owner's approval;
if reality contradicts it, write the conflict in `docs/WORKLOG.md` and stop at the next gate.

## Hard rules

1. **Git.** Work on a branch per phase (`phase-N-<slug>`) and open a PR. Never push to `main`,
   never force-push, never touch `nareshrajesh787/Costa` except through the reviewed `ForecastProvider` PR.
2. **Secrets.** Copernicus credentials and any API keys live in env vars / GitHub secrets only.
   Keep `.env.example` current. Never print a secret in logs or outputs.
3. **No fabricated numbers.** Every number in the README, model card, app or PR text must come from a
   committed file in `outputs/`, produced by a script. If a number is not in `outputs/`, it does not exist.
4. **Time discipline.** Splits are by season only: train 2019–2023, validate 2024, test 2025–2026.
   Never shuffle. Never read `data/test_lock/` or score on 2025–2026 before Gate 4 is approved.
   Every feature carries an `available_at` timestamp and a test asserts `available_at <= issue_time`.
5. **Labels are frozen.** Severity rules (0 none, 1 present, 2 brown water or smell, 3 very brown;
   event = 2+) are defined in SPEC.md. Do not tune them to improve scores.
6. **Reproducibility.** Seed everything. Pin dependencies (`uv lock` or `pip-tools`). `make results`
   rebuilds every results table and figure from cached raw data in one command.
7. **Money.** Spend cap is $0 recurring. Before any call that could cost money (paid API, paid hosting,
   vision-model labeling), stop and ask. Respect Open-Meteo's non-commercial limits (<10,000 calls/day).
8. **Data courtesy.** Credit NOAA/AOML, USF, FIU, Copernicus Marine and Open-Meteo wherever data
   is shown. Do not republish FIU photos or raw reports; publish derived daily labels only if FIU agreed
   (see `docs/DATA_SOURCES.md`).
9. **Honest results.** Report every model against B0 (persistence) and B1 (climatology) with
   weekly block-bootstrap 95% CIs. A difference counts only if its CI excludes zero. Negative results
   go in the README as prominently as positive ones.
10. **Work log.** Append to `docs/WORKLOG.md` at the end of every session: what was done, what failed,
    what is unverified, next step.

## Commands

- `make data` — pull and cache raw inputs (idempotent, resumable)
- `make labels features` — build site-day labels and the feature store
- `make results` — train, evaluate, write `outputs/results_*.csv` and figures
- `make backtest` — decision backtest
- `make test` — pytest + ruff + mypy (the Stop hook runs this)

## Subagents

- `data-verifier`: re-pulls a small live sample from each source and diffs it against the cache.
- `leakage-cop`: audits feature timestamps, splits and any use of reanalysis in place of forecasts.
- `honesty-cop`: checks every claim and number in README, model card and app copy against `outputs/`.

Run `leakage-cop` before Gate 4 and `honesty-cop` before Gates 4, 5 and 7.

## Gates

Stop at each gate (G1–G5 and release) with a summary of at most 15 lines: what was built, the key numbers
(with file paths), what is unverified, and the one decision needed. Do not start the next phase until the
owner replies.
