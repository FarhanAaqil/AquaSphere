"""
Source verification script for AquaSphere (SIH 26066).

Checks dataset IDs and metadata from configs/data.yaml before downloading,
preventing incorrect dataset ID bugs and registering known assets in data/manifest.json.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from aquasphere.data.manifest import DataManifest, verify_erddap_dataset

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("verify_sources")


def verify_all_sources(config_path: Path | str = "configs/data.yaml") -> None:
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        logger.error("Configuration file %s does not exist.", cfg_file)
        return

    with open(cfg_file, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    manifest = DataManifest(manifest_path=cfg.get("manifest", {}).get("path", "data/manifest.json"))

    # Register local Argo training CSV if present
    training_csv = Path("data/argo_sst_training.csv")
    if training_csv.exists():
        manifest.register_artifact(
            name="argo_sst_training_csv",
            file_path=training_csv,
            description="Real Argo profiles collocated with NOAA OISST v2.1 for North Indian Ocean (v1 baseline snapshot).",
            source_url="https://argovis-api.colorado.edu",
            date_range=("2025-03-25", "2025-09-15"),
            row_count=2253,
        )

    # Satellite sources check
    sat_cfg = cfg.get("satellite", {}).get("variables", {})
    print("\n" + "=" * 70)
    print("  AQUASPHERE DATA PIPELINE — SOURCE VERIFICATION")
    print("=" * 70)

    # 1. SST Check (NOAA OISST v2.1)
    sst_id = sat_cfg.get("sst", {}).get("primary", "ncdc_oisst_v2_avhrr_by_time_zlev_lat_lon")
    print(f"[*] Checking Primary SST dataset: {sst_id}")
    sst_res = verify_erddap_dataset(
        sst_id,
        base_url="https://www.ncei.noaa.gov/erddap/info",
        expected_variable="sst",
        timeout_s=6.0,
    )
    status_icon = "[OK]" if sst_res["verified"] else "[OFFLINE/FALLBACK]"
    print(f"    Status: {status_icon} - {sst_res['notes']}")

    # 2. SSS (SMAP) Check
    sss_id = sat_cfg.get("sss", {}).get("primary", "jplSMAP_L3_SSS_8day")
    print(f"[*] Checking Primary SSS dataset: {sss_id}")
    sss_res = verify_erddap_dataset(
        sss_id,
        base_url="https://coastwatch.pfeg.noaa.gov/erddap/info",
        expected_variable="sss",
        timeout_s=6.0,
    )
    status_icon = "[OK]" if sss_res["verified"] else "[OFFLINE/FALLBACK]"
    print(f"    Status: {status_icon} - {sss_res['notes']}")

    print("=" * 70)
    manifest.save()
    print(f"Manifest written to: {manifest.manifest_path}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify remote data sources")
    parser.add_argument("--config", default="configs/data.yaml", help="Path to data config YAML")
    args = parser.parse_args()
    verify_all_sources(args.config)
