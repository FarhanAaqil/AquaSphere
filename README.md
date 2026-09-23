# AquaSphere — OceanEmbed

> **Smart India Hackathon Problem Statement 26066**  
> **Framework:** Satellite Embedding-Based Deep Learning Framework for Reconstruction of Subsurface Ocean Temperature from Surface Satellite Observations  
> **Organization:** Ministry of Earth Sciences (MoES) / INCOIS  
> **Target Region:** North Indian Ocean ($5^\circ\text{N}–30^\circ\text{N}, 45^\circ\text{E}–105^\circ\text{E}$)  
> **Vertical Resolution:** 15 Standard Depths ($0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000\text{ m}$)

---

## 🌊 Overview

Traditional vertical ocean monitoring relies on autonomous ARGO profiling floats, which yield high-fidelity measurements but are spatially and temporally sparse. In contrast, satellite radiometers measure surface conditions continuously across vast ocean basins, but their signal attenuates within the top millimeter of water.

**OceanEmbed** addresses this challenge by learning a nonlinear latent representation—the **16-dimensional Ocean Embedding**—that maps sea surface temperature and spatiotemporal coordinates to continuous vertical temperature profiles down to $1,000\text{ m}$ depth.

---

## 📊 Live Model Validation Benchmarks

Trained on **1,854 real collocated ARGO float profiles and NOAA OISST v2.1 satellite observations** across the North Indian Ocean:

| Depth Layer | Depths Covered | Validation RMSE | Mean Bias | Pearson Correlation ($r$) |
|---|---|---|---|---|
| **Mixed Layer (0–30 m)** | 0, 5, 10, 20, 30 m | **0.728 °C** | +0.026 °C | **0.904** |
| **Thermocline (50–150 m)** | 50, 75, 100, 125, 150 m | **1.118 °C** | +0.046 °C | **0.934** |
| **Sub-thermocline (200–300 m)** | 200, 300 m | **0.854 °C** | -0.087 °C | **0.954** |
| **Deep Abyss (500–1000 m)** | 500, 700, 1000 m | **0.737 °C** | +0.066 °C | **0.936** |
| **Overall Ocean Column** | **All 15 Depths** | **0.894 °C** | **+0.026 °C** | **0.993** |

*All metrics are verified on a held-out validation set and served live to the dashboard via `/validation`.*

---

## 🔄 Real vs. Phase 2 Features

| Variable / Component | Status | Source / Pipeline |
|---|---|---|
| **Sea Surface Temperature (SST)** | ✅ **Real** | NOAA OISST v2.1 AVHRR via ERDDAP ($0.25^\circ$ grid) |
| **Subsurface T Profiles (0–1000 m)** | ✅ **Real** | PyTorch MLP trained on collocated ARGO floats |
| **Ocean Embedding (16-dim)** | ✅ **Real** | Encoder latent vector returned as first-class output |
| **Validation Metrics (RMSE/Bias/r)** | ✅ **Real** | Evaluated on real held-out ARGO observations |
| **Serving Layer & CORS** | ✅ **Real** | FastAPI running on `localhost:8000` |
| **Interactive Dashboard** | ✅ **Real** | Dynamic SVG profile with live status badges |
| **Sea Surface Salinity (SSS)** | ⏳ *Phase 2* | NASA SMAP / Aquarius (Requires PO.DAAC login) |
| **Sea Surface Height (SSH/SLA)** | ⏳ *Phase 2* | Copernicus CMEMS / AVISO (Requires registration) |
| **Surface Currents & Winds** | ⏳ *Phase 2* | OSCAR (NOAA/JPL) & ECMWF ERA5 |

---

## 🏗️ Neural Network Architecture

```text
Surface Satellite Observations & Coordinates
[lat, lon, sin(doy), cos(doy), sst]
                    │
                    ▼
          ENCODER NETWORK (PyTorch)
          Linear(5 → 64) → ReLU → Linear(64 → 16)
                    │
                    ▼
     ┌─────────────────────────────┐
     │ 16-Dimensional Ocean Embed  │  <-- First-class output for search,
     └─────────────────────────────┘      clustering & projection
                    │
                    ▼
          DECODER NETWORK (PyTorch)
          Linear(16 → 64) → ReLU → Linear(64 → 15)
                    │
                    ▼
Reconstructed Vertical Temperature Profile [T₀, T₅, ..., T₁₀₀₀]
```

---

## 📂 Repository Structure

```text
AquaSphere/
├── data/
│   ├── collect.py              # Bulk Argo float fetcher + NOAA OISST collocation
│   ├── argo_sst_training.csv   # Real training dataset (1,854+ profiles)
│   └── cache/                  # Disk cache for Argovis & NOAA ERDDAP responses
├── model/
│   ├── train.py                # PyTorch MLP training script
│   ├── model.pt                # Checkpointed neural network weights
│   ├── scaler.json             # Feature standardization statistics
│   └── validation_metrics.json # Computed metrics (RMSE, bias, corr)
├── server/
│   └── main.py                 # FastAPI serving layer (port 8000)
├── oceanembed-prototype.html   # Interactive UI dashboard (standalone HTML/JS)
├── requirements.txt            # Python dependencies
├── PIPELINE_GUIDE.md           # In-depth architectural & execution guide
└── README.md                   # Project overview & benchmarks
```

---

## 🚀 Quick Start Guide

### 1. Installation
Clone the repository and install the dependencies:
```bash
git clone https://github.com/FarhanAaqil/AquaSphere.git
cd AquaSphere
pip install -r requirements.txt
```

### 2. Ingest Data (Optional)
The repository includes pre-assembled training data in `data/argo_sst_training.csv`. To pull additional real profiles:
```bash
python data/collect.py
# Or run with limited date windows:
python data/collect.py --max-windows 10
```

### 3. Train the Model
```bash
python model/train.py --epochs 200 --hidden 64
```
Outputs `model/model.pt`, `model/scaler.json`, and `model/validation_metrics.json`.

### 4. Start the API Server
```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```
Verify endpoints:
- `http://localhost:8000/health` — Service liveness
- `http://localhost:8000/predict?lat=15&lon=88&date=2025-06-01` — Predictions & embedding
- `http://localhost:8000/validation` — Real validation benchmarks

### 5. Launch the Dashboard
Open `oceanembed-prototype.html` directly in any web browser.
- **Location View:** Renders the dynamic temperature profile and displays the `● Real OISST + model` badge.
- **Validation View:** Automatically populates the validation table with live statistics from the backend.
- **Offline Fallback:** If the API is offline, the interface seamlessly falls back to deterministic simulation without errors.

---

## 📖 In-Depth Documentation

For full mathematical equations, physical surface layer adjustments, and end-to-end details, refer to:
👉 [**`PIPELINE_GUIDE.md`**](PIPELINE_GUIDE.md)
