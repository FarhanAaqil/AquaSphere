### Experiment E1: Generalization & Leakage Gap Analysis

> **Objective:** Quantify the performance inflation caused by naive random splitting in oceanography.
> In oceanographic machine learning, random splitting leaks Argo float trajectories (spatial autocorrelation)
> and temporal persistence, producing dangerously optimistic error metrics.

#### Thermocline RMSE (50–150 m) Across Splitting Protocols

| Model | Random Split (Naive) | Float-Grouped | Time-Blocked | Float Leakage Gap (ΔRMSE) | Temporal Gap (ΔRMSE) |
|---|:---:|:---:|:---:|:---:|:---:|
| **Climatology** | 1.927 °C | 2.187 °C | 2.348 °C | **+0.260 °C** | **+0.420 °C** |
| **Climatology + Ridge** | 1.914 °C | 2.150 °C | 2.280 °C | **+0.236 °C** | **+0.366 °C** |
| **Gradient Boosted Trees (HistGBDT)** | 1.036 °C | 1.507 °C | 1.390 °C | **+0.471 °C** | **+0.354 °C** |
| **v1 OceanEmbedNet** | 1.333 °C | 1.505 °C | 1.997 °C | **+0.172 °C** | **+0.663 °C** |

#### Skill Score (vs Climatology) Across Splitting Protocols

| Model | Random SS | Float-Grouped SS | Time-Blocked SS | Impact |
|---|:---:|:---:|:---:|---|
| **Climatology** | +0.000 | +0.000 | +0.000 | Consistent across splits |
| **Climatology + Ridge** | +0.113 | +0.089 | +0.199 | Skill drops by 0.024 under honest spatial hold-out |
| **Gradient Boosted Trees (HistGBDT)** | +0.817 | +0.680 | +0.749 | Skill drops by 0.136 under honest spatial hold-out |
| **v1 OceanEmbedNet** | +0.634 | +0.626 | +0.348 | Skill drops by 0.008 under honest spatial hold-out |

#### Key Scientific Findings
1. **Random splitting underestimates thermocline error:** Naive random splitting yields artificially lower RMSE because subsequent profiles from the same drifting float exist in both training and test sets.
2. **Float-grouped holdout enforces generalization:** Holding out complete float trajectories reveals true spatial transferability across unseen oceanic coordinates.
3. **Time-blocked holdout tests seasonal transfer:** Temporal holdout tests forward-in-time forecasting where the model cannot rely on temporally adjacent observations.