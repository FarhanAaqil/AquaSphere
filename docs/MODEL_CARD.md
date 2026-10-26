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
*Run `python -m aquasphere.eval.report` to populate this section.*
<!-- METRICS:END -->

## Known Failure Modes

- Coastal regions where SSS retrievals are contaminated by radio-frequency interference.
- Eddy-rich zones (e.g., Somali Current, Lakshadweep eddy) where spatial context from a 9×9 patch may be insufficient.
- Monsoon onset/withdrawal transitions — rapid thermocline shoaling not fully captured.
- Depths > 700 m: Argo data are sparse; model uncertainty is large here.

## Limitations

This model is a research prototype trained on publicly available data.
Results should be interpreted alongside physical oceanographic judgement.
