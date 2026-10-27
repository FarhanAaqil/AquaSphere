# AquaSphere (OceanEmbed — SIH 26066) Execution Walkthrough

**Problem Statement:** SIH 26066 — Satellite Embedding-Based Deep Learning Framework for Reconstruction of Subsurface Ocean Temperature from Surface Satellite Observations (Ministry of Earth Sciences / INCOIS).

---

## 1. Summary of Completed Phases (1 through 8)

| Phase | Milestone | Deliverables | Verification Status |
|---|---|---|---|
| **Phase 1** | **Foundation & Code Quality** | Restructured package into `src/aquasphere/`, `pyproject.toml`, strict ruff, mypy, and GitHub Actions CI. | ✅ 100% CI Green |
| **Phase 2** | **Evaluation Protocol** | Leak-free float-grouped and time-blocked splits, oceanographic metrics (RMSE, SS, D20, MLD, OHC300), baseline ladder. | ✅ No-leakage test verified |
| **Phase 3** | **Data Pipeline** | Multi-sensor ingestion (Argo, OISST, SMAP, DUACS, ERA5), Zarr surface store, manifests, and checksums. | ✅ Store opens offline |
| **Phase 4** | **Tier A Model & Uncertainty** | 16-D bottleneck MLP, masked heteroscedastic loss, conformal calibration ($90\%$ coverage). | ✅ 85–95% coverage gate met |
| **Phase 5** | **Tier B & Tier C (Novelty)** | Patch-CNN encoder, Masked Patch Autoencoder self-supervised pre-training, multi-seed ablation ladder. | ✅ Multi-seed ablation recorded |
| **Phase 6** | **Serving Layer** | FastAPI serving (`/predict`, `/predict_batch`, `/grid`, `/validation/profile`, `/meta`, `/explain`), 4-stage honest resolver. | ✅ Zero silent simulation |
| **Phase 7** | **Modular Frontend** | Native ES modules frontend in `web/` across all 9 views, in-flight request deduplication, conformal bands, honest badges. | ✅ All 9 views operational |
| **Phase 8** | **Final Eval & Documentation** | Auto-generated benchmark tables, Model/Data cards, Architecture diagrams, pitch demo script, reproduction guide. | ✅ Reproducible from clean clone |

---

## 2. Honest Benchmark Ladder (Held-Out Evaluation)

<!-- METRICS:START -->
### Honest Baseline Ladder (Float-Grouped Hold-Out Evaluation)

> **Evaluation Set:** 242 held-out profiles across 15 unique Argo floats.
> **Hold-Out Rule:** Zero float ID overlap with training (leak-free guaranteed).

| Model | Overall RMSE (°C) | Thermocline RMSE (50-150m) | 95% CI (Thermo) | Skill Score (SS) | D20 Error (m) | MLD Error (m) |
|---|---|---|---|---|---|---|
| **Climatology** | 1.925 | 2.290 | [2.03, 2.58] | +0.000 | 29.6 | 30.6 |
| **Climatology + Ridge** | 1.776 | 2.195 | [1.98, 2.45] | +0.149 | 29.7 | 30.0 |
| **Gradient Boosted Trees (HistGBDT)** | 0.954 | 1.460 | [1.18, 1.82] | +0.754 | 20.7 | 16.5 |
| **v1 OceanEmbedNet (Re-evaluated)** | 1.184 | 1.590 | [1.43, 1.81] | +0.622 | 21.9 | 18.1 |

*Note: v1 OceanEmbedNet numbers reflect honest float-grouped hold-out splits (unlike the random split reported in v1 prototypes).*
<!-- METRICS:END -->

---

## 3. Multi-Sensor Ablation Table

<!-- ABLATION:START -->
| Run | SST | +SLA | +SSS | +Wind/Curr | +Patch | +SSL | Thermo RMSE (°C) | Skill Score | Conformal Cov. |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| A1 (SST only) | Yes | - | - | - | - | - | 1.930 ± 0.039 | 0.195 ± 0.032 | 90.3% ± 0.0% |
| A2 (+ SLA) | Yes | Yes | - | - | - | - | 1.945 ± 0.036 | 0.183 ± 0.030 | 90.3% ± 0.0% |
| A3 (+ SSS) | Yes | Yes | Yes | - | - | - | 1.952 ± 0.024 | 0.177 ± 0.020 | 90.3% ± 0.0% |
| A4 (+ Wind/Curr) | Yes | Yes | Yes | Yes | - | - | 1.989 ± 0.009 | 0.145 ± 0.008 | 90.3% ± 0.0% |
| B (+ Patch CNN) | Yes | Yes | Yes | Yes | Yes | - | 2.060 ± 0.013 | 0.084 ± 0.012 | 90.3% ± 0.0% |
| C (+ SSL Pretrain) | Yes | Yes | Yes | Yes | Yes | Yes | 2.093 ± 0.040 | 0.053 ± 0.036 | 90.3% ± 0.0% |
<!-- ABLATION:END -->

---

## 4. Experiment E1: Leakage Gap Analysis

| Model | Random Split (Naive) | Float-Grouped | Time-Blocked | Float Leakage Gap (ΔRMSE) | Temporal Gap (ΔRMSE) |
|---|:---:|:---:|:---:|:---:|:---:|
| **Climatology** | 1.927 °C | 2.187 °C | 2.348 °C | **+0.260 °C** | **+0.420 °C** |
| **Climatology + Ridge** | 1.914 °C | 2.150 °C | 2.280 °C | **+0.236 °C** | **+0.366 °C** |
| **Gradient Boosted Trees (HistGBDT)** | 1.036 °C | 1.507 °C | 1.390 °C | **+0.471 °C** | **+0.354 °C** |
| **v1 OceanEmbedNet** | 1.333 °C | 1.505 °C | 1.997 °C | **+0.172 °C** | **+0.663 °C** |

---

## 4. Verification Commands

```bash
# Linting & Formatting Check
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/

# Strict Type-checking
python -m mypy src/aquasphere/data src/aquasphere/models src/aquasphere/train src/aquasphere/eval src/aquasphere/serve

# Test Suite & Coverage Verification (>= 80%)
python -m pytest tests/ --cov=aquasphere --cov-fail-under=80 -q

# Launch Serving API and Web Interface
python -m aquasphere.serve.app --host 0.0.0.0 --port 8000
```
