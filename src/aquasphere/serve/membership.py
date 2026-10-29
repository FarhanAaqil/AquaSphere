"""
Training-set membership for the served model.

The API must be able to say whether a prediction point, or a validation profile, was part of the
data the served model was trained on (blueprint §10.2: validation views show only held-out profiles
and mark any in-training point).

Resolution order:
1. ``train_float_ids`` stored in the checkpoint by the training script (exact).
2. Reconstruct the split the training script uses (float-grouped 80/20, seed from the checkpoint
   config) on the same Argo table: data/processed/argo_profiles.parquet, else the tracked
   data/argo_sst_training.csv, which yields an identical float split.
3. Unknown: membership questions return ``None`` rather than guessing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aquasphere.data.splits import ensure_float_id_column, make_float_grouped_split

logger = logging.getLogger(__name__)

ARGO_TABLES = (
    Path("data/processed/argo_profiles.parquet"),
    Path("data/argo_sst_training.csv"),
)

# A prediction counts as "in training" when a training profile lies in the same 0.25° collocation
# cell (half a cell either way) on the same date.
POINT_TOLERANCE_DEG = 0.125


def _read_table(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


class TrainingMembership:
    """Answers "was this float / point / date in the served model's training split?"."""

    def __init__(
        self,
        train_float_ids: set[str] | None,
        train_points: pd.DataFrame | None,
        source: str,
    ) -> None:
        self.train_float_ids = train_float_ids
        self.source = source
        self._points_by_date: dict[str, np.ndarray] = {}
        if train_points is not None and len(train_points):
            pts = train_points.reset_index(drop=True)
            dates = pts["date"].astype(str).str[:10]
            coords = pts[["lat", "lon"]].to_numpy(dtype=np.float64)
            for date, rows in dates.groupby(dates).indices.items():
                self._points_by_date[str(date)] = coords[rows]

    @property
    def known(self) -> bool:
        return self.train_float_ids is not None

    @classmethod
    def unknown(cls) -> TrainingMembership:
        return cls(None, None, "unknown")

    @classmethod
    def resolve(
        cls,
        checkpoint: dict[str, Any] | None,
        tables: tuple[Path, ...] = ARGO_TABLES,
    ) -> TrainingMembership:
        """Build membership from the checkpoint if it records it, else reconstruct the split."""
        stored = (checkpoint or {}).get("train_float_ids")
        seed = int(((checkpoint or {}).get("config") or {}).get("training", {}).get("seed", 42))

        table_path = next((p for p in tables if p.exists()), None)
        df = None
        if table_path is not None:
            try:
                df = ensure_float_id_column(_read_table(table_path))
                df["float_id"] = df["float_id"].astype(str)
            except Exception as e:  # unreadable table: fall through to unknown
                logger.warning("Could not read Argo table %s for membership: %s", table_path, e)
                df = None

        if stored is not None:
            floats = {str(f) for f in stored}
            points = (
                df[df["float_id"].isin(floats)].reset_index(drop=True) if df is not None else None
            )
            return cls(floats, points, "checkpoint")

        if df is None or table_path is None:
            logger.warning("No Argo table found; training membership is unknown.")
            return cls.unknown()

        # Same call as aquasphere.train.train (float-grouped, 80/20, no test partition).
        train_df, _, _ = make_float_grouped_split(
            df, train_ratio=0.80, val_ratio=0.20, test_ratio=0.0, seed=seed
        )
        floats = set(train_df["float_id"].astype(str).unique())
        logger.info(
            "Reconstructed training membership from %s: %d training floats (seed %d).",
            table_path,
            len(floats),
            seed,
        )
        return cls(
            floats, train_df.reset_index(drop=True), f"reconstructed:{table_path.as_posix()}"
        )

    def float_in_training(self, float_id: Any) -> bool | None:
        if self.train_float_ids is None:
            return None
        return str(float_id) in self.train_float_ids

    def point_in_training(self, lat: float, lon: float, date: str) -> bool | None:
        if self.train_float_ids is None:
            return None
        pts = self._points_by_date.get(str(date)[:10])
        if pts is None or not len(pts):
            return False
        near = (np.abs(pts[:, 0] - lat) <= POINT_TOLERANCE_DEG) & (
            np.abs(pts[:, 1] - lon) <= POINT_TOLERANCE_DEG
        )
        return bool(near.any())
