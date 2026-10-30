.PHONY: setup data data-store data-argo data-collocate data-coverage data-patches data-demo train eval eval-phase4 serve ui-data test lint typecheck audit reproduce clean

# ── Setup ────────────────────────────────────────────────────────────────────
setup:
	pip install -e ".[dev]"
	pre-commit install

# ── Data pipeline (real, open data; see docs/DATA_CARD.md) ──────────────────
# ~4 GB of downloads on first run, cached under data/cache afterwards.
data: data-store data-argo data-collocate data-coverage data-patches

data-store:
	python -m aquasphere.data.satellite_fetch --start 2015-01-01 --end 2025-12-31

data-argo:
	python -m aquasphere.data.argo_ingest --start 2015-01-01 --end 2025-12-31

data-collocate:
	python -m aquasphere.data.collocate_nio

data-coverage:
	python -m aquasphere.data.coverage

# 9x9 patch stacks at lags t, t-7, t-14, t-28 for Tier B/C, plus unlabelled training-year patches
data-patches:
	python -m aquasphere.data.patches --ssl

# Synthetic demo store (13 dates) for offline UI demos only. Never train or evaluate on it.
data-demo:
	python -m aquasphere.data.satellite

# ── Training (Phase 4) ───────────────────────────────────────────────────────
train:
	python -m aquasphere.train.train --config configs/model_a.yaml

# ── Evaluation (Phase 4+) ────────────────────────────────────────────────────
eval:
	python -m aquasphere.eval.report_v2

# The 2024-25 test period is locked (aquasphere.eval.protocol) until the one final evaluation in
# roadmap Phase 6, which adds its own target. Nothing before that may read it.
eval-test:
	@echo "Test period locked until the final evaluation (roadmap Phase 6)." && exit 1

# Phase 4: physics ablation, E3-E7 on validation 2023, and the served Tier A v2 checkpoint
eval-phase4:
	python -m aquasphere.eval.report_phase4

ablate:
	python -m aquasphere.eval.ablation --fixture data/processed/argo_profiles.parquet --epochs 4

leakage:
	python -m aquasphere.eval.leakage

# ── Serve ────────────────────────────────────────────────────────────────────
serve:
	uvicorn aquasphere.serve.app:app --reload --port 8000

ui-data:
	python -c "import shutil, pathlib; (pathlib.Path('web/data')).mkdir(parents=True, exist_ok=True); [shutil.copy(f'docs/results/{n}.json', f'web/data/{n}.json') for n in ('metrics', 'metrics_v2', 'ablation', 'e1_leakage', 'e1_leakage_v2', 'phase4', 'data_coverage') if pathlib.Path(f'docs/results/{n}.json').exists()]"
	python scripts/build_web_data.py

# ── Tests ────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -q

test-unit:
	pytest tests/unit -q

test-api:
	pytest tests/api -q

test-data:
	pytest tests/data -q

# ── Lint & type-check ────────────────────────────────────────────────────────
lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

typecheck:
	mypy src/aquasphere/data src/aquasphere/models src/aquasphere/eval

audit:
	pip-audit

# ── Full reproduce (from clean state — used in CI and for submission) ─────────
reproduce:
	@echo "=== AquaSphere full reproduce run ==="
	$(MAKE) data
	$(MAKE) eval
	$(MAKE) eval-phase4
	$(MAKE) ui-data
	@echo "=== Done. Check docs/results/metrics_v2.json and phase4.json ==="

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
