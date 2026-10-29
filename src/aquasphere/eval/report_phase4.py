"""
Roadmap Phase 4: model and uncertainty experiments on the validation year (2023) only.

    python -m aquasphere.eval.report_phase4            # everything (~1-2 h on CPU)
    python -m aquasphere.eval.report_phase4 --quick    # 1 seed, few epochs: plumbing check only

    physics  Tier A with and without the gradient and anti-inversion terms (choose the loss)
    E3       sensor ablation: SST, +SLA, +SSS, +wind/currents, and all sensors without SSS
    E4       Tier A point features vs Tier B 9x9 patch encoder
    E5       scratch vs pre-trained (masked; masked + temporal) at 10/25/50/100% of labels
    E6       calibration: heteroscedastic vs seed ensemble vs global vs Mondrian conformal; DI
    E7       nowcast (SST + SLA) vs delayed (all sensors) from the same model

It also trains the served Tier A v2 model, calibrates it on 2023 (Mondrian, per mode), fits the
dissimilarity index on training embeddings and writes checkpoints/tier_a_v2/model.pt.

Outputs docs/results/phase4.json and phase4.md. Predictions of every run are cached under
data/cache/phase4 so the report can be rebuilt without retraining. The 2024-2025 test
partition is never read.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from aquasphere.data import patches as patch_io
from aquasphere.data.collocate_nio import OUTPUT as TABLE
from aquasphere.data.provenance import build_provenance
from aquasphere.eval import metrics_v2 as m
from aquasphere.eval.applicability import DissimilarityIndex
from aquasphere.eval.baselines_v2 import B0Climatology, targets
from aquasphere.eval.protocol import assign, partition
from aquasphere.train import conformal_v2 as cv
from aquasphere.train.v2 import ABLATION, MODES, Config, PatchNorm, ProfileModel, pretrain

logger = logging.getLogger(__name__)

OUT = Path("docs/results")
CACHE = Path("data/cache/phase4")
CHECKPOINT = Path("checkpoints/tier_a_v2/model.pt")
SEEDS = (0, 1, 2)
FRACTIONS = (0.1, 0.25, 0.5, 1.0)
H2_FULL, H2_LOW = 0.05, 0.10  # frozen H2 thresholds (docs/hypotheses.yaml)
COVERAGE_BAND = (0.85, 0.95)  # Phase 4 gate, per stratum, on validation


def _r(x: float | None, n: int = 4) -> float | None:
    return None if x is None or not np.isfinite(x) else round(float(x), n)


class Runner:
    def __init__(self, quick: bool, n_boot: int) -> None:
        self.quick = quick
        self.n_boot = n_boot
        self.seeds = (0,) if quick else SEEDS
        df = assign(pd.read_parquet(TABLE))
        df["_row"] = np.arange(len(df))
        self.train = partition(df, "train")
        self.val = partition(df, "val")
        self.y, self.mask = targets(self.val)
        self.groups = self.val["float_id"].astype(str).to_numpy()
        self.reg, self.sea = cv.strata(self.val)
        lab = patch_io.load(patch_io.LABELLED)
        if not np.array_equal(lab["profile_id"], df["profile_id"].astype(str).to_numpy()):
            raise ValueError("patches_nio.npz is out of date: run `make data-patches`")
        self.p_all, self.land_all = lab["patches"], lab["land"]
        unl = patch_io.load(patch_io.UNLABELLED)
        self.unl, self.unl_land = unl["patches"], unl["land"]
        self.norm = PatchNorm().fit(self.unl)  # training-year patches only
        b0 = B0Climatology().fit(self.train).predict(self.val)
        self.err_b0 = self._err(b0)
        CACHE.mkdir(parents=True, exist_ok=True)

    # ── helpers ─────────────────────────────────────────────────────────────
    def _err(self, pred: np.ndarray) -> np.ndarray:
        return np.where(self.mask, pred - self.y, 0.0)

    def _patches(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        rows = df["_row"].to_numpy()
        return {"patches": self.p_all[rows], "land": self.land_all[rows]}

    def epochs(self, base: int, fraction: float = 1.0) -> int:
        """Fewer labels -> more passes, the same rule for every arm (equal tuning budget)."""
        if self.quick:
            return 3
        return round(base * min(3.0, 1.0 / math.sqrt(fraction)))

    def run(
        self, name: str, fit: Callable[[], ProfileModel], modes: tuple[str, ...] = ("delayed",)
    ) -> dict[str, np.ndarray]:
        """Validation predictions per mode, cached on disk by run name."""
        path = CACHE / f"{name}{'_quick' if self.quick else ''}.npz"
        if path.exists():
            with np.load(path) as z:
                return {k: z[k] for k in z.files}
        t0 = time.time()
        model = fit()
        tier_b = model.cfg.tier != "A"
        out: dict[str, np.ndarray] = {}
        for mode in modes:
            kw = self._patches(self.val) if tier_b else {}
            mean, sigma, _ = model.predict(self.val, mode=mode, **kw)
            out[f"{mode}_mean"], out[f"{mode}_sigma"] = mean, sigma
        np.savez(path, **out)  # type: ignore[arg-type]
        logger.info("%s: %.0fs", name, time.time() - t0)
        return out

    def summary(self, pred: np.ndarray) -> dict[str, Any]:
        err = self._err(pred)
        boot = m.bootstrap_rmse(err, self.mask, self.groups, m.THERMOCLINE, self.n_boot)
        return {
            "thermocline_rmse": _r(boot["rmse"]),
            "ci": [_r(boot["ci_low"]), _r(boot["ci_high"])],
            "headline_rmse": _r(m.rmse(err, self.mask, m.HEADLINE)),
            "skill_thermocline": _r(m.skill(err, self.err_b0, self.mask, m.THERMOCLINE)),
            "bands": m.band_table(err, self.mask),
        }

    def by_stratum(self, pred: np.ndarray) -> list[dict[str, Any]]:
        err = self._err(pred)
        rows = []
        for r in ("Arabian Sea", "Bay of Bengal"):
            for s in ("NE monsoon", "Inter-monsoon", "SW monsoon"):
                sel = (self.reg == r) & (self.sea == s)
                if sel.any():
                    rows.append(
                        {
                            "region": r,
                            "season": s,
                            "profiles": int(sel.sum()),
                            "floats": len(np.unique(self.groups[sel])),
                            "thermocline_rmse": _r(m.rmse(err[sel], self.mask[sel], m.THERMOCLINE)),
                            "skill": _r(
                                m.skill(err[sel], self.err_b0[sel], self.mask[sel], m.THERMOCLINE)
                            ),
                        }
                    )
        return rows

    def paired(self, a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
        """RMSE(a) - RMSE(b) at the thermocline, relative to RMSE(b), float-block bootstrap."""
        d = m.paired_rmse_difference(
            self._err(a), self._err(b), self.mask, self.groups, m.THERMOCLINE, self.n_boot
        )
        base = m.rmse(self._err(b), self.mask, m.THERMOCLINE)
        return {
            "diff_c": _r(d["diff"]),
            "ci": [_r(d["ci_low"]), _r(d["ci_high"])],
            "p": _r(d["p"]),
            "relative": _r(d["diff"] / base),
        }

    def seed_mean(self, runs: list[dict[str, np.ndarray]], key: str = "delayed_mean") -> np.ndarray:
        return np.asarray(np.mean([r[key] for r in runs], axis=0))

    def per_seed(
        self, runs: list[dict[str, np.ndarray]], key: str = "delayed_mean"
    ) -> dict[str, Any]:
        vals = [m.rmse(self._err(r[key]), self.mask, m.THERMOCLINE) for r in runs]
        return {"mean": _r(float(np.mean(vals))), "std": _r(float(np.std(vals)))}

    def fit_a(self, cfg: Config, seed: int) -> ProfileModel:
        return ProfileModel(cfg).fit(self.train, seed)

    # ── experiments ─────────────────────────────────────────────────────────
    def physics(self) -> tuple[dict[str, Any], Config]:
        arms = {
            "with": Config(epochs=self.epochs(40)),
            "without": Config(epochs=self.epochs(40), lambda_grad=0.0, lambda_phys=0.0),
        }
        out: dict[str, Any] = {}
        preds = {}
        for k, cfg in arms.items():
            runs = [self.run(f"physics_{k}_s{s}", partial(self.fit_a, cfg, s)) for s in self.seeds]
            preds[k] = self.seed_mean(runs)
            out[k] = {**self.summary(preds[k]), "seeds": self.per_seed(runs)}
        out["with_minus_without"] = self.paired(preds["with"], preds["without"])
        chosen = (
            "with"
            if out["with"]["thermocline_rmse"] <= out["without"]["thermocline_rmse"]
            else "without"
        )
        out["chosen"] = chosen
        return out, arms[chosen]

    def e3(self, base: Config) -> dict[str, Any]:
        configs = {**ABLATION, "A4-noSSS": tuple(c for c in ABLATION["A4"] if c != "sss")}
        labels = {
            "A1": "SST",
            "A2": "SST + SLA",
            "A3": "SST + SLA + SSS",
            "A4": "All sensors",
            "A4-noSSS": "All sensors except SSS",
        }
        preds, out = {}, {}
        for k, chans in configs.items():
            cfg = replace(base, channels=chans, nowcast_share=0.0)
            runs = [self.run(f"e3_{k}_s{s}", partial(self.fit_a, cfg, s)) for s in self.seeds]
            preds[k] = self.seed_mean(runs)
            out[k] = {
                "label": labels[k],
                "channels": list(chans),
                **self.summary(preds[k]),
                "seeds": self.per_seed(runs),
                "strata": self.by_stratum(preds[k]),
            }
        steps = [("A2", "A1"), ("A3", "A2"), ("A4", "A3"), ("A4", "A4-noSSS")]
        return {
            "configs": out,
            "steps": {f"{a} vs {b}": self.paired(preds[a], preds[b]) for a, b in steps},
            "h1a_direction_validation": self.paired(preds["A2"], preds["A1"])["relative"],
        }

    def tier_b(
        self, fraction: float, seed: int, encoder_variant: str | None
    ) -> dict[str, np.ndarray]:
        tag = "scratch" if encoder_variant is None else encoder_variant.replace("+", "_")
        name = f"e5_{tag}_f{int(fraction * 100)}_s{seed}"

        def fit() -> ProfileModel:
            enc = None
            if encoder_variant is not None:
                enc = self.encoder(encoder_variant, seed)
            cfg = Config(
                tier="B" if enc is None else "C",
                epochs=self.epochs(25, fraction),
                label_fraction=fraction,
            )
            return ProfileModel(cfg).fit(
                self.train, seed, patch_norm=self.norm, encoder=enc, **self._patches(self.train)
            )

        return self.run(name, fit)

    def encoder(self, variant: str, seed: int) -> Any:
        path = (
            CACHE
            / f"encoder_{variant.replace('+', '_')}_s{seed}{'_quick' if self.quick else ''}.pt"
        )
        from aquasphere.models.patch_cnn import PatchCNNEncoder
        from aquasphere.train.v2 import PATCH_IN

        enc = PatchCNNEncoder(in_channels=PATCH_IN)
        if path.exists():
            enc.load_state_dict(torch.load(path, weights_only=True))
            return enc
        trained, losses = pretrain(
            self.unl,
            self.unl_land,
            self.norm,
            variant=variant,
            epochs=2 if self.quick else 15,
            seed=seed,
        )
        torch.save(trained.state_dict(), path)
        (path.with_suffix(".json")).write_text(json.dumps({"loss": losses}))
        return trained

    def e4_e5(self, tier_a: np.ndarray) -> tuple[dict[str, Any], dict[str, Any]]:
        arms = {"scratch": None, "masked": "masked", "masked+temporal": "masked+temporal"}
        curves: dict[str, Any] = {}
        preds: dict[tuple[str, float], np.ndarray] = {}
        for arm, variant in arms.items():
            curves[arm] = []
            for f in FRACTIONS:
                runs = [self.tier_b(f, s, variant) for s in self.seeds]
                preds[(arm, f)] = self.seed_mean(runs)
                curves[arm].append(
                    {
                        "fraction": f,
                        "thermocline_rmse": _r(
                            m.rmse(self._err(preds[(arm, f)]), self.mask, m.THERMOCLINE)
                        ),
                        "seeds": self.per_seed(runs),
                    }
                )
        e4 = {
            "tier_a": self.summary(tier_a),
            "tier_b": self.summary(preds[("scratch", 1.0)]),
            "b_minus_a": self.paired(preds[("scratch", 1.0)], tier_a),
            "note": "Tier B is the scratch arm of E5 at 100% of labels (identical architecture).",
        }
        gains = {}
        for arm in ("masked", "masked+temporal"):
            gains[arm] = {
                f"{int(f * 100)}%": self.paired(preds[(arm, f)], preds[("scratch", f)])
                for f in FRACTIONS
            }
        # Go/no-go on H2 at validation: relative reduction vs scratch at 100% and 10% of labels
        best_arm = min(
            ("masked", "masked+temporal"), key=lambda a: gains[a]["100%"]["relative"] or 0.0
        )
        full = -(gains[best_arm]["100%"]["relative"] or 0.0)
        low = -(gains[best_arm]["10%"]["relative"] or 0.0)
        go = full >= H2_FULL and low >= H2_LOW
        e5 = {
            "curves": curves,
            "pretrained_minus_scratch": gains,
            "h2_validation": {
                "best_pretext": best_arm,
                "reduction_full_labels": _r(full),
                "reduction_10pct_labels": _r(low),
                "thresholds": {"full": H2_FULL, "10%": H2_LOW},
                "decision": "go" if go else "no-go",
            },
        }
        return e4, e5

    def e6_e7(self, cfg: Config) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Served model (seed 0) plus seeds 1-2 for the seed-ensemble comparison."""
        models: dict[int, ProfileModel] = {}

        def fit(s: int) -> ProfileModel:
            models[s] = ProfileModel(cfg).fit(self.train, s)
            return models[s]

        runs = [
            self.run(f"served_s{s}", partial(fit, s), modes=("delayed", "nowcast"))
            for s in self.seeds
        ]
        served = models.get(0) or ProfileModel(cfg).fit(self.train, 0)
        d_mean, d_sig = runs[0]["delayed_mean"], runs[0]["delayed_sigma"]
        n_mean = runs[0]["nowcast_mean"]

        # E7: skill retained in nowcast mode
        sk_d = m.skill(self._err(d_mean), self.err_b0, self.mask, m.THERMOCLINE)
        sk_n = m.skill(self._err(n_mean), self.err_b0, self.mask, m.THERMOCLINE)
        rng = np.random.default_rng(0)
        blocks = [np.flatnonzero(self.groups == g) for g in np.unique(self.groups)]
        ratios = []
        for _ in range(self.n_boot):
            idx = np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))])
            ed, en, eb = self._err(d_mean)[idx], self._err(n_mean)[idx], self.err_b0[idx]
            mk = self.mask[idx]
            sd_ = m.skill(ed, eb, mk, m.THERMOCLINE)
            ratios.append(m.skill(en, eb, mk, m.THERMOCLINE) / sd_ if sd_ > 0 else np.nan)
        e7 = {
            "delayed": self.summary(d_mean),
            "nowcast": self.summary(n_mean),
            "skill_delayed": _r(sk_d),
            "skill_nowcast": _r(sk_n),
            "skill_ratio": _r(sk_n / sk_d if sk_d > 0 else float("nan")),
            "skill_ratio_ci": [
                _r(float(np.nanpercentile(ratios, 2.5))),
                _r(float(np.nanpercentile(ratios, 97.5))),
            ],
            "h1b_threshold": 0.85,
            "nowcast_minus_delayed": self.paired(n_mean, d_mean),
            "preliminary_sst": (
                "Not run. ERDDAP keeps the preliminary OISST release only until the final one "
                "replaces it (about two weeks), so 2023 preliminary fields no longer exist to "
                "download. E7 here uses final OISST in both modes; the preliminary-release run "
                "needs a prospective archive (blueprint's optional 2026 shadow test)."
            ),
        }

        # E6: calibration comparison on 2023, coverage by cross-conformal folds over floats
        scores = np.abs(self.y - d_mean) / np.maximum(d_sig, 1e-6)
        scores = np.where(self.mask, scores, np.nan)
        methods: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        z90 = 1.645
        methods["heteroscedastic"] = (d_mean, z90 * d_sig)
        if len(runs) > 1:
            means = np.stack([r["delayed_mean"] for r in runs])
            var = (
                np.mean(np.stack([r["delayed_sigma"] for r in runs]) ** 2 + means**2, axis=0)
                - means.mean(0) ** 2
            )
            methods["seed_ensemble"] = (means.mean(0), z90 * np.sqrt(np.maximum(var, 1e-12)))
        q_g = cv.cross_conformal(scores, self.mask, self.reg, self.sea, self.groups, mondrian=False)
        q_m = cv.cross_conformal(scores, self.mask, self.reg, self.sea, self.groups, mondrian=True)
        methods["conformal_global"] = (d_mean, q_g * d_sig)
        methods["conformal_mondrian"] = (d_mean, q_m * d_sig)
        e6: dict[str, Any] = {"methods": {}}
        for k, (mu, half) in methods.items():
            inside = np.abs(self.y - mu) <= half
            cov = cv.coverage_by_stratum(
                inside, self.mask, self.reg, self.sea, self.groups, self.n_boot
            )
            sig_equiv = half / z90
            e6["methods"][k] = {
                "coverage": cov,
                "mean_width": _r(float(np.mean((2 * half)[self.mask]))),
                "crps_thermocline": _r(
                    float(
                        np.mean(
                            m.crps_gaussian(self.y, mu, sig_equiv)[:, m.cols(m.THERMOCLINE)][
                                self.mask[:, m.cols(m.THERMOCLINE)]
                            ]
                        )
                    )
                ),
            }
        # Reliability: raw Gaussian levels vs Mondrian conformal fitted at each level
        levels = list(m.RELIABILITY_LEVELS)
        conf_emp = []
        for p in levels:
            q = cv.cross_conformal(scores, self.mask, self.reg, self.sea, self.groups, alpha=1 - p)
            conf_emp.append(float(np.mean((scores <= q)[self.mask])))
        e6["reliability"] = {
            "nominal": levels,
            "heteroscedastic": m.reliability(self.y, d_mean, d_sig, self.mask, levels)["empirical"],
            "conformal_mondrian": conf_emp,
        }
        status = self.stratum_status()
        mond = e6["methods"]["conformal_mondrian"]["coverage"]
        for row in mond:
            row["status"] = status.get((row["region"], row["season"]), "overall")
        e6["gate"] = {
            "band": list(COVERAGE_BAND),
            "every_stratum_in_band": all(
                COVERAGE_BAND[0] <= r["coverage"] <= COVERAGE_BAND[1] for r in mond
            ),
            "confirmatory_strata_in_band": all(
                COVERAGE_BAND[0] <= r["coverage"] <= COVERAGE_BAND[1]
                for r in mond
                if r["status"] in ("confirmatory", "overall")
            ),
        }

        # Applicability domain: DI from training embeddings (folds by float)
        _, _, emb_tr = served.predict(self.train)
        di = DissimilarityIndex().fit(emb_tr, self.train["float_id"].astype(str).to_numpy())
        _, _, emb_va = served.predict(self.val)
        di_va, inside_dom = di.in_domain(emb_va)
        err = self._err(d_mean)
        dom: dict[str, Any] = {
            "threshold": _r(di.threshold),
            "share_inside": _r(float(np.mean(inside_dom))),
            "di_quantiles_val": [_r(float(v)) for v in np.percentile(di_va, [5, 25, 50, 75, 95])],
        }
        for k, sel in (("inside", inside_dom), ("outside", ~inside_dom)):
            dom[k] = {
                "profiles": int(sel.sum()),
                "thermocline_rmse": _r(m.rmse(err[sel], self.mask[sel], m.THERMOCLINE))
                if sel.any()
                else None,
            }
        if inside_dom.any() and (~inside_dom).any():
            # Bootstrap over floats of RMSE(outside) - RMSE(inside)
            rng = np.random.default_rng(1)
            reps = []
            for _ in range(self.n_boot):
                idx = np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))])
                a, b_ = idx[~inside_dom[idx]], idx[inside_dom[idx]]
                if len(a) and len(b_):
                    reps.append(
                        m.rmse(err[a], self.mask[a], m.THERMOCLINE)
                        - m.rmse(err[b_], self.mask[b_], m.THERMOCLINE)
                    )
            dom["outside_minus_inside_ci"] = [
                _r(float(np.percentile(reps, 2.5))),
                _r(float(np.percentile(reps, 97.5))),
            ]
        e6["applicability"] = dom
        return e6, e7, {"model": served, "di": di, "scores": scores}

    def stratum_status(self) -> dict[tuple[str, str], str]:
        path = OUT / "metrics_v2.json"
        if not path.exists():
            return {}
        rows = json.loads(path.read_text(encoding="utf-8")).get("strata", [])
        return {(r["region"], r["season"]): r["status"] for r in rows}

    def save_served(self, served: ProfileModel, di: DissimilarityIndex) -> dict[str, Any]:
        """Calibrate on all of 2023 per mode (Mondrian) and write the serving checkpoint."""
        calib = {}
        for mode in MODES:
            mean, sigma, _ = served.predict(self.val, mode=mode)
            sc = np.where(self.mask, np.abs(self.y - mean) / np.maximum(sigma, 1e-6), np.nan)
            calib[mode] = cv.MondrianConformal().fit(sc, self.mask, self.reg, self.sea).to_dict()
        payload = {
            "format": "aquasphere-v2",
            "model_version": "tier_a_v2.0",
            **served.state(),
            "conformal": calib,
            "dissimilarity": di.to_dict(),
            "provenance": build_provenance(TABLE, 0),
            "protocol": {"train": "2015-2022", "calibration": "2023", "test": "2024-2025 (locked)"},
        }
        if not self.quick:
            CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
            torch.save(payload, CHECKPOINT)
            logger.info("wrote %s", CHECKPOINT)
        return {"path": CHECKPOINT.as_posix(), "written": not self.quick}


