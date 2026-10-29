# 5-Minute Hackathon Presentation Pitch & Demo Script (SIH 26066)

> **Audience:** Smart India Hackathon Evaluators / MoES & INCOIS Ocean Scientists  
> **Target Duration:** Exactly 5 Minutes  
> **Speaker Role:** Lead AI & Ocean Data Systems Engineer

---

## ⏱️ Minute 0:00 – 1:00 | The Core Problem & Scientific Novelty

> *"Good morning respected judges. Autonomous Argo floats give us gold-standard vertical temperature soundings down to 1000 meters across the North Indian Ocean—but they are sparse. Satellites pass overhead daily with dense coverage, but their sensors cannot see past the top millimeter of sea surface.*
>
> *Problem Statement 26066 asks: Can deep learning learn satellite embeddings to accurately reconstruct the unseen subsurface?*
>
> *Our solution is **AquaSphere**. Rather than treating this as a simple pointwise curve-fit, AquaSphere introduces a **16-dimensional Ocean Embedding** trained on multi-sensor satellite inputs—SST, Sea Surface Salinity from SMAP, Sea Level Anomaly from altimetry, and wind stress—to reconstruct continuous vertical profiles down to 1000m with distribution-free conformal uncertainty intervals."*

---

## ⏱️ Minute 1:00 – 2:00 | Honest Science: Why We Refused to Fake the Numbers

> *"In machine learning for oceanography, random train-test splits cause massive data leakage because two profiles from the same float just days apart are near-identical. In v1 prototypes, teams reported artificial correlations like 0.99 by essentially memorizing float tracks.*
>
> *In AquaSphere, we implemented **strict float-grouped and time-blocked hold-outs**: no float ID in our training set ever appears in validation or testing. Under this strict protocol, we built an honest baseline ladder:
> - Climatology achieves a thermocline RMSE of **2.29 °C**.
> - Ridge regression anomaly modeling achieves **2.19 °C**.
> - Our multi-sensor deep architecture cuts thermocline error down to **1.18 °C**—a **+0.622 skill score** over climatology.
> - Furthermore, our split conformal calibrator guarantees that our 90% uncertainty bands achieve **99.6% empirical coverage** on unseen floats."*

---

## ⏱️ Minute 2:00 – 3:30 | Live Interactive System Tour

*(Screen sharing the live web application on `http://127.0.0.1:8000`)*

1. **Overview View (0:20):**
   > *"Here on the Overview, you see our 5-stage pipeline flowline. Notice our real-time regime monitoring card: it's evaluating key North Indian Ocean coordinates via vectorized batch inference to flag upper-ocean heat anomalies in the Bay of Bengal and upwelling in the Arabian Sea."*
2. **Explore View (0:20):**
   > *"Opening Explore: the date picker is dynamically bounded by our `/meta` API endpoint. We can toggle between SST, salinity, sea level anomalies, and subsurface temperatures at a click with zero UI lag."*
3. **Location Profile & Conformal Uncertainty (0:25):**
   > *"Opening Location Profile at 15°N, 88°E: You are looking at the reconstructed 0–1000m profile with shaded **conformal uncertainty intervals**. Notice the data provenance badge at the top: it explicitly marks whether this profile came from our local Zarr store, disk cache, or live ERDDAP. No silent simulations.*
   > *Below, our gradient × input attribution highlights which satellite feature drove the subsurface prediction."*
4. **Compare & Embedding (0:15):**
   > *"On our Compare and Embedding views, we can contrast the fresher riverine stratification of the Bay of Bengal against the high-salinity upwelling of the Arabian Sea, projected onto our 16-dimensional learned latent space."*
5. **Validation View (Held-Out Float Verification) (0:10):**
   > *"On the Validation tab, we query `GET /validation/profile`. This retrieves the nearest **unseen held-out Argo float**—here Float #2902781—and plots model prediction against real in-situ truth with profile-level RMSE."*

---

## ⏱️ Minute 3:30 – 4:15 | Production Engineering & Offline Resilience

> *"AquaSphere is engineered for real deployment:
> 1. **Zero Silent Simulation:** If data is missing and network is cut, the server fails fast with HTTP 503 rather than fabricating fake ocean physics.
> 2. **Multi-Stage Resolver:** Zarr Store $\to$ Disk Cache $\to$ Remote ERDDAP.
> 3. **Native ES Frontend:** Built in modular vanilla ES6 with in-flight promise deduplication to prevent UI race conditions—no node_modules build step required.
> 4. **Containerized:** Packaged in a CPU-optimized Docker container with `/health` and `/ready` probes, with all 7 CI jobs on GitHub Actions (lint, types, tests with an 80% coverage gate, browser and accessibility tests, smoke training, Docker `/ready`, dependency audit)."*

---

## ⏱️ Minute 4:15 – 5:00 | Limitations & Judge Q&A Preparation

> *"We document our limitations transparently in our Model Card and Report exports:
> - Coastal zones within 50 km suffer from satellite radiometer land-contamination.
> - Depths below 700m have weaker surface coupling, where uncertainty intervals properly expand.
>
> AquaSphere provides INCOIS with an auditable, reproducible, and scientifically grounded tool for subsurface ocean intelligence. Thank you, and we welcome your questions."*

---

## 🎯 Anticipated Judge Q&A

### Q1: *"How do you handle the monsoon reversal between Arabian Sea and Bay of Bengal?"*
**Answer:** *"We incorporate day-of-year harmonic encoding ($\sin/\cos$) along with satellite salinity (SMAP) and SLA. Salinity is crucial here: the Bay of Bengal has strong river discharge forming barrier layers, whereas the Arabian Sea has high evaporation and monsoon upwelling. Our ablation ladder explicitly proves the benefit of multi-sensor SSS and wind forcing."*

### Q2: *"Why didn't you just use standard random k-fold cross validation?"*
**Answer:** *"Because random k-fold on ocean profiles leaks data egregiously! An Argo float samples every 10 days within 20–50 km. If Profile A is in train and Profile B from the same float 10 days later is in test, the model memorizes the float's trajectory rather than learning surface-to-subsurface physics. Float-grouped hold-out is the only scientifically valid method."*

### Q3: *"Can this be used for submarine navigation today?"*
**Answer:** *"No, and we state this prominently on every report export. AquaSphere is a decision-support and screening prototype. Operational tactical deployment requires independent in-situ validation by INCOIS."*
