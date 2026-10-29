# Data Card — AquaSphere

> **Dataset Name:** AquaSphere North Indian Ocean In-Situ & Satellite Collocated Archive  
> **Geographic Domain:** $5^\circ\text{–}30^\circ\text{N}, 45^\circ\text{–}105^\circ\text{E}$ (Arabian Sea, Bay of Bengal, Equatorial Indian Ocean)  
> **Temporal Coverage:** 2015-01-01 through 2025-12-31  
> **Vertical Pressure Levels:** 15 Standard Depths ($0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000\text{ m}$)

---

## 1. Data Sources & Provenance

Every product below is fetched from a public NOAA or Argovis endpoint with no account. The
registry in code is `aquasphere.data.sources`; `make data` rebuilds everything (≈4 GB on first
run, cached under `data/cache/` afterwards).

| Product | Server · dataset ID | Resolution | Store variables | Available from |
|---|---|---|---|---|
| **Argo floats** | Argovis API (`/argo`, weekly polygon queries) | Profiles | Labels: T at 15 depths, data mode R/A/D | 2015 in this project |
| **NOAA OISST v2.1 Final** | CoastWatch PFEG · `ncdcOisst21Agg` | 0.25°, daily | `sst` | 1981-09 |
| **NOAA CoastWatch altimetry** | CoastWatch PFEG · `nesdisSSH1day` | 0.25°, daily | `sla`, `ug`, `vg` (geostrophic) | **2017-02-13** |
| **SMAP sea-surface salinity (NRT)** | CoastWatch · `noaacwSMAPsssDaily` | 0.25°, daily (gappy) | `sss` | 2015-04-01 |
| **NCEI Blended Sea Winds v2** | CoastWatch · `noaacwBlendedWindsDaily` | 0.25°, daily | `u10`, `v10` | 1987-07 |
| *OISST v2.1 Preliminary* | CoastWatch PFEG · `ncdcOisst21NrtAgg` | 0.25°, daily | (for E7 nowcast tests) | recent ~2 weeks |

Each product is fetched one month at a time with a half-cell margin, bilinearly regridded onto
the store's 0.25° grid (cell centres on whole quarter degrees, 5–30°N, 45–105°E) and written to
`data/store/surface_nio.zarr`. A day a product does not cover stays NaN with its mask at 0;
altimetry before 2017-02-13 and the many SMAP gaps are therefore **masked, never filled**.
Spot check: store SST matches the original point-by-point OISST collection at 437 Argo
positions with RMS 0.08 °C.

**Argo QC.** Profiles need position and time QC = 1, levels need temperature *and* pressure QC
= 1, pressure is converted to depth (UNESCO 1983) before PCHIP interpolation to the 15 standard
depths, and every profile keeps its data mode (R real-time, A adjusted, D delayed) so headline
results can prefer delayed-mode data. The table is checked against the pandera contract
(`aquasphere.data.contracts`) before it is written.

**Synthetic-input finding.** The older tables (`tests/fixtures/argo_200.parquet`,
`data/processed/argo_profiles.parquet`) carry SSS / SLA / current / wind columns that were
collocated from the *synthetic* demo store (`make data-demo`); `aquasphere.data.audit` proves
this by reproducing every value exactly. Only their SST is real. They are superseded by
`data/processed/argo_nio_collocated.parquet`. Coverage of the real data is in
`docs/results/data_coverage.md`.

### 1a. Input independence audit (Blueprint §10.1)

A model can look skilful simply because an input already contains Argo information, so every
input product is audited before results are reported.

| Product | Contains Argo or other in-situ T/S? | Status | Handling |
|---|---|---|---|
| OISST v2.1 (SST) | Yes: blends satellite data with ships, buoys and Argo near-surface values (above ~5 m) | Verified | Headline skill reported for 20 m and below; 0–10 m reported separately and flagged |
| ARMOR3D | Yes: merges satellite fields with in-situ profiles | Documented | Never an input or target; mooring comparison only (B5, E8) |
| Reanalyses (e.g. GLORYS12) | Yes: assimilate in-situ profiles | Documented | Not used as training targets; Argo is the label source |
| Salinity (SMAP, SMOS, CCI, multi-observation) | Possibly: some products are bias-adjusted with in-situ salinity | To verify | E3 reported with and without SSS |
| DUACS altimetry (SLA, currents) | Not expected | To verify | Confirm in product documentation |
| ERA5 / CCMP winds | Not expected | To verify | Confirm in product documentation; masked in nowcast mode |

The current `metrics.json` predates this rule and still groups 0–30 m together. Splitting
0–10 m from 20 m-and-below arrives with the evaluation framework v2 (roadmap Phase 3); the web
Profile Explorer already shows an RMSE for 20 m and below next to the all-depth figure.

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