def markdown(r: dict[str, Any]) -> str:
    def ci(c: list[float | None]) -> str:
        return f"{c[0]:.3f} to {c[1]:.3f}" if None not in c else "-"

    def pv(p: float | None) -> str:
        return "-" if p is None else ("< 0.001" if p < 0.001 else f"{p:.3f}")

    lines = [
        "# Phase 4 results: model and uncertainty (validation 2023)",
        "",
        f"Generated by `python -m aquasphere.eval.report_phase4` at {r['generated_at']}. "
        f"Validation: {r['split']['val_profiles']} profiles from {r['split']['val_floats']} floats never seen in training. "
        "The 2024-2025 test period was not read. Thermocline = 50-150 m; CIs are 95% from a bootstrap over floats.",
        "",
        "## Loss: physics terms",
        "",
        "| Arm | Thermocline RMSE | 95% CI | Skill vs B0 |",
        "|---|---|---|---|",
    ]
    for k in ("with", "without"):
        a = r["physics"][k]
        lines.append(
            f"| {k} | {a['thermocline_rmse']:.3f} | {ci(a['ci'])} | {a['skill_thermocline']:+.3f} |"
        )
    lines += [
        f"\nChosen: **{r['physics']['chosen']}** (lower validation RMSE).",
        "",
        "## E3 sensor ablation",
        "",
    ]
    lines += [
        "| Config | Inputs | Thermocline RMSE | 95% CI | Skill vs B0 | Seeds (mean ± std) |",
        "|---|---|---|---|---|---|",
    ]
    for k, a in r["e3"]["configs"].items():
        lines.append(
            f"| {k} | {a['label']} | {a['thermocline_rmse']:.3f} | {ci(a['ci'])} | {a['skill_thermocline']:+.3f} | {a['seeds']['mean']:.3f} ± {a['seeds']['std']:.3f} |"
        )
    lines += ["", "| Step | Difference (°C) | 95% CI | Relative | p |", "|---|---|---|---|---|"]
    for k, d in r["e3"]["steps"].items():
        lines.append(
            f"| {k} | {d['diff_c']:+.3f} | {ci(d['ci'])} | {d['relative']:+.1%} | {pv(d['p'])} |"
        )
    e4 = r["e4"]
    lines += [
        "",
        "## E4 point features vs patch encoder",
        "",
        f"Tier A {e4['tier_a']['thermocline_rmse']:.3f} °C, Tier B {e4['tier_b']['thermocline_rmse']:.3f} °C; "
        f"B - A = {e4['b_minus_a']['diff_c']:+.3f} °C (95% CI {ci(e4['b_minus_a']['ci'])}, p {pv(e4['b_minus_a']['p'])}).",
        "",
        "## E5 pre-training learning curves",
        "",
        "| Labels | Scratch | Masked | Masked + temporal |",
        "|---|---|---|---|",
    ]
    for i, f in enumerate(FRACTIONS):
        row = [
            f"{c[i]['thermocline_rmse']:.3f}"
            for c in (r["e5"]["curves"][a] for a in ("scratch", "masked", "masked+temporal"))
        ]
        lines.append(f"| {int(f * 100)}% | " + " | ".join(row) + " |")
    h2 = r["e5"]["h2_validation"]
    lines += [
        "",
        f"H2 at validation ({h2['best_pretext']}): reduction {h2['reduction_full_labels']:+.1%} at full labels "
        f"(needs ≥ {H2_FULL:.0%}), {h2['reduction_10pct_labels']:+.1%} at 10% (needs ≥ {H2_LOW:.0%}). "
        f"Decision: **{h2['decision']}**.",
        "",
        "## E6 calibration",
        "",
        "| Method | Overall 90% coverage | 95% CI | Mean width (°C) | Thermocline CRPS |",
        "|---|---|---|---|---|",
    ]
    for k, meth in r["e6"]["methods"].items():
        o = meth["coverage"][0]
        lines.append(
            f"| {k} | {o['coverage']:.1%} | {o['ci_low']:.1%} to {o['ci_high']:.1%} | {meth['mean_width']:.2f} | {meth['crps_thermocline']:.3f} |"
        )
    lines += [
        "",
        "Mondrian conformal by stratum (cross-conformal over floats):",
        "",
        "| Region | Season | Profiles | Floats | Coverage | 95% CI | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in r["e6"]["methods"]["conformal_mondrian"]["coverage"]:
        lines.append(
            f"| {row['region']} | {row['season']} | {row['profiles']} | {row['floats']} | {row['coverage']:.1%} | {row['ci_low']:.1%} to {row['ci_high']:.1%} | {row['status']} |"
        )
    ap = r["e6"]["applicability"]
    lines += [
        "",
        f"Applicability domain: threshold DI {ap['threshold']}, {ap['share_inside']:.1%} of validation profiles inside. "
        f"Thermocline RMSE inside {ap['inside']['thermocline_rmse']}, outside {ap['outside']['thermocline_rmse']} "
        f"({ap['outside']['profiles']} profiles); outside - inside 95% CI {ap.get('outside_minus_inside_ci', '-')}.",
        "",
        "## E7 nowcast vs delayed",
        "",
        f"Skill vs B0: delayed {r['e7']['skill_delayed']:+.3f}, nowcast {r['e7']['skill_nowcast']:+.3f}; "
        f"ratio {r['e7']['skill_ratio']:.3f} (95% CI {ci(r['e7']['skill_ratio_ci'])}; H1b needs ≥ 0.85 on the test period).",
        "",
        r["e7"]["preliminary_sst"],
        "",
        "## Gate",
        "",
        f"- Mondrian coverage in {COVERAGE_BAND[0]:.0%}-{COVERAGE_BAND[1]:.0%} in every stratum: {'yes' if r['e6']['gate']['every_stratum_in_band'] else 'no'}; "
        f"in every confirmatory stratum and overall: {'yes' if r['e6']['gate']['confirmatory_strata_in_band'] else 'no'}.",
        f"- H2 go/no-go: **{h2['decision']}**. Shipped: {r['served']['tier']}.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--n-boot", type=int, default=2000)
    a = ap.parse_args()
    run = Runner(quick=a.quick, n_boot=200 if a.quick else a.n_boot)
    physics, cfg = run.physics()
    e3 = run.e3(cfg)
    e6, e7, served = run.e6_e7(cfg)
    e4, e5 = run.e4_e5(
        run.run("served_s0", lambda: served["model"], modes=("delayed", "nowcast"))["delayed_mean"]
    )
    saved = run.save_served(served["model"], served["di"])
    result = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "quick": a.quick,
        "split": {
            "train_profiles": len(run.train),
            "val_profiles": len(run.val),
            "val_floats": int(run.val["float_id"].nunique()),
        },
        "seeds": list(run.seeds),
        "physics": physics,
        "e3": e3,
        "e4": e4,
        "e5": e5,
        "e6": e6,
        "e7": e7,
        "served": {
            "tier": "Tier A v2 (point features, nowcast-aware, Mondrian conformal per mode, DI)",
            "config": {k: v for k, v in served["model"].state()["config"].items() if k != "extra"},
            **saved,
        },
    }
    # A quick run only checks the plumbing: its numbers never reach docs/results
    out = CACHE if a.quick else OUT
    out.mkdir(parents=True, exist_ok=True)
    (out / "phase4.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (out / "phase4.md").write_text(markdown(result), encoding="utf-8")
    logger.info("wrote %s/phase4.json and phase4.md", out.as_posix())


if __name__ == "__main__":
    main()
