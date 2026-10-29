# Reproducing AquaSphere Results

Follow these steps to reproduce all benchmarks, test suites, and model outputs from a clean repository clone.

Tested on **Python 3.11 / 3.12** on Linux, macOS, and Windows (CPU-optimized, GPU optional).

---

## Quickstart (≤ 6 Commands)

```bash
# 1. Clone repository
git clone https://github.com/FarhanAaqil/AquaSphere.git
cd AquaSphere

# 2. Install package and dependencies
pip install -e ".[dev]"

# 3. Verify data sources and manifest integrity
python data/verify_sources.py

# 4. Run test suite with coverage verification (>= 80%)
pytest tests/ --cov=aquasphere --cov-fail-under=80 -q

# 5. Evaluate models and regenerate benchmark tables
python -m aquasphere.eval.report --split val

# 6. Launch the interactive decision-support server
python -m aquasphere.serve.app --host 0.0.0.0 --port 8000
```

Open **`http://127.0.0.1:8000`** in any web browser to explore the 9 interactive views.

---

## Makefile Targets

| Target | Description |
|---|---|
| `make setup` | Install package in editable mode with development tooling |
| `make test` | Execute full unit, ML behavior, and API contract test suite |
| `make lint` | Run `ruff check` and `ruff format --check` |
| `make typecheck` | Run strict `mypy` type analysis on core packages |
| `make train` | Run Tier A training pipeline with conformal calibration |
| `make eval` | Generate evaluation ladder and metrics payload |
| `make serve` | Start FastAPI serving layer on port 8000 |
| `make reproduce` | Complete end-to-end clean pipeline reproduction |

---

## Docker Deployment

To reproduce the deployment environment inside an isolated container:

```bash
docker build -t aquasphere:latest .
docker run -p 8000:8000 aquasphere:latest
```

The container automatically exposes `/health` and `/ready` probes, as verified in continuous integration.
