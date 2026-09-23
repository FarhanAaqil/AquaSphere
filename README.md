# AquaSphere — OceanEmbed
### SIH Problem Statement 26066 · Ministry of Earth Sciences / INCOIS

End-to-end prototype for **satellite embedding-based reconstruction of subsurface ocean temperature** from surface satellite observations, covering the North Indian Ocean (5°N–30°N, 45°E–105°E).

---

## What's real vs. what's still simulated

| Variable | Status | Source |
|---|---|---|
| **Sea Surface Temperature (SST)** | ✅ **Real** | NOAA OISST v2.1 via ERDDAP (free, no login) |
| **Subsurface T profile (0–1000 m)** | ✅ **Real** | MLP trained on real Argo float profiles |
| **Ocean Embedding (16-dim)** | ✅ **Real** | MLP encoder output — not a placeholder |
| **Validation metrics (RMSE/bias/r)** | ✅ **Real** | Computed on held-out Argo profiles |
| **Sea Surface Salinity (SSS)** | ⏳ Phase 2 | SMAP / Aquarius (NASA PO.DAAC — requires login) |
| **Sea Level Anomaly (SSH/SLA)** | ⏳ Phase 2 | AVISO / CMEMS (requires registration) |
| **Surface currents** | ⏳ Phase 2 | OSCAR (NOAA/JPL) |
| **Surface winds** | ⏳ Phase 2 | ERA5 / ASCAT |

SSS, SSH, currents, and winds are still shown from the deterministic simulation in the UI. They are flagged as Phase 2 in the interface (the existing banners and obs-flag/est-flag labels already communicate this).

---

## Directory layout

```
AquaSphere/
├── oceanembed-prototype.html   # Full interactive UI (wired to FastAPI)
├── requirements.txt
├── data/
│   ├── collect.py              # Argo + OISST data collection
│   ├── argo_sst_training.csv   # Assembled training data (after collect.py)
│   ├── collect.log             # Fetch log
│   └── cache/                  # Raw HTTP response cache (auto-populated)
├── model/
│   ├── train.py                # MLP encoder-decoder training
│   ├── model.pt                # Trained PyTorch model (after train.py)
│   ├── scaler.json             # Input normalisation stats
│   └── validation_metrics.json # Real computed RMSE / bias / corr
└── server/
    └── main.py                 # FastAPI serving layer
```

---

## How to run locally

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

PyTorch can be slow to install. If you're on a CPU-only machine and want the fastest setup:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install fastapi uvicorn requests numpy scipy scikit-learn joblib
```

### 2. Collect training data (takes 15–45 min depending on connection)

```bash
python data/collect.py
# Quick smoke test (50 profiles, ~3 min):
python data/collect.py --max-profiles 50
```

This fetches real Argo profiles from [Argovis](https://argovis-api.colorado.edu) and collocated SST from NOAA OISST via ERDDAP. Raw responses are cached in `data/cache/` — re-runs skip already-downloaded data.

### 3. Train the model

```bash
python model/train.py
# Faster run (fewer epochs):
python model/train.py --epochs 50
```

Saves `model/model.pt`, `model/scaler.json`, and `model/validation_metrics.json`.

### 4. Start the API server

```bash
uvicorn server.main:app --reload --port 8000
```

Verify it's running:

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/predict?lat=15&lon=88&date=2025-06-01"
curl http://localhost:8000/validation
```

### 5. Open the UI

Double-click `oceanembed-prototype.html` (or serve it locally). The UI will automatically connect to the running API. Navigate to **Location profile** or **Validation** — the badge in the section header shows whether the current data is:

- 🟢 **Real OISST + model** — live SST fetched and model ran
- 🟡 **Model (sim. SST)** — SST estimated, model ran  
- ⚫ **Simulated** — API not reachable, full fallback mode

If the API isn't running, the UI still works with the original deterministic simulation — no errors, no blank screens.

---

## Architecture

```
Surface obs (SST)
      │
      ▼
  Encoder MLP
  [lat, lon, sin(doy), cos(doy), sst] → 16-dim Ocean Embedding
      │
      ▼
  Decoder MLP
  16-dim embedding → [T₀, T₅, T₁₀, ..., T₁₀₀₀]  (15 standard depths)
```

The **16-dim Ocean Embedding** is the primary output referenced in the SIH problem statement. It is returned directly from `/predict` and visualised in the Embedding view. The 2D scatter plot shows the first two dimensions, which carry the most variance after training on real Argo profiles.

---

## Standard depths

0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000 m

## Geographic scope

North Indian Ocean · 5°N–30°N · 45°E–105°E  
Emphasis on Bay of Bengal (lon ≥ 78°E) and Arabian Sea (lon < 78°E).
