# sargassum-forecast — see CLAUDE.md for what each target means.
.PHONY: physics physics-best p1-score tides data labels features results backtest test lint typecheck sir fiu afai openmeteo spike

UV ?= uv

data: fiu sir afai openmeteo tides ## pull and cache raw inputs (idempotent, resumable)

# AFAI: full Broward + upstream box (23–28N, 82–78W) at native 0.015°, Mar–Oct 2019–2026, 1D and 3D,
# plus the small 2025 boxes used by the Phase 1 spike (Cancún–Puerto Morelos, Progreso). ~11 min total.
afai:
	$(UV) run python -m pipeline.ingest.afai --dataset 1D --start 2019-03 --end 2026-10 --season-only
	$(UV) run python -m pipeline.ingest.afai --dataset 3D --start 2019-03 --end 2026-10 --season-only
	$(UV) run python -m pipeline.ingest.afai --dataset 1D --start 2025-01 --end 2025-12 --box 20.75 21.30 -87.10 -86.65
	$(UV) run python -m pipeline.ingest.afai --dataset 3D --start 2025-01 --end 2025-12 --box 20.75 21.30 -87.10 -86.65
	$(UV) run python -m pipeline.ingest.afai --dataset 1D --start 2025-06 --end 2025-06 --box 21.20 21.50 -89.90 -89.40

tides:
	$(UV) run python -m pipeline.ingest.tides

openmeteo:
	$(UV) run python -m pipeline.ingest.openmeteo --start 2022-01-01 --end 2026-10-31

fiu:
	$(UV) run python -m pipeline.ingest.fiu --manifest archive/fiu/manifest.csv

sir:
	$(UV) run python -m pipeline.ingest.sir_archive --days 7

labels:
	$(UV) run python -m pipeline.labels.fiu_labels

# Phase 1: rerun every SPEC spike number + feasibility measurements -> outputs/spike, outputs/feasibility
SPIKES = s01_afai_metadata s02_nearshore_puerto_morelos s03_progreso_control s04_afai_label_cancun \
         s05_fiu_api s06_label_base_rates s07_beach_persistence s08_offshore_vs_beach s09_openmeteo s10_sir \
         f01_afai_throughput f02_fiu_label_stats f03_copernicus_catalogue f04_openmeteo_coverage f05_sir_archive
spike: labels
	@for s in $(SPIKES); do echo "== $$s"; $(UV) run python -m spike.$$s || exit 1; done
	$(UV) run python -m spike.compare

# Phase 2: AFAI grid → Zarr + region stats (2019–2024 only; test seasons stay locked until G4), then the
# versioned feature store data/features/v<N>/ with an available_at column per feature group.
features: labels
	$(UV) run python -m pipeline.ingest.tides
	$(UV) run python -m pipeline.features.afai_grid
	$(UV) run python -m pipeline.features.build

# Every results table and figure from cached raw data (run time dominated by OpenDrift runs):
# labels → features → baselines (val) → P1 sweep + training seasons + score → hybrid (val) → frozen test
# scoring (only if the retrained model hash matches the frozen one, see eval/run_test.py) → gallery →
# backtests → API results file.
results: features physics-best
	$(UV) run python -m eval.run_val
	$(UV) run python -m physics.score
	$(UV) run python -m eval.run_hybrid
	$(UV) run python -m eval.run_test
	$(UV) run python -m eval.gallery
	$(MAKE) backtest
	$(UV) run python -m ops.intervals
	$(UV) run python -m ops.publish_results

# P1 with the frozen Phase 3 choice (no Stokes, 2 % windage; outputs/results_val_p1_meta.json)
physics-best:
	$(MAKE) physics MODE=no_stokes WINDAGE=0.02

backtest:
	$(UV) run python -m decision.backtest --preds data/interim/preds_val_hybrid.parquet --tag val2024
	$(UV) run python -m decision.backtest --preds data/test_lock/preds_test.parquet --tag test

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy .

test: ## pytest + ruff + mypy (the Stop hook runs this)
	$(UV) run pytest -m "not live"
	$(MAKE) lint
	$(MAKE) typecheck
	node --test --experimental-strip-types web/lib/knapsack.test.ts

# Phase 3 (needs Copernicus Marine credentials): validation sweep on 2024 (2 current modes × 4 windages per run),
# then the chosen configuration on the training seasons (set MODE/WINDAGE from outputs/p1_sweep_val.csv), then score.
MODE ?= total
WINDAGE ?= 0.02
physics:
	$(UV) run python -m physics.drift --season 2024 --modes total no_stokes
	for s in 2021 2022 2023; do $(UV) run python -m physics.drift --season $$s --modes $(MODE) --windages $(WINDAGE) || exit 1; done

p1-score:
	$(UV) run python -m physics.score
