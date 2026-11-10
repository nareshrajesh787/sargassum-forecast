# sargassum-forecast — see CLAUDE.md for what each target means.
.PHONY: data labels features results backtest test lint typecheck sir fiu

UV ?= uv

data: fiu sir ## pull and cache raw inputs (idempotent, resumable)

fiu:
	$(UV) run python -m pipeline.ingest.fiu --manifest archive/fiu/manifest.csv

sir:
	$(UV) run python -m pipeline.ingest.sir_archive --days 7

labels:
	@echo "labels: implemented in Phase 1/2 (pipeline/labels)"; exit 1

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
