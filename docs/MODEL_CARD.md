# Model Card — AquaSphere (OceanEmbed)

> **Status:** Draft — populated after Phase 4 training runs.

## Intended Use

Decision-support tool for researchers and INCOIS operators to visualise
reconstructed subsurface North Indian Ocean temperature profiles from satellite
observations.  **Not for operational forecasting or safety-critical decisions
without INCOIS validation.**

## Training Data

- Argo float profiles 2015–2025, delayed-mode adjusted, QC flag 1 (good).
- Satellite predictors: NOAA OISST v2.1, SMAP SSS, CMEMS DUACS SLA, ERA5 winds.
- Domain: 5–30°N, 45–105°E.  15 standard depths (0–1000 m).

## Evaluation Splits

| Split | Years | Floats |
|---|---|---|
| Train | 2015–2022 | held strictly by float ID |
| Val | 2023 | held strictly by float ID |
| Test | 2024–2025 | **used once — final reporting only** |

## Metrics

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

## Known Failure Modes

- Coastal regions where SSS retrievals are contaminated by radio-frequency interference.
- Eddy-rich zones (e.g., Somali Current, Lakshadweep eddy) where spatial context from a 9×9 patch may be insufficient.
- Monsoon onset/withdrawal transitions — rapid thermocline shoaling not fully captured.
- Depths > 700 m: Argo data are sparse; model uncertainty is large here.

## Limitations

This model is a research prototype trained on publicly available data.
Results should be interpreted alongside physical oceanographic judgement.
