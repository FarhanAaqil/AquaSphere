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