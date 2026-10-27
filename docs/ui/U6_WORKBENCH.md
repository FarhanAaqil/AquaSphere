# Phase U6: Workbench — AquaSphere (OceanEmbed)

Following the **Immersive UI/UX Playbook §3.1, §4.4, §10, and Appendix A.4**.

---

## 1. Workbench Architecture Overview

The Workbench (`/explorer` / Profile view) serves as the calm, analytical layer designed for oceanographers, climate analysts, and hackathon evaluators.

### 1.1 Left Panel: Spatial Basin Navigation (`web/js/views/explore.js`)
- **North Indian Ocean Map:** Cartographic canvas displaying the regional landmask (India, Sri Lanka, Arabian Peninsula, Horn of Africa, Indochina, Sumatra).
- **Interactive Layers:**
  - Sea Surface Temperature (SST, MUR L4)
  - Sea Surface Salinity (SSS, SMAP)
  - Sea Level Anomaly (SLA, DUACS altimetry)
  - Thermocline Depth ($D_{20}$)
  - Subsurface Temperature at active depth level
- **Interactive Coordinate Crosshair:** Click anywhere on the basin grid (5°–30°N, 45°–105°E) to reposition the observation focal point.

### 1.2 Right Panel: Calibrated Vertical Profile (`web/js/views/location.js`)
- **0–1000m Chart Frame:**
  - Teal curve: AquaSphere reconstructed vertical temperature profile.
  - Teal envelope: 90% and 95% conformal prediction intervals.
  - Climatology baseline: Regional seasonal mean curve for comparative reference.
  - Surface observation cards: Direct SST, Satellite SSS proxy, Altimetry SLA, Mixed Layer Depth (MLD), and $D_{20}$.
- **Attribution & Drivers (`/explain`):**
  - Integrated gradients attribution displaying normalized feature importance (SST, SLA, SSS, Wind/Current vectors).
- **Hold-Out Integrity Flag:**
  - Clearly alerts whether the active spatiotemporal coordinate is a leak-free held-out test point or part of the training set.

---

## 2. Mandatory Data-Provenance Badging & Error Handling

- **Provenance Badges:** Implemented via `.badge-provenance` from `tokens.css`:
  - `LOCAL STORE`: Loaded from local Zarr store (`store.zarr`).
  - `CACHED`: Fast client-side LRU cache response.
  - `LIVE API`: Operational live inference from FastAPI `/predict`.
  - `SAMPLE / SYNTHETIC`: Synthetic deterministic demonstration fallback when backend is offline.
  - `CALIBRATED`: Conformal prediction intervals with empirical coverage guarantee.
- **Offline / Server-down Graceful Degradation:**
  - Automatic banner alert with clear explanation: *Backend Unreachable — Displaying deterministic synthetic demonstration values.*
  - Zero application crashes; fallback math preserves exact mathematical gradients and thermocline structure.

---

## 3. Phase U6 Gate Check

- [x] Analytical workbench views functional with real data views.
- [x] All numbers sourced from `/predict`, `/explain`, and `/meta` API endpoints.
- [x] Provenance badges visible on every chart and metric tile.
- [x] Offline demo fallback handles disconnected states gracefully without broken UI.
