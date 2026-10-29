"""Checkpoint provenance: recorded at training time, verified before the API reports ready."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch

from aquasphere.data.provenance import (
    DATA_UNAVAILABLE,
    MISMATCH,
    NOT_RECORDED,
    VERIFIED,
    build_provenance,
    file_sha256,
    verify_provenance,
)
from aquasphere.models.decoder import TierAModel
from aquasphere.serve.engine import InferenceEngine


@pytest.fixture()
def data_file(tmp_path: Path) -> Path:
    p = tmp_path / "argo.csv"
    p.write_text("profile_id,lat,lon,date\n111_001,10.0,60.0,2025-05-15\n", encoding="utf-8")
    return p


def test_build_provenance_records_hash_and_seed(data_file: Path) -> None:
    prov = build_provenance(data_file, seed=7)
    assert prov["data_sha256"] == file_sha256(data_file)
    assert prov["seed"] == 7
    assert prov["data_path"].endswith("argo.csv")
    assert "git_sha" in prov and "trained_at" in prov


def test_verify_statuses(data_file: Path) -> None:
    assert verify_provenance(None)[0] == NOT_RECORDED
    assert verify_provenance({})[0] == NOT_RECORDED

    prov = build_provenance(data_file, seed=1)
    assert verify_provenance(prov)[0] == VERIFIED

    data_file.write_text("changed\n", encoding="utf-8")
    status, detail = verify_provenance(prov)
    assert status == MISMATCH
    assert "changed since training" in detail

    assert verify_provenance({**prov, "data_path": "nope/missing.csv"})[0] == DATA_UNAVAILABLE


def _write_checkpoint(path: Path, provenance: dict[str, Any] | None) -> None:
    model = TierAModel(input_dim=18, hidden_dim=128, embed_dim=16, n_depths=15)
    payload: dict[str, Any] = {
        "model_state": model.state_dict(),
        "scaler": {"mean": [0.0] * 18, "std": [1.0] * 18},
        "climatology": np.full((12, 15), 20.0).tolist(),
        "conformal_calibration": {
            "scale_factor": 1.65,
            "nominal_coverage": 0.9,
            "n_calibration_samples": 10,
            "empirical_val_coverage": 0.9,
        },
        "config": {"training": {"seed": 42}},
    }
    if provenance is not None:
        payload["provenance"] = provenance
    torch.save(payload, path)


def test_engine_ready_when_provenance_verifies(tmp_path: Path, data_file: Path) -> None:
    ckpt = tmp_path / "model.pt"
    _write_checkpoint(ckpt, build_provenance(data_file, seed=42))
    engine = InferenceEngine(checkpoint_path=ckpt)
    assert engine.weights == "trained"
    assert engine.provenance_status == VERIFIED
    assert engine.is_ready


def test_engine_refuses_ready_when_training_data_changed(tmp_path: Path, data_file: Path) -> None:
    ckpt = tmp_path / "model.pt"
    _write_checkpoint(ckpt, build_provenance(data_file, seed=42))
    data_file.write_text("tampered\n", encoding="utf-8")
    engine = InferenceEngine(checkpoint_path=ckpt)
    assert engine.provenance_status == MISMATCH
    assert not engine.is_ready


def test_engine_old_checkpoint_without_provenance_is_still_ready(tmp_path: Path) -> None:
    ckpt = tmp_path / "model.pt"
    _write_checkpoint(ckpt, None)
    engine = InferenceEngine(checkpoint_path=ckpt)
    assert engine.provenance_status == NOT_RECORDED
    assert engine.is_ready


def test_engine_without_checkpoint_is_untrained_and_not_ready(tmp_path: Path) -> None:
    engine = InferenceEngine(checkpoint_path=tmp_path / "missing.pt")
    assert engine.weights == "untrained"
    assert not engine.is_ready
    assert engine.model_version.endswith("+untrained")
