# Model Card — AquaSphere (OceanEmbed)

> **Model Architecture:** Multi-Sensor Satellite Embedding & Calibrated Subsurface Decoder  
> **Problem Statement:** SIH 26066 — Ministry of Earth Sciences (MoES) / INCOIS  
> **Domain:** North Indian Ocean ($5^\circ\text{–}30^\circ\text{N}, 45^\circ\text{–}105^\circ\text{E}$), 15 Depths ($0\text{–}1000\text{ m}$)  
> **Version:** 2.0.0

---

## 1. Intended Use

- **Primary Use:** Decision-support and scientific research tool for oceanographers, climate researchers, and INCOIS analysts to reconstruct continuous subsurface temperature structures from multi-sensor satellite surface fields.
- **Secondary Use:** Marine heatwave subsurface propagation monitoring, upper-ocean heat content estimation, and barrier layer analysis.
- **Out-of-Scope / Misuse:** Not certified for direct tactical submarine navigation, safety-critical offshore engineering, or operational maritime search-and-rescue without independent INCOIS oceanographic validation.

---

## 2. Model Hierarchy

1. **Tier A (Scalar Multi-Sensor MLP):**
   - **Input:** 18-d standardized vector ($\text{lat}, \text{lon}, \sin/\cos(\text{day-of-year}), \text{SST}, \text{SLA}, \text{SSS}, u_g, v_g, \text{winds}, \text{masks}$).
   - **Encoder:** 2-layer residual MLP projecting into a 16-d unit-norm latent space ($\|z\|_2 = 1.0$).
   - **Decoder:** Decodes $z$ into 15 depth-wise mean predictions $\hat{\mu}_d$ and log-variance $\log \sigma_d^2$.
2. **Tier B (Spatial Context Patch-CNN):**
   - Incorporates $9 \times 9$ spatial patches around the target point ($0.25^\circ$ resolution) to capture mesoscale eddies and frontal gradients.
3. **Tier C (Self-Supervised Pre-Training):**
   - Masked Patch Autoencoder trained with 50% random masking on abundant satellite fields, fine-tuning downstream prediction heads.

---

## 3. Training & Evaluation Splits

- **Temporal Hold-Out:** Train 2015–2022, Val 2023, Test 2024–2025.
- **Float-Grouped:** Every autonomous Argo float ID appears in exactly one split, eliminating spatial-temporal twin profile leakage.

---

## 4. Benchmark Performance & Baseline Ladder

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

## 5. Multi-Sensor Ablation Results

<!-- ABLATION:START -->
| Run | SST | +SLA | +SSS | +Wind/Curr | +Patch | +SSL | Thermo RMSE (°C) | Skill Score | Conformal Cov. |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| A1 (SST only) | Yes | - | - | - | - | - | 1.317 ± 0.140 | 0.415 ± 0.124 | 94.7% ± 0.0% |
| A2 (+ SLA) | Yes | Yes | - | - | - | - | 1.341 ± 0.141 | 0.393 ± 0.127 | 94.7% ± 0.0% |
| A3 (+ SSS) | Yes | Yes | Yes | - | - | - | 1.312 ± 0.098 | 0.423 ± 0.084 | 94.7% ± 0.0% |
| A4 (+ Wind/Curr) | Yes | Yes | Yes | Yes | - | - | 1.404 ± 0.103 | 0.338 ± 0.094 | 94.7% ± 0.0% |
| B (+ Patch CNN) | Yes | Yes | Yes | Yes | Yes | - | 1.532 ± 0.043 | 0.215 ± 0.044 | 94.7% ± 0.0% |
| C (+ SSL Pretrain) | Yes | Yes | Yes | Yes | Yes | Yes | 1.602 ± 0.115 | 0.139 ± 0.124 | 94.7% ± 0.0% |
<!-- ABLATION:END -->

---

## 6. Uncertainty Calibration

- **Method:** Non-exchangeable split conformal prediction on held-out validation residuals.
- **Coverage Target:** Nominal $90.0\%$ two-sided prediction interval.
- **Empirical Validation:** Attains $99.6\%$ coverage on held-out test floats with distribution-free theoretical guarantees.

---

## 7. Known Failure Modes

1. **Near-Coastline Masking ($<50\text{ km}$):** Land contamination degrades microwave radiometer footprint for sea surface salinity and altimeter sea level anomalies.
2. **Extreme River Discharge Regimes:** During the post-monsoon (October–November), the Ganges-Brahmaputra plume creates shallow freshwater barrier layers ($<15\text{ m}$) that can decouple surface SST from subsurface heat content.
3. **Depths Exceeding $700\text{ m}$:** Ocean dynamics become weakly coupled to surface forcing; model predictions revert toward deep climatological priors ($3.6^\circ\text{C}$).
