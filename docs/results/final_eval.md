# Final evaluation: 2024-2025 test period (read once)

Run at 2026-10-30T11:58:49+00:00 on 2466 test profiles from 53 floats that never appear in training or calibration. Every model was fitted on 2015-2022; the served model was calibrated on 2023. p is the share of 2000 float-block bootstrap replicates in which the hypothesis's falsification criterion holds; Holm-adjusted over the five (docs/hypotheses_deviations.md).

## Confirmatory hypotheses

| Hypothesis | Estimate | 95% CI | Threshold | p | p (Holm) | Result |
|---|---|---|---|---|---|---|
| H1a SLA adds to SST | 19.8% RMSE reduction | 17.0% to 22.5% | >= 15% | 0.0005 | 0.002 | supported |
| H1b nowcast skill kept | ratio 1.0286 | 0.953 to 1.147 | >= 0.85 | 0.0 | 0.0 | supported |
| H2 pre-training | -0.4% (100%), 1.1% (10%) | -1.3% to 0.4%; 0.2% to 2.0% | >= 5%, >= 10% | 1.0 | 1.0 | not supported |
| H3 calibrated 90% intervals | 90.0% coverage | 88.6% to 91.1% | 87-93%; strata 85-95% | 0.0005 | 0.002 | supported |
| H4 random-split optimism | 3.2% gap (B3) | -10.0% to 14.2% | >= 20% | 0.999 | 1.0 | not supported |

## Test-period ladder (thermocline RMSE, 95% CI over floats)

| Model | Thermocline RMSE | 95% CI | Skill vs B0 | >= 20 m RMSE | D20 RMSE (m) |
|---|---|---|---|---|---|
| B0 | 1.539 | 1.361 to 1.744 | +0.000 | 1.188 | 34.52 |
| B1 | 1.333 | 1.187 to 1.502 | +0.249 | 1.042 | 30.3 |
| B2 | 1.239 | 1.109 to 1.386 | +0.352 | 0.977 | 28.09 |
| B3 | 1.470 | 1.297 to 1.655 | +0.087 | 1.123 | 29.66 |
| B4 | 1.237 | 1.109 to 1.382 | +0.354 | 0.984 | 27.35 |
| Tier A v2 | 1.262 | 1.129 to 1.412 | +0.327 | 1.001 | 27.94 |
| Tier A v2 nowcast | 1.253 | 1.126 to 1.406 | +0.336 | 0.996 | 28.95 |

## H3 coverage by region and season

| Region | Season | Profiles | Floats | Coverage | 95% CI | Status |
|---|---|---|---|---|---|---|
| All | All | 2466 | 53 | 90.0% | 88.6% to 91.1% | overall |
| Arabian Sea | Inter-monsoon | 822 | 29 | 91.2% | 90.2% to 92.3% | confirmatory |
| Arabian Sea | NE monsoon | 223 | 28 | 90.0% | 87.4% to 92.6% | descriptive only |
| Arabian Sea | SW monsoon | 705 | 30 | 92.6% | 91.2% to 93.7% | confirmatory |
| Bay of Bengal | Inter-monsoon | 318 | 23 | 87.1% | 85.0% to 89.7% | descriptive only |
| Bay of Bengal | NE monsoon | 140 | 23 | 80.0% | 75.1% to 85.0% | descriptive only |
| Bay of Bengal | SW monsoon | 258 | 22 | 87.6% | 85.6% to 89.5% | descriptive only |

Applicability domain on test: 93.1% inside; thermocline RMSE 1.247 °C inside, 1.4503 °C outside (171 profiles).

Results are reported whether or not they support the hypotheses. Exploratory comparisons are not confirmatory.
