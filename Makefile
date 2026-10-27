.PHONY: setup data train eval serve ui-data test lint typecheck audit reproduce clean

# ── Setup ────────────────────────────────────────────────────────────────────
setup:
	pip install -e ".[dev]"
	pre-commit install

# ── Data pipeline (Phase 3) ──────────────────────────────────────────────────
data:
	python data/verify_sources.py
	python -m aquasphere.data.argo
	python -m aquasphere.data.satellite
	python -m aquasphere.data.collocate

# ── Training (Phase 4) ───────────────────────────────────────────────────────
train:
	python -m aquasphere.train.train --config configs/model_a.yaml

# ── Evaluation (Phase 4+) ────────────────────────────────────────────────────
eval:
	python -m aquasphere.eval.report --split val

# Run once on the held-out test year — only when model is frozen
eval-test:
	python -m aquasphere.eval.report --split test

# ── Serve ────────────────────────────────────────────────────────────────────
serve:
	uvicorn aquasphere.serve.app:app --reload --port 8000

ui-data:
	python -c "import shutil, pathlib; (pathlib.Path('web/data')).mkdir(parents=True, exist_ok=True); shutil.copy('docs/results/metrics.json', 'web/data/metrics.json')"

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
	$(MAKE) train
	$(MAKE) eval
	@echo "=== Done. Check docs/results/metrics.json ==="

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
