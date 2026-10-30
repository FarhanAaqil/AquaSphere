"""
ONNX export and CPU inference for the served Tier A v2 network (roadmap Phase 5, B13).

    python -m aquasphere.serve.onnx_runtime     # writes checkpoints/tier_a_v2/model.onnx

The engine swaps the torch network for onnxruntime only when the exported file exists, the
optional `onnx` extra is installed, and a parity check on fixed inputs agrees with torch to
1e-4 °C. Otherwise it keeps torch. Gradient-based explanations always use torch.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import torch

logger = logging.getLogger(__name__)

PARITY_TOL = 1e-4
OUTPUTS = ("mean", "log_s2", "emb")


def export(net: torch.nn.Module, n_inputs: int, path: Path) -> Path:
    """Export a Tier A network (scalars -> mean, log sigma^2, embedding) with a dynamic batch."""
    net.eval()
    path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        torch.onnx.export(
            net,
            (torch.zeros(2, n_inputs),),
            str(path),
            input_names=["x"],
            output_names=list(OUTPUTS),
            dynamic_axes={"x": {0: "n"}, **{o: {0: "n"} for o in OUTPUTS}},
            opset_version=17,
            dynamo=False,
        )
    return path


class OnnxNet:
    """Drop-in for the v2 _Net forward on Tier A: (scalars, None) -> torch tensors."""

    def __init__(self, path: Path) -> None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        self.path = path

    def __call__(
        self, s: torch.Tensor, p: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        if p is not None:
            raise ValueError("The ONNX export covers the Tier A point model only")
        mean, log_s2, emb = self.session.run(None, {"x": s.detach().numpy().astype(np.float32)})
        return torch.from_numpy(mean), torch.from_numpy(log_s2), torch.from_numpy(emb)

    def eval(self) -> OnnxNet:
        return self


def attach(model: Any, path: Path) -> bool:
    """Swap model.model (a v2 ProfileModel's network) for onnxruntime if it is safe to."""
    if model.cfg.tier != "A" or not path.exists():
        return False
    try:
        onnx_net = OnnxNet(path)
    except Exception as e:  # onnxruntime missing or the file unreadable
        logger.info("ONNX runtime not used (%s); serving with torch", e)
        return False
    rng = np.random.default_rng(0)
    x = torch.tensor(rng.normal(size=(64, len(model.mu) + 7)), dtype=torch.float32)
    with torch.no_grad():
        ref = model.model(x, None)
    got = onnx_net(x)
    worst = max(float((a - b).abs().max()) for a, b in zip(ref, got, strict=True))
    if worst > PARITY_TOL:
        logger.warning("ONNX parity check failed (max diff %.2e); serving with torch", worst)
        return False
    model.torch_model = model.model
    model.model = onnx_net
    logger.info("Serving the Tier A v2 network with onnxruntime (%s)", path)
    return True


def main() -> None:
    from aquasphere.serve.engine import V2_CHECKPOINT
    from aquasphere.train.v2 import FEATURES, ProfileModel

    logging.basicConfig(level=logging.INFO)
    st = torch.load(V2_CHECKPOINT, map_location="cpu", weights_only=True)
    model = ProfileModel.from_state(st)
    out = export(model.model.net, len(FEATURES), V2_CHECKPOINT.with_suffix(".onnx"))
    if not attach(model, out):
        raise SystemExit("exported, but the parity check against torch failed")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
