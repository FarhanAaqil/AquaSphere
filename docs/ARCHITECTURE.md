# System Architecture — AquaSphere (OceanEmbed)

> **Framework:** Multi-Sensor Satellite Embedding & Calibrated Subsurface Ocean Reconstruction  
> **Target Region:** North Indian Ocean ($5^\circ\text{–}30^\circ\text{N}, 45^\circ\text{–}105^\circ\text{E}$)  
> **Problem Statement:** SIH 26066 (MoES / INCOIS)

---

## 1. End-to-End System Pipeline

```mermaid
flowchart TD
    subgraph Data_Sources[1. Observational Ingestion]
        OISST[NOAA OISST v2.1\nAVHRR Surface Temp]
        DUACS[CMEMS DUACS\nSea Level Anomaly + Currents]
        SMAP[NASA SMAP\nSea Surface Salinity]
        WIND[CCMP / ERA5\n10m Wind Stress]
        ARGO[Argo GDAC Floats\nDelayed-Mode Adjusted Profiles]
    end

    subgraph Storage[2. Data & Feature Pipeline]
        STORE[(Multi-Sensor Surface Zarr Store\nChunked 0.25° NIO Grid)]
        COL[Collocator\nPCHIP Vertical Interpolation + Depth Masks]
        SPLIT[Leak-Free Splits\nFloat-Grouped & Time-Blocked]
    end

    subgraph Modeling[3. Model Hierarchy & Calibration]
        SSL[Tier C: Masked Autoencoder\nSelf-Supervised Pre-Training on Patches]
        CNN[Tier B: Patch-CNN\nSpatial Mesoscale Fronts & Eddies]
        MLP[Tier A: Multi-Sensor MLP\n18-d Input -> 16-d Unit-Norm Latent Space]
        LOSS[Masked Heteroscedastic Loss\nTemperature Variance Warmup + Physics Penalty]
        CAL[Split Conformal Calibrator\nDistribution-Free 90% Uncertainty Bounds]
    end

    subgraph Serving[4. FastAPI Serving Layer]
        RES[4-Stage Honest Resolver\n1: Zarr Store -> 2: Disk Cache -> 3: ERDDAP -> 4: 503 Fail-Fast]
        ENG[Inference Engine\nVectorized Batch & Attribution Profiling]
        API[FastAPI Endpoints\n/health · /ready · /meta · /predict · /grid · /validation/profile]
    end

    subgraph Frontend[5. Modular Web Interface]
        UI[Native ES Module Frontend\nweb/ - 9 Interactive Ocean Intelligence Views]
    end

    OISST & DUACS & SMAP & WIND --> STORE
    ARGO & STORE --> COL
    COL --> SPLIT
    SPLIT --> SSL & CNN & MLP
    SSL -. fine-tune .-> CNN & MLP
    MLP & CNN --> LOSS
    LOSS --> CAL
    CAL --> ENG
    STORE & RES --> ENG
    ENG --> API
    API --> UI
```

---

## 2. 4-Stage Honest Resolver Flow

To eliminate silent simulation, every observation lookup executes through a strict 4-stage hierarchy:

```text
Resolve(lat, lon, date):
   │
   ├─► 1. In-Memory LRU Cache: instant response (data_source = disk_cache)
   │
   ├─► 2. Local Zarr Surface Store: offline disk chunk query (data_source = local_store)
   │
   ├─► 3. On-Demand Disk Cache: verified SHA-256 cache hits (data_source = disk_cache)
   │
   ├─► 4. Live Satellite ERDDAP (if network enabled): fetches remote observation (data_source = live)
   │
   └─► 5. FAIL-FAST: Return HTTP 503 Service Unavailable (Silent simulation strictly prohibited)
```

---

## 3. Modular Frontend Architecture (`web/`)

- Built strictly with **native ES6 modules** (`<script type="module">`). Zero npm/webpack/vite build step required.
- **In-Flight Request Deduplication:** Tracks ongoing network promises in a central `Map<string, Promise>` to eliminate race conditions during rapid user clicks.
- **Dynamic Date Picker:** Range and bounds loaded from `GET /meta` rather than hardcoded dates.
- **Provenanced Visualizations:** Every chart displays an explicit badge indicating whether inputs came from `local_store`, `disk_cache`, `live`, or `offline_synthetic`.
