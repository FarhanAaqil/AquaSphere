"""
Applicability domain in embedding space (blueprint §9.5, following Meyer & Pebesma 2021).

    DI(e) = d(e, nearest training embedding) / mean nearest-neighbour distance among training
            embeddings

The threshold comes from training-fold statistics: training floats are split into folds, each
fold's DI is computed against the other folds, and the threshold is the upper whisker
(Q3 + 1.5 IQR) of those values. Predictions above it are flagged outside the applicability
domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.neighbors import NearestNeighbors

MAX_REFERENCE = 20000  # embeddings kept for serving; a seeded subsample beyond this


def _nn_distance(ref: np.ndarray, query: np.ndarray, exclude_self: bool = False) -> np.ndarray:
    nn = NearestNeighbors(n_neighbors=2 if exclude_self else 1).fit(ref)
    d, _ = nn.kneighbors(query)
    return np.asarray(d[:, 1] if exclude_self else d[:, 0], dtype=np.float64)


@dataclass
class DissimilarityIndex:
    reference: np.ndarray | None = None
    mean_nn: float = 1.0
    threshold: float = np.inf
    fold_di: np.ndarray | None = None

    def fit(
        self, emb: np.ndarray, floats: np.ndarray, folds: int = 5, seed: int = 0
    ) -> DissimilarityIndex:
        rng = np.random.default_rng(seed)
        self.mean_nn = float(np.mean(_nn_distance(emb, emb, exclude_self=True)))
        uniq = np.unique(floats)
        fold_of = dict(zip(rng.permutation(uniq), np.arange(len(uniq)) % folds, strict=True))
        fold = np.array([fold_of[f] for f in floats])
        di = np.empty(len(emb))
        for k in range(folds):
            held = fold == k
            di[held] = _nn_distance(emb[~held], emb[held]) / self.mean_nn
        q1, q3 = np.percentile(di, [25, 75])
        self.threshold = float(q3 + 1.5 * (q3 - q1))
        self.fold_di = di
        keep = (
            rng.choice(len(emb), MAX_REFERENCE, replace=False)
            if len(emb) > MAX_REFERENCE
            else np.arange(len(emb))
        )
        self.reference = emb[keep].astype(np.float32)
        return self

    def __call__(self, emb: np.ndarray) -> np.ndarray:
        if self.reference is None:
            raise RuntimeError("DissimilarityIndex is not fitted")
        return _nn_distance(self.reference, emb) / self.mean_nn

    def in_domain(self, emb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        di = self(emb)
        return di, di <= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": None if self.reference is None else self.reference.tolist(),
            "mean_nn": self.mean_nn,
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DissimilarityIndex:
        ref = d.get("reference")
        return cls(
            reference=None if ref is None else np.asarray(ref, dtype=np.float32),
            mean_nn=float(d["mean_nn"]),
            threshold=float(d["threshold"]),
        )
