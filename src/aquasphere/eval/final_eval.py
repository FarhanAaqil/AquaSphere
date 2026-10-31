"""
Final evaluation (roadmap Phase 6): the one run on the 2024-2025 test period.

    python -m aquasphere.eval.final_eval --confirm final-evaluation-once

Tests the frozen hypotheses (docs/hypotheses.yaml) with Holm correction, scores the baseline
ladder and the served model on the test period, and writes docs/results/final_eval.json and
final_eval.md. Every model is fitted on 2015-2022 only (the served model is the Phase 4
checkpoint, calibrated on 2023). The p-value of each hypothesis is the share of float-block
bootstrap replicates in which its falsification criterion holds (docs/hypotheses_deviations.md,
written before this run).

The test partition is read through aquasphere.eval.protocol, which logs the access. This module
refuses to run again once final_eval.json exists.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml

from aquasphere.data import patches as patch_io
from aquasphere.data.collocate_nio import OUTPUT as TABLE
from aquasphere.eval import metrics_v2 as m
from aquasphere.eval.applicability import DissimilarityIndex
from aquasphere.eval.baselines_v2 import LADDER, B4DeepEnsemble, targets
from aquasphere.eval.protocol import UNLOCK_PHRASE, assign, partition
from aquasphere.eval.report_v2 import d20_rmse
from aquasphere.models.patch_cnn import PatchCNNEncoder
from aquasphere.train import conformal_v2 as cv
from aquasphere.train.v2 import ABLATION, PATCH_IN, Config, PatchNorm, ProfileModel

logger = logging.getLogger(__name__)

OUT = Path("docs/results")
CACHE = Path("data/cache/phase4")
HYPOTHESES = Path("docs/hypotheses.yaml")
V2_CHECKPOINT = Path("checkpoints/tier_a_v2/model.pt")  # the served model from Phase 4
SEEDS = (0, 1, 2)
N_BOOT = 2000
ALPHA = 0.05


def _r(x: float | None, n: int = 4) -> float | None:
    return None if x is None or not np.isfinite(x) else round(float(x), n)


class Blocks:
    """Float-block bootstrap over per-float sums, so every statistic resamples the same floats."""

    def __init__(self, floats: np.ndarray, n_boot: int = N_BOOT, seed: int = 0) -> None:
        self.uniq, self.inv = np.unique(floats, return_inverse=True)
        rng = np.random.default_rng(seed)
        self.draws = rng.integers(0, len(self.uniq), size=(n_boot, len(self.uniq)))

    def sums(self, per_row: np.ndarray) -> tuple[float, np.ndarray]:
        """Point total and bootstrap totals of a per-row quantity."""
        per_float = np.bincount(self.inv, weights=per_row, minlength=len(self.uniq))
        return float(per_float.sum()), per_float[self.draws].sum(axis=1)


class Final:
    def __init__(self, n_boot: int, dry: bool = False, quick: bool = False) -> None:
        self.n_boot = n_boot
        # quick (dry runs only): one seed and a few epochs, to exercise every code path fast
        self.seeds = (0,) if quick else SEEDS
        self.quick = quick
        # Dry run: every code path on the 2023 validation year, no unlock, nothing logged
        self.prefix = "dry_" if dry else "final_"
        df = assign(pd.read_parquet(TABLE))
        df["_row"] = np.arange(len(df))
        self.df = df
        self.train = partition(df, "train")
        self.test = (
            partition(df, "val")
            if dry
            else partition(
                df,
                "test",
                unlock=UNLOCK_PHRASE,
                purpose="Phase 6 final evaluation: H1a, H1b, H2, H3, H4 with Holm; E2 ladder on test",
            )
        )
        self.y, self.mask = targets(self.test)
        self.floats = self.test["float_id"].astype(str).to_numpy()
        self.boot = Blocks(self.floats, n_boot)
        self.reg, self.sea = cv.strata(self.test)
        b0 = LADDER["B0"]().fit(self.train).predict(self.test)
        self.err_b0 = self._err(b0)
        self.thermo = m.cols(m.THERMOCLINE)
        logger.info("test partition: %d profiles, %d floats", len(self.test), len(set(self.floats)))

    # ── helpers ─────────────────────────────────────────────────────────────
    def _err(self, pred: np.ndarray) -> np.ndarray:
        return np.where(self.mask, pred - self.y, 0.0)

    def sse(self, pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Per-row thermocline squared-error sum and observation count."""
        e = self._err(pred)[:, self.thermo]
        mk = self.mask[:, self.thermo]
        return (e**2 * mk).sum(axis=1), mk.sum(axis=1).astype(float)

    def rmse_reps(self, pred: np.ndarray) -> tuple[float, np.ndarray]:
        s, n = self.sse(pred)
        (ps, rs), (pn, rn) = self.boot.sums(s), self.boot.sums(n)
        return float(np.sqrt(ps / pn)), np.sqrt(rs / np.maximum(rn, 1))

    def skill_reps(self, pred: np.ndarray) -> tuple[float, np.ndarray]:
        s, _ = self.sse(pred)
        s0, _ = self.sse(self.y + self.err_b0)
        (ps, rs), (p0, r0) = self.boot.sums(s), self.boot.sums(s0)
        return 1 - ps / p0, 1 - rs / np.maximum(r0, 1e-12)

    def summary(self, pred: np.ndarray) -> dict[str, Any]:
        point, reps = self.rmse_reps(pred)
        err = self._err(pred)
        d20, n20 = d20_rmse(self.y, pred)
        return {
            "thermocline_rmse": _r(point),
            "ci": [_r(float(np.percentile(reps, 2.5))), _r(float(np.percentile(reps, 97.5)))],
            "headline_rmse": _r(m.rmse(err, self.mask, m.HEADLINE)),
            "skill_thermocline": _r(m.skill(err, self.err_b0, self.mask, m.THERMOCLINE)),
            "d20_rmse_m": _r(d20, 2),
            "d20_n": n20,
            "bands": m.band_table(err, self.mask),
        }

    def cached(self, name: str, fit: Callable[[], np.ndarray]) -> np.ndarray:
        """Test predictions are cached so a crash mid-run does not force a second read."""
        path = CACHE / f"{self.prefix}{name}.npy"
        if path.exists():
            return np.asarray(np.load(path))
        t0 = time.time()
        pred = fit()
        CACHE.mkdir(parents=True, exist_ok=True)
        np.save(path, pred)
        logger.info("%s: %.0fs", name, time.time() - t0)
        return pred

    # ── models ──────────────────────────────────────────────────────────────
    def served(self) -> dict[str, Any]:
        ck = torch.load(V2_CHECKPOINT, map_location="cpu", weights_only=True)
        model = ProfileModel.from_state(ck)
        out: dict[str, Any] = {"model": model, "version": ck.get("model_version")}
        for mode in ("delayed", "nowcast"):
            mean, sigma, emb = model.predict(self.test, mode=mode)
            mc = cv.MondrianConformal.from_dict(ck["conformal"][mode])
            lo, hi = mc.interval(mean, sigma, self.reg, self.sea)
            out[mode] = {"mean": mean, "sigma": sigma, "emb": emb, "lower": lo, "upper": hi}
        out["di"] = DissimilarityIndex.from_dict(ck["dissimilarity"])
        return out

    def tier_a(self, channels: tuple[str, ...], seed: int) -> np.ndarray:
        cfg = Config(
            epochs=3 if self.quick else 40,
            channels=channels,
            nowcast_share=0.0,
            lambda_grad=0.0,
            lambda_phys=0.0,
        )
        return ProfileModel(cfg).fit(self.train, seed).predict(self.test)[0]

    def patch_model(self, fraction: float, seed: int, pretrained: bool) -> np.ndarray:
        lab = patch_io.load(patch_io.LABELLED)
        unl = patch_io.load(patch_io.UNLABELLED)
        norm = PatchNorm().fit(unl["patches"])
        tr_rows, te_rows = self.train["_row"].to_numpy(), self.test["_row"].to_numpy()
        enc = None
        if pretrained:
            enc = PatchCNNEncoder(in_channels=PATCH_IN)
            path = CACHE / f"encoder_masked_temporal_s{seed}.pt"
            enc.load_state_dict(torch.load(path, weights_only=True))  # pre-trained on 2015-2022
        epochs = 2 if self.quick else round(25 * min(3.0, 1.0 / np.sqrt(fraction)))
        cfg = Config(tier="C" if pretrained else "B", epochs=epochs, label_fraction=fraction)
        model = ProfileModel(cfg).fit(
            self.train,
            seed,
            patches=lab["patches"][tr_rows],
            land=lab["land"][tr_rows],
            patch_norm=norm,
            encoder=enc,
        )
        return model.predict(self.test, patches=lab["patches"][te_rows], land=lab["land"][te_rows])[
            0
        ]

    def ladder(self, key: str, seed: int) -> tuple[np.ndarray, np.ndarray | None]:
        model = LADDER[key]().fit(self.train, seed=seed)
        if isinstance(model, B4DeepEnsemble):
            return model.predict_dist(self.test)
        return model.predict(self.test), None

    def _patch_seed(self, fraction: float, pretrained: bool, seed: int) -> np.ndarray:
        return self.patch_model(fraction, seed, pretrained)

    def _ladder_mean(self, key: str, seed: int) -> np.ndarray:
        return self.ladder(key, seed)[0]

    # ── hypotheses ──────────────────────────────────────────────────────────
    def seed_mean(self, name: str, fn: Callable[[int], np.ndarray]) -> np.ndarray:
        return np.asarray(
            np.mean([self.cached(f"{name}_s{s}", partial(fn, s)) for s in self.seeds], axis=0)
        )

    def h1a(self) -> tuple[dict[str, Any], np.ndarray]:
        a1 = self.seed_mean("A1", lambda s: self.tier_a(ABLATION["A1"], s))
        a2 = self.seed_mean("A2", lambda s: self.tier_a(ABLATION["A2"], s))
        p1, r1 = self.rmse_reps(a1)
        p2, r2 = self.rmse_reps(a2)
        red, reps = 1 - p2 / p1, 1 - r2 / r1
        return {
            "claim": "Adding SLA to SST lowers 50-150 m RMSE by at least 15%.",
            "rmse_sst_only": _r(p1),
            "rmse_sst_sla": _r(p2),
            "reduction": _r(red),
            "ci": [_r(float(np.percentile(reps, 2.5))), _r(float(np.percentile(reps, 97.5)))],
            "threshold": 0.15,
            "p": float(np.mean(reps < 0.15)),
            "meets_threshold": bool(red >= 0.15),
            "diff_ci_excludes_zero": bool(np.percentile(r2 - r1, 97.5) < 0),
        }, reps

    def h1b(self, srv: dict[str, Any]) -> dict[str, Any]:
        pd_, rd = self.skill_reps(srv["delayed"]["mean"])
        pn, rn = self.skill_reps(srv["nowcast"]["mean"])
        ratio, reps = pn / pd_, rn / rd
        return {
            "claim": "Nowcast mode keeps at least 85% of the full-mode thermocline skill score.",
            "skill_delayed": _r(pd_),
            "skill_nowcast": _r(pn),
            "ratio": _r(ratio),
            "ci": [_r(float(np.percentile(reps, 2.5))), _r(float(np.percentile(reps, 97.5)))],
            "threshold": 0.85,
            "p": float(np.mean(reps < 0.85)),
            "meets_threshold": bool(ratio >= 0.85),
        }

    def h2(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "claim": "Pre-training cuts test thermocline RMSE by >= 5% at full labels and >= 10% at 10% of labels.",
            "pretext": "masked+temporal",
        }
        fails = np.zeros(self.n_boot, dtype=bool)
        ok = True
        for frac, thr in ((1.0, 0.05), (0.1, 0.10)):
            tag = f"{int(frac * 100)}"
            scratch = self.seed_mean(f"B_f{tag}", partial(self._patch_seed, frac, False))
            pre = self.seed_mean(f"C_f{tag}", partial(self._patch_seed, frac, True))
            ps, rs = self.rmse_reps(scratch)
            pp, rp = self.rmse_reps(pre)
            red, reps = 1 - pp / ps, 1 - rp / rs
            res[f"labels_{tag}pct"] = {
                "rmse_scratch": _r(ps),
                "rmse_pretrained": _r(pp),
                "reduction": _r(red),
                "ci": [_r(float(np.percentile(reps, 2.5))), _r(float(np.percentile(reps, 97.5)))],
                "threshold": thr,
            }
            fails |= reps < thr
            ok &= bool(red >= thr)
        res["p"] = float(np.mean(fails))
        res["meets_threshold"] = ok
        return res

    def h3(self, srv: dict[str, Any]) -> dict[str, Any]:
        d = srv["delayed"]
        inside = (self.y >= d["lower"]) & (self.y <= d["upper"])
        hit = (inside & self.mask).sum(axis=1).astype(float)
        tot = self.mask.sum(axis=1).astype(float)
        (ph, rh), (pt, rt) = self.boot.sums(hit), self.boot.sums(tot)
        cov, reps = ph / pt, rh / rt
        rows = cv.coverage_by_stratum(
            inside, self.mask, self.reg, self.sea, self.floats, self.n_boot
        )
        status = {
            (r["region"], r["season"]): r["status"]
            for r in json.loads((OUT / "metrics_v2.json").read_text(encoding="utf-8"))["strata"]
        }
        for r in rows:
            r["status"] = status.get((r["region"], r["season"]), "overall")
            r["in_band"] = bool(0.85 <= r["coverage"] <= 0.95) if r["region"] != "All" else None
        conf = [r for r in rows if r["status"] == "confirmatory"]
        _, in_dom = srv["di"].in_domain(d["emb"])
        err = self._err(d["mean"])
        dom = {
            "threshold": _r(srv["di"].threshold),
            "share_inside": _r(float(np.mean(in_dom))),
            "rmse_inside": _r(m.rmse(err[in_dom], self.mask[in_dom], m.THERMOCLINE))
            if in_dom.any()
            else None,
            "rmse_outside": _r(m.rmse(err[~in_dom], self.mask[~in_dom], m.THERMOCLINE))
            if (~in_dom).any()
            else None,
            "profiles_outside": int((~in_dom).sum()),
        }
        return {
            "claim": "Nominal 90% intervals reach 87-93% coverage overall and stay within 85-95% in each region and season; errors inside the applicability domain are lower than outside.",
            "coverage": _r(cov),
            "ci": [_r(float(np.percentile(reps, 2.5))), _r(float(np.percentile(reps, 97.5)))],
            "mean_width": _r(float(np.mean((d["upper"] - d["lower"])[self.mask]))),
            "band": [0.87, 0.93],
            "p": float(np.mean((reps < 0.87) | (reps > 0.93))),
            "meets_threshold": bool(0.87 <= cov <= 0.93) and all(r["in_band"] for r in conf),
            "strata": rows,
            "confirmatory_strata_in_band": all(r["in_band"] for r in conf),
            "applicability": dom,
            "nowcast_coverage": _r(
                float(
                    np.mean(
                        ((self.y >= srv["nowcast"]["lower"]) & (self.y <= srv["nowcast"]["upper"]))[
                            self.mask
                        ]
                    )
                )
            ),
        }

    def h4(self) -> dict[str, Any]:
        blocked = self.seed_mean("B3_blocked", lambda s: self.ladder("B3", s)[0])
        pb, rb = self.rmse_reps(blocked)
        pool = pd.concat([self.train, self.test]).reset_index(drop=True)
        rng = np.random.default_rng(0)
        held = rng.random(len(pool)) < 0.2
        tr, ev = pool[~held], pool[held]
        y, mk = targets(ev)
        preds = []
        for s in self.seeds:
            path = CACHE / f"{self.prefix}B3_random_s{s}.npy"
            if path.exists():
                preds.append(np.load(path))
            else:
                p = LADDER["B3"]().fit(tr, seed=s).predict(ev)
                np.save(path, p)
                preds.append(p)
        pr = np.mean(preds, axis=0)
        boot = Blocks(ev["float_id"].astype(str).to_numpy(), self.n_boot, seed=1)
        e = np.where(mk, pr - y, 0.0)[:, self.thermo]
        mt = mk[:, self.thermo]
        (ps, rs), (pn, rn) = (
            boot.sums((e**2 * mt).sum(axis=1)),
            boot.sums(mt.sum(axis=1).astype(float)),
        )
        prand, rrand = float(np.sqrt(ps / pn)), np.sqrt(rs / np.maximum(rn, 1))
        gap, reps = (pb - prand) / pb, (rb - rrand) / rb
        return {
            "claim": "The random-split RMSE of the current baseline is at least 20% lower than its blocked-split RMSE at 50-150 m.",
            "model": "B3",
            "rmse_blocked": _r(pb),
            "rmse_random": _r(prand),
            "gap": _r(gap),
            "ci": [_r(float(np.percentile(reps, 2.5))), _r(float(np.percentile(reps, 97.5)))],
            "threshold": 0.20,
            "p": float(np.mean(reps < 0.20)),
            "meets_threshold": bool(gap >= 0.20),
            "random_pool": {"train": len(tr), "eval": len(ev)},
        }

    def ladder_table(self, srv: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in LADDER:
            seeds = (0,) if key in ("B0", "B1") else self.seeds
            preds = [self.cached(f"{key}_s{s}", partial(self._ladder_mean, key, s)) for s in seeds]
            out[key] = {
                "name": LADDER[key].name if hasattr(LADDER[key], "name") else key,
                **self.summary(np.mean(preds, axis=0)),
            }
        out["Tier A v2"] = {
            "name": f"AquaSphere {srv['version']} (served)",
            **self.summary(srv["delayed"]["mean"]),
        }
        out["Tier A v2 nowcast"] = {
            "name": "AquaSphere, nowcast mode",
            **self.summary(srv["nowcast"]["mean"]),
        }
        return out


def holm(results: dict[str, dict[str, Any]]) -> None:
    order = sorted(results, key=lambda k: results[k]["p"])
    running = 0.0
    n = len(order)
    for i, k in enumerate(order):
        adj = min(1.0, (n - i) * results[k]["p"])
        running = max(running, adj)
        results[k]["p_holm"] = round(running, 4)
        results[k]["p"] = round(results[k]["p"], 4)
        results[k]["supported"] = bool(running < ALPHA and results[k]["meets_threshold"])


def markdown(r: dict[str, Any]) -> str:
    h = r["hypotheses"]

    def ci(c: list[Any]) -> str:
        return f"{c[0]:.3f} to {c[1]:.3f}"

    def pci(c: list[Any]) -> str:
        return f"{c[0]:.1%} to {c[1]:.1%}"

    lines = [
        "# Final evaluation: 2024-2025 test period (read once)",
        "",
        f"Run at {r['generated_at']} on {r['split']['test_profiles']} test profiles from {r['split']['test_floats']} floats "
        "that never appear in training or calibration. Every model was fitted on 2015-2022; the served model was "
        f"calibrated on 2023. p is the share of {r['n_boot']} float-block bootstrap replicates in which the hypothesis's "
        "falsification criterion holds; Holm-adjusted over the five (docs/hypotheses_deviations.md).",
        "",
        "## Confirmatory hypotheses",
        "",
        "| Hypothesis | Estimate | 95% CI | Threshold | p | p (Holm) | Result |",
        "|---|---|---|---|---|---|---|",
        f"| H1a SLA adds to SST | {h['H1a']['reduction']:.1%} RMSE reduction | {pci(h['H1a']['ci'])} | >= 15% | {h['H1a']['p']} | {h['H1a']['p_holm']} | {'supported' if h['H1a']['supported'] else 'not supported'} |",
        f"| H1b nowcast skill kept | ratio {h['H1b']['ratio']} | {ci(h['H1b']['ci'])} | >= 0.85 | {h['H1b']['p']} | {h['H1b']['p_holm']} | {'supported' if h['H1b']['supported'] else 'not supported'} |",
        f"| H2 pre-training | {h['H2']['labels_100pct']['reduction']:.1%} (100%), {h['H2']['labels_10pct']['reduction']:.1%} (10%) | {pci(h['H2']['labels_100pct']['ci'])}; {pci(h['H2']['labels_10pct']['ci'])} | >= 5%, >= 10% | {h['H2']['p']} | {h['H2']['p_holm']} | {'supported' if h['H2']['supported'] else 'not supported'} |",
        f"| H3 calibrated 90% intervals | {h['H3']['coverage']:.1%} coverage | {pci(h['H3']['ci'])} | 87-93%; strata 85-95% | {h['H3']['p']} | {h['H3']['p_holm']} | {'supported' if h['H3']['supported'] else 'not supported'} |",
        f"| H4 random-split optimism | {h['H4']['gap']:.1%} gap (B3) | {pci(h['H4']['ci'])} | >= 20% | {h['H4']['p']} | {h['H4']['p_holm']} | {'supported' if h['H4']['supported'] else 'not supported'} |",
        "",
        "## Test-period ladder (thermocline RMSE, 95% CI over floats)",
        "",
        "| Model | Thermocline RMSE | 95% CI | Skill vs B0 | >= 20 m RMSE | D20 RMSE (m) |",
        "|---|---|---|---|---|---|",
    ]
    for k, v in r["ladder"].items():
        lines.append(
            f"| {k} | {v['thermocline_rmse']:.3f} | {ci(v['ci'])} | {v['skill_thermocline']:+.3f} | {v['headline_rmse']:.3f} | {v['d20_rmse_m']} |"
        )
    lines += [
        "",
        "## H3 coverage by region and season",
        "",
        "| Region | Season | Profiles | Floats | Coverage | 95% CI | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in h["H3"]["strata"]:
        lines.append(
            f"| {s['region']} | {s['season']} | {s['profiles']} | {s['floats']} | {s['coverage']:.1%} | {s['ci_low']:.1%} to {s['ci_high']:.1%} | {s['status']} |"
        )
    ap = h["H3"]["applicability"]
    lines += [
        "",
        f"Applicability domain on test: {ap['share_inside']:.1%} inside; thermocline RMSE {ap['rmse_inside']} °C inside, {ap['rmse_outside']} °C outside ({ap['profiles_outside']} profiles).",
        "",
        "Results are reported whether or not they support the hypotheses. Exploratory comparisons are not confirmatory.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", default="", help=f"must be '{UNLOCK_PHRASE}' for the real run")
    ap.add_argument("--dry-run", action="store_true", help="run every step on 2023 instead")
    ap.add_argument("--quick", action="store_true", help="with --dry-run: one seed, few epochs")
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    a = ap.parse_args()
    out = CACHE / "dry" if a.dry_run else OUT
    if not a.dry_run:
        if a.confirm != UNLOCK_PHRASE:
            raise SystemExit("The test period is read once; pass --confirm with the unlock phrase.")
        if (OUT / "final_eval.json").exists():
            raise SystemExit(
                "docs/results/final_eval.json exists: the test period was already evaluated."
            )
    if a.quick and not a.dry_run:
        raise SystemExit("--quick is only for dry runs")
    # The frozen file is kept locally (git tag hypotheses-v1-2026-10-29 holds the committed copy)
    frozen = yaml.safe_load(HYPOTHESES.read_text(encoding="utf-8")) if HYPOTHESES.exists() else {}
    run = Final(a.n_boot, dry=a.dry_run, quick=a.quick)
    srv = run.served()
    hyp = {
        "H1a": run.h1a()[0],
        "H1b": run.h1b(srv),
        "H2": run.h2(),
        "H3": run.h3(srv),
        "H4": run.h4(),
    }
    holm(hyp)
    result = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "hypotheses_file": {"frozen_at": frozen.get("frozen_at"), "status": frozen.get("status")},
        "split": {
            "train_profiles": len(run.train),
            "test_profiles": len(run.test),
            "test_floats": len(set(run.floats)),
        },
        "n_boot": a.n_boot,
        "hypotheses": hyp,
        "ladder": run.ladder_table(srv),
    }
    result["dry_run"] = a.dry_run
    out.mkdir(parents=True, exist_ok=True)
    (out / "final_eval.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (out / "final_eval.md").write_text(markdown(result), encoding="utf-8")
    logger.info("wrote %s/final_eval.json and final_eval.md", out.as_posix())


if __name__ == "__main__":
    main()
