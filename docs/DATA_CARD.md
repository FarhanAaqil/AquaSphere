# Data Card — AquaSphere

> **Status:** Draft — hashes populated after Phase 3 data download.

## Argo Float Profiles

| Field | Value |
|---|---|
| Source | Argo GDAC via `argopy` / Ifremer ERDDAP |
| Variables | TEMP_ADJUSTED, PSAL_ADJUSTED |
| QC flags kept | 1 (good); 2 (probably good) excluded by default |
| Mode | Delayed-mode adjusted preferred; real-time fallback |
| Time range | 2015–2025 |
| Domain | 5–30°N, 45–105°E |
| Licence | Argo data are freely available (Argo data policy) |

## Satellite Predictors

| Variable | Dataset | Source | Licence |
|---|---|---|---|
| SST | NOAA OISST v2.1 | ERDDAP / NCEI | Public domain |
| SSS | SMAP L3 8-day | NASA PO.DAAC | Public domain |
| SLA + currents | CMEMS DUACS L4 | Copernicus Marine Service | Free registration |
| Winds | ERA5 | Copernicus CDS | Free registration |

## QC Rules

- Profiles must pass position and time QC.
- Profiles missing > 3 of the 15 standard depths are retained with a depth mask (masked loss); **not dropped**.
- A manifest (`data/manifest.json`) records SHA-256 and row counts for every downloaded file.

## Manifest

<!-- DATA_MANIFEST:START -->
*Run `python data/verify_sources.py` then `python -m aquasphere.data.store` to populate.*
<!-- DATA_MANIFEST:END -->
