# Reproducing AquaSphere Results

Tested on Python 3.11, Linux/macOS/Windows (CPU).  GPU optional.

```bash
# 1. Clone and install
git clone https://github.com/FarhanAaqil/AquaSphere.git
cd AquaSphere
pip install -e ".[dev]"          # or: uv sync

# 2. Verify data sources (metadata check — no large download)
python data/verify_sources.py

# 3. Download and build the Zarr store + Argo parquet
make data                        # runs aquasphere.data pipeline

# 4. Train Tier A (ablation A1–A4, 3 seeds each)
make train                       # runs aquasphere.train.train

# 5. Evaluate against baselines, generate metrics.json
make eval                        # runs aquasphere.eval.report

# 6. Start the API server
make serve

# 7. Run all tests
make test
```

All steps write deterministic outputs given the pinned lockfile (`uv.lock` /
`requirements-lock.txt`).  See `docs/ARCHITECTURE.md` for the full pipeline
diagram.

> **Test-set discipline:** the held-out test year (2024–2025) is touched only
> in step 5.  Do not run `make eval` with `--test` until the model is frozen.
