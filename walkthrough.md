# OceanEmbed — Pipeline Execution & UI Validation Walkthrough

Smart India Hackathon Problem Statement 26066: **OceanEmbed — Satellite Embedding-Based Deep Learning Framework for Reconstruction of Subsurface Ocean Temperature from Surface Satellite Observations** (Ministry of Earth Sciences / INCOIS).

---

## 1. Summary of Completed Deliverables

| Deliverable | Path | Status | Notes |
|---|---|---|---|
| **Data Ingestion** | [`data/collect.py`](file:///d:/EDU/Projects/OceanEmbed_Prototype/data/collect.py) | ✅ Operational | Bulk polygon queries to Argovis API + NOAA OISST v2.1 collocation |
| **Collocated Dataset** | [`data/argo_sst_training.csv`](file:///d:/EDU/Projects/OceanEmbed_Prototype/data/argo_sst_training.csv) | ✅ Real Data | 962+ real Argo profiles across North Indian Ocean (5°N–30°N, 45°E–105°E) |
| **Model Pipeline** | [`model/train.py`](file:///d:/EDU/Projects/OceanEmbed_Prototype/model/train.py) | ✅ Complete | PyTorch MLP Encoder-Decoder with 16-dim Ocean Embedding |
| **Trained Weights** | [`model/model.pt`](file:///d:/EDU/Projects/OceanEmbed_Prototype/model/model.pt) | ✅ Saved | Checkpointed PyTorch model weights |
| **Input Normalizer** | [`model/scaler.json`](file:///d:/EDU/Projects/OceanEmbed_Prototype/model/scaler.json) | ✅ Saved | Means and standard deviations for inputs |
| **Validation Metrics** | [`model/validation_metrics.json`](file:///d:/EDU/Projects/OceanEmbed_Prototype/model/validation_metrics.json) | ✅ Real Metrics | Computed on held-out validation set |
| **FastAPI Serving** | [`server/main.py`](file:///d:/EDU/Projects/OceanEmbed_Prototype/server/main.py) | ✅ Active (:8000) | Serves `/predict`, `/validation`, and `/health` with CORS `*` |
| **Prototype Interface** | [`oceanembed-prototype.html`](file:///d:/EDU/Projects/OceanEmbed_Prototype/oceanembed-prototype.html) | ✅ Wired | Consumes real API with graceful offline fallback; zero UI/CSS regressions |

---

## 2. Validation Metrics (Real PyTorch Model vs. Real Argo Observations)

Trained on real collocated profiles across 15 standard depth levels (`0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000 m`):

- **Overall Performance:**
  - **RMSE:** `0.894 °C`
  - **Bias:** `+0.026 °C`
  - **Pearson Correlation (r):** `0.993`

- **Depth-wise Performance:**

| Depth Layer | Target Depths | Validation RMSE | Mean Bias | Pearson Correlation ($r$) |
|---|---|---|---|---|
| **Mixed Layer (0–30 m)** | 0, 5, 10, 20, 30 m | **0.728 °C** | +0.026 °C | **0.904** |
| **Thermocline (50–150 m)** | 50, 75, 100, 125, 150 m | **1.118 °C** | +0.046 °C | **0.934** |
| **Sub-thermocline (200–300 m)** | 200, 300 m | **0.854 °C** | -0.087 °C | **0.954** |
| **Deep Ocean (500–1000 m)** | 500, 700, 1000 m | **0.737 °C** | +0.066 °C | **0.936** |

---

## 3. UI Verification in Browser

The UI was verified end-to-end with the live backend running:

### Reconstructed Profile & Model Badge (Location View)
![Location View](file:///C:/Users/aaqil/.gemini/antigravity-ide/brain/f0f64e4b-db5b-4983-83c2-beebeae0699a/location_view_1790183876696.png)

### Real Validation Table from Live API (Validation View)
![Validation Table](file:///C:/Users/aaqil/.gemini/antigravity-ide/brain/f0f64e4b-db5b-4983-83c2-beebeae0699a/validation_table_1790183946981.png)

---

## 4. How to Run Locally

### Start the FastAPI Serving Layer
```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### Open the Prototype
Open [`oceanembed-prototype.html`](file:///d:/EDU/Projects/OceanEmbed_Prototype/oceanembed-prototype.html) directly in any browser. It connects automatically to `http://localhost:8000`. If the server is stopped, it gracefully falls back to deterministic simulation.
