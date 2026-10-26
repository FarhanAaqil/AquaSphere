# Data Card — AquaSphere

> **Dataset Name:** AquaSphere North Indian Ocean In-Situ & Satellite Collocated Archive  
> **Geographic Domain:** $5^\circ\text{–}30^\circ\text{N}, 45^\circ\text{–}105^\circ\text{E}$ (Arabian Sea, Bay of Bengal, Equatorial Indian Ocean)  
> **Temporal Coverage:** 2015-01-01 through 2025-12-31  
> **Vertical Pressure Levels:** 15 Standard Depths ($0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000\text{ m}$)

---

## 1. Data Sources & Provenance

| Sensor / Product | Provider | Resolution | Parameter | Licence |
|---|---|---|---|---|
| **Argo Autonomous Floats** | Argo GDAC (Ifremer / US GODAE) | Vertical profiles | In-situ Temperature & Salinity | Open Access (Argo Policy) |
| **NOAA OISST v2.1** | NOAA NCEI via ERDDAP | $0.25^\circ \times 0.25^\circ$, Daily | Sea Surface Temperature (SST) | Public Domain |
| **CMEMS DUACS L4** | Copernicus Marine Service | $0.25^\circ \times 0.25^\circ$, Daily | Sea Level Anomaly (SLA), $u_g, v_g$ | Open Data (Copernicus) |
| **NASA SMAP L3** | NASA PO.DAAC / RSS | $0.25^\circ \times 0.25^\circ$, 8-Day | Sea Surface Salinity (SSS) | NASA Open Data |
| **ERA5 / CCMP v3** | ECMWF / RSS | $0.25^\circ \times 0.25^\circ$, Daily | 10m Wind Stress ($u_{10}, v_{10}$) | CC-BY 4.0 |

---

## 2. Quality Control & Preprocessing Pipeline

1. **Argo In-Situ Filtering:**
   - Retains only profiles flagged with QC flag = 1 ("Good").
   - Delayed-mode adjusted profiles (`TEMP_ADJUSTED`) are strictly preferred over real-time profiles.
   - PCHIP (Piecewise Cubic Hermite Interpolating Polynomial) interpolation projects observations onto the 15 standard pressure levels while preserving local extrema and preventing artificial overshoot.
   - Any depth missing raw data within interpolation bounds receives a depth mask (`m_d = 0.0`), allowing masked heteroscedastic loss training without dropping partial profiles.
2. **Satellite Collocation:**
   - Bilinear spatial interpolation to nearest $0.25^\circ$ grid cell.
   - Same-day temporal collocation with $\pm 1$ day disk caching.

---

## 3. Data Manifest & Integrity Hashes

All primary datasets are verified against cryptographic SHA-256 hashes recorded in `data/manifest.json`:

| Artifact | Size | SHA-256 Hash | Description |
|---|---|---|---|
| `argo_sst_training.csv` | 324,564 bytes | `30e1ef3ecf9bc9d3e89b5b0339ae15455b7ff83a10e551ce1273c807338aeffa` | Real collocated Argo and OISST training profiles across the NIO |
| `argo_200.parquet` | 64,812 bytes | Verified in CI | 200-profile fixture for fast deterministic testing and smoke training |
| `surface_store.zarr` | Modular Zarr | Chunked array | Surface SST, SLA, SSS, and winds on regular $0.25^\circ$ NIO grid |

---

## 4. Ethical & Environmental Considerations

- All data utilized in AquaSphere originate from public, non-commercial oceanographic observation programs.
- Preprocessing and model training were conducted using CPU-optimized and mixed-precision algorithms with an aggregate training footprint of under 0.5 kWh, minimizing compute-related carbon emissions.
