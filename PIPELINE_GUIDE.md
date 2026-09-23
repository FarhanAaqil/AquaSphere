# OceanEmbed — Complete System Architecture & Pipeline Guide

> **Smart India Hackathon Problem Statement 26066**  
> **Topic:** Satellite Embedding-Based Deep Learning Framework for Reconstruction of Subsurface Ocean Temperature from Surface Satellite Observations  
> **Agency / Ministry:** Ministry of Earth Sciences / INCOIS  
> **Geographic Scope:** North Indian Ocean ($5^\circ\text{N}–30^\circ\text{N}, 45^\circ\text{E}–105^\circ\text{E}$)  
> **Target Depths:** $0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000\text{ m}$ (15 standard levels)

---

## 1. System Overview

Traditional ocean temperature observation relies heavily on autonomous ARGO profiling floats, which provide high vertical accuracy but are spatially and temporally sparse. Conversely, satellite sensors observe surface parameters (Sea Surface Temperature, Sea Surface Salinity, Sea Surface Height, winds) at high spatial resolution but cannot directly penetrate beneath the top millimeter of water.

**OceanEmbed** bridges this gap:
1. It ingests surface satellite observations and spatiotemporal metadata:
   $$\mathbf{x} = \left[\text{Latitude}, \text{Longitude}, \sin\left(\frac{2\pi \cdot \text{DOY}}{365}\right), \cos\left(\frac{2\pi \cdot \text{DOY}}{365}\right), \text{SST}\right]$$
2. It projects these surface variables into a rich **16-dimensional latent Ocean Embedding**:
   $$\mathbf{z} = \text{Encoder}(\mathbf{x}) \in \mathbb{R}^{16}$$
3. It decodes the 16-dimensional latent embedding into a continuous subsurface vertical temperature profile from the surface down to $1,000\text{ m}$:
   $$\hat{\mathbf{y}} = \text{Decoder}(\mathbf{z}) \in \mathbb{R}^{15}$$
4. Predictions are served through a high-performance **FastAPI backend** and visualized dynamically on an **interactive dashboard** with graceful offline fallbacks.

---

## 2. Repository Structure

```text
AquaSphere/
├── data/
│   ├── collect.py              # Ingests Argo profiles (Argovis) & collocates NOAA OISST (ERDDAP)
│   ├── argo_sst_training.csv   # Collocated training dataset with 15 depth targets
│   └── cache/                  # Disk cache for Argovis & NOAA OISST HTTP responses
├── model/
│   ├── train.py                # PyTorch neural network training & evaluation script
│   ├── model.pt                # Checkpointed PyTorch model weights (Encoder + Decoder)
│   ├── scaler.json             # Input standardisation statistics (mean & standard deviation)
│   └── validation_metrics.json # Computed validation metrics (RMSE, bias, Pearson r per depth group)
├── server/
│   └── main.py                 # FastAPI serving layer (port 8000, CORS enabled)
├── oceanembed-prototype.html   # Standalone interactive dashboard UI
├── requirements.txt            # Python environment dependencies
├── PIPELINE_GUIDE.md           # This comprehensive guide
└── README.md                   # Project overview and real vs. simulated matrix
```

---

## 3. Data Pipeline (`data/collect.py`)

### Data Sources
1. **Argovis API (`https://argovis-api.colorado.edu`)**:
   - Provides quality-controlled global ARGO float profiles.
   - Script uses 7-day bulk polygon queries over the North Indian Ocean ($45^\circ\text{E}–105^\circ\text{E}, 5^\circ\text{N}–30^\circ\text{N}$) to fetch complete profile arrays in single requests.
2. **NOAA OISST v2.1 via ERDDAP (`https://www.ncei.noaa.gov/erddap/griddap/...`)**:
   - Daily $0.25^\circ$ optimum interpolation sea surface temperature.
   - Collocated with each ARGO float location and date.

### Processing Steps
- Decibar pressure readings are converted to depths in meters ($\approx 1\text{ dbar} = 1\text{ m}$).
- Temperatures are interpolated onto the 15 standard depths ($0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000\text{ m}$).
- Results are saved to `data/argo_sst_training.csv` incrementally every 5 date windows so no network progress is lost.
- All HTTP responses are cached under `data/cache/` to make re-runs instantaneous.

---

