# sargassum-forecast — see CLAUDE.md for what each target means.
.PHONY: data labels features results backtest test lint typecheck sir fiu afai openmeteo spike

UV ?= uv

data: fiu sir afai openmeteo ## pull and cache raw inputs (idempotent, resumable)

# AFAI: full Broward + upstream box (23–28N, 82–78W) at native 0.015°, Mar–Oct 2019–2026, 1D and 3D,
# plus the small 2025 boxes used by the Phase 1 spike (Cancún–Puerto Morelos, Progreso). ~11 min total.
afai:
	$(UV) run python -m pipeline.ingest.afai --dataset 1D --start 2019-03 --end 2026-10 --season-only
	$(UV) run python -m pipeline.ingest.afai --dataset 3D --start 2019-03 --end 2026-10 --season-only
	$(UV) run python -m pipeline.ingest.afai --dataset 1D --start 2025-01 --end 2025-12 --box 20.75 21.30 -87.10 -86.65
	$(UV) run python -m pipeline.ingest.afai --dataset 3D --start 2025-01 --end 2025-12 --box 20.75 21.30 -87.10 -86.65
	$(UV) run python -m pipeline.ingest.afai --dataset 1D --start 2025-06 --end 2025-06 --box 21.20 21.50 -89.90 -89.40

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

features:
	@echo "features: implemented in Phase 2 (pipeline/features)"; exit 1

results:
	@echo "results: implemented in Phase 2 (make results)"; exit 1

backtest:
	@echo "backtest: implemented in Phase 5 (decision/backtest.py)"; exit 1

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy .

test: ## pytest + ruff + mypy (the Stop hook runs this)
	$(UV) run pytest -m "not live"
	$(MAKE) lint
	$(MAKE) typecheck
