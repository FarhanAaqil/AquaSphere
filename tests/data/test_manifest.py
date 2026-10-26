"""
Unit tests for data provenance, manifest tracking, and source verification (SIH 26066).
"""

from pathlib import Path

import pytest

from aquasphere.data.manifest import DataManifest, compute_file_sha256, verify_erddap_dataset


def test_compute_file_sha256(tmp_path: Path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("AquaSphere Ocean Data", encoding="utf-8")

    hash1 = compute_file_sha256(test_file)
    assert isinstance(hash1, str)
    assert len(hash1) == 64

    # Identical content yields identical hash
    test_file2 = tmp_path / "sample_copy.txt"
    test_file2.write_text("AquaSphere Ocean Data", encoding="utf-8")
    assert compute_file_sha256(test_file2) == hash1

    # Missing file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        compute_file_sha256(tmp_path / "non_existent.txt")


def test_data_manifest_registration_and_verification(tmp_path: Path):
    manifest_file = tmp_path / "manifest.json"
    dummy_data = tmp_path / "test_data.csv"
    dummy_data.write_text("id,val\n1,10\n2,20\n", encoding="utf-8")

    manifest = DataManifest(manifest_path=manifest_file)
    entry = manifest.register_artifact(
        name="test_data",
        file_path=dummy_data,
        description="Test dataset",
        row_count=2,
    )

    assert "sha256" in entry
    assert manifest_file.exists()
    assert manifest.verify_artifact("test_data")

    # Reload from disk
    manifest2 = DataManifest(manifest_path=manifest_file)
    assert manifest2.verify_artifact("test_data")

    # Tampering test: modify content -> verification must fail
    dummy_data.write_text("id,val\n1,10\n2,999\n", encoding="utf-8")
    assert not manifest2.verify_artifact("test_data")


def test_verify_erddap_dataset_error_handling():
    # Invalid endpoint / non-existent host should handle gracefully
    res = verify_erddap_dataset(
        dataset_id="non_existent_dataset_12345",
        base_url="https://invalid-host-for-test.example.com",
        timeout_s=0.5,
    )
    assert not res["verified"]
    assert "failed" in res["notes"]