## 4. Deep Learning Model (`model/train.py`)

### Architecture
```text
Inputs [5]                                          Encoder
[lat, lon, sin(doy), cos(doy), sst]  --->  Linear(5 -> hidden=64) + ReLU
                                     --->  Linear(hidden -> embed_dim=16)
                                                   |
                                                   v
                                     [16-dim Ocean Embedding Vector]
                                                   |
                                                   v
Decoder                              --->  Linear(16 -> hidden=64) + ReLU
Subsurface Temperatures [15]         --->  Linear(hidden -> 15 depths)
```

### Physical Constraints & Surface Alignment
Because ARGO floats shut off sensors at $2–5\text{ m}$ depth to prevent surface contamination, observations at $0\text{ m}$ are physically anchored to the collocated satellite Sea Surface Temperature (SST). Missing deep abyss values ($1,000\text{ m}$) are filled via downward propagation of the deepest measured thermocline reading.

### Model Performance on Held-Out Validation Set

| Layer Depth | Depths Covered | RMSE | Mean Bias | Pearson Correlation ($r$) |
|---|---|---|---|---|
| **Mixed Layer (0–30 m)** | 0, 5, 10, 20, 30 m | **0.728 °C** | +0.026 °C | **0.904** |
| **Thermocline (50–150 m)** | 50, 75, 100, 125, 150 m | **1.118 °C** | +0.046 °C | **0.934** |
| **Sub-thermocline (200–300 m)**| 200, 300 m | **0.854 °C** | -0.087 °C | **0.954** |
| **Deep Abyss (500–1000 m)** | 500, 700, 1000 m | **0.737 °C** | +0.066 °C | **0.936** |
| **Overall Ocean Column** | **All 15 Depths** | **0.894 °C** | **+0.026 °C** | **0.993** |

---

## 5. Serving Layer (`server/main.py`)

The FastAPI application provides three endpoints:

1. **`GET /health`**
   - Returns `{ "status": "ok", "model_loaded": true, "backend": "pytorch" }`.
2. **`GET /predict?lat={lat}&lon={lon}&date={YYYY-MM-DD}`**
   - Queries or calculates collocated SST.
   - Standardises input features using `model/scaler.json`.
   - Passes tensor through PyTorch encoder to produce the 16-dim embedding.
   - Passes embedding through decoder to reconstruct temperatures at all 15 depths.
   - Returns JSON with `lat`, `lon`, `date`, `sst`, `source` (`"real"` | `"model_simulated_sst"`), `depths`, `profile`, and `embedding`.
3. **`GET /validation`**
   - Returns `{ "overall": {...}, "per_depth": [...], "grouped": [...] }` directly from `model/validation_metrics.json`.

---

## 6. Frontend Dashboard Integration (`oceanembed-prototype.html`)

- **Location View:** When selecting a point in the North Indian Ocean, the dashboard sends an asynchronous request to `http://localhost:8000/predict`. When received, the SVG profile updates and displays a `● Real OISST + model` badge.
- **Validation View:** Dynamically queries `http://localhost:8000/validation` and renders the real validation metrics table.
- **Offline Resilience:** If the server is offline, the interface catches errors silently and falls back to deterministic simulation—ensuring the prototype never breaks.

---

## 7. Step-by-Step Run Instructions (From Scratch)

### Step 1: Environment Setup
```bash
git clone https://github.com/FarhanAaqil/AquaSphere.git
cd AquaSphere
pip install -r requirements.txt
```

### Step 2: Ingest Real Data (Optional if dataset already exists)
```bash
python data/collect.py
```
*Note: An initial dataset with ~1,800+ profiles is already included in `data/argo_sst_training.csv`.*

### Step 3: Train the PyTorch Model
```bash
python model/train.py --epochs 200 --hidden 64
```
This produces `model/model.pt`, `model/scaler.json`, and `model/validation_metrics.json`.

### Step 4: Start the API Server
```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```
Verify the server is running by opening `http://localhost:8000/health` in your browser.

### Step 5: Launch the Frontend
Open `oceanembed-prototype.html` directly in your browser:
- On Windows: Double-click `oceanembed-prototype.html` or run:
  ```powershell
  Start-Process oceanembed-prototype.html
  ```
Navigate to **Location** and **Validation** to view the live model reconstructions.
