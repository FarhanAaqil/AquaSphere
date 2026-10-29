"""
Evaluation report for protocol v2 (roadmap Phase 3): E2 baseline ladder, E1 leakage gap,
stratified results with power analysis, and B4 calibration. Validation (2023) only: the test
partition stays locked until the final evaluation.

    python -m aquasphere.eval.report_v2

Writes docs/results/metrics_v2.json, baseline_table_v2.md, e1_leakage_v2.json and .md.
Numbers in the docs and the web UI are generated from these files, never typed by hand.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.data.collocate_nio import OUTPUT as TABLE
from aquasphere.data.splits import make_float_grouped_split
from aquasphere.eval import metrics_v2 as m
from aquasphere.eval.baselines_v2 import LADDER, B4DeepEnsemble, targets
from aquasphere.eval.metrics import compute_d20
from aquasphere.eval.protocol import PERIODS, assign, partition, region, season, summarise

logger = logging.getLogger(__name__)

OUT = Path("docs/results")
SEEDS = (0, 1, 2)
DETERMINISTIC = {"B0", "B1"}  # no randomness: one fit is the same as three
MIN_FLOATS_FOR_CLAIMS = 5  # strata with fewer floats are reported as descriptive only


def _round(x: float, n: int = 4) -> float | None:
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def d20_rmse(y: np.ndarray, pred: np.ndarray) -> tuple[float, int]:
    """D20 computed identically on observed and predicted profiles (blueprint V10)."""
    pairs = [(compute_d20(t), compute_d20(p)) for t, p in zip(y, pred, strict=True)]
    diffs = np.array([b - a for a, b in pairs if np.isfinite(a) and np.isfinite(b)])
    return (float(np.sqrt(np.mean(diffs**2))), len(diffs)) if diffs.size else (float("nan"), 0)


def fit_predict(
    key: str, train: pd.DataFrame, val: pd.DataFrame, seed: int
) -> tuple[np.ndarray, np.ndarray | None]:
    model = LADDER[key]().fit(train, seed=seed)
    if isinstance(model, B4DeepEnsemble):
        return model.predict_dist(val)
    return model.predict(val), None


def e2_ladder(
    train: pd.DataFrame, val: pd.DataFrame, seeds: tuple[int, ...], n_boot: int
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    y, mask = targets(val)
    groups = val["float_id"].to_numpy()
    errors: dict[str, np.ndarray] = {}
    out: dict[str, Any] = {}
    clim_pred: np.ndarray | None = None
    for key in LADDER:
        t0 = time.time()
        runs = [fit_predict(key, train, val, s) for s in ((0,) if key in DETERMINISTIC else seeds)]
        per_seed = [m.rmse(np.where(mask, p - y, 0.0), mask, m.THERMOCLINE) for p, _ in runs]
        pred = np.mean([p for p, _ in runs], axis=0)  # seed-averaged prediction
        err = np.where(mask, pred - y, 0.0)
        errors[key] = err
        if key == "B0":
            clim_pred = pred
        assert clim_pred is not None
        boot_t = m.bootstrap_rmse(err, mask, groups, m.THERMOCLINE, n_boot=n_boot)
        boot_h = m.bootstrap_rmse(err, mask, groups, m.HEADLINE, n_boot=n_boot)
        d20, n_d20 = d20_rmse(np.where(mask, y, np.nan), pred)
        entry: dict[str, Any] = {
            "name": LADDER[key].name,
            "seeds": len(runs),
            "thermocline_rmse": _round(boot_t["rmse"]),
            "thermocline_ci_95": [_round(boot_t["ci_low"]), _round(boot_t["ci_high"])],
            "thermocline_rmse_seed_mean": _round(float(np.mean(per_seed))),
            "thermocline_rmse_seed_std": _round(float(np.std(per_seed))),
            "headline_rmse_20m_plus": _round(boot_h["rmse"]),
            "headline_ci_95": [_round(boot_h["ci_low"]), _round(boot_h["ci_high"])],
            "skill_thermocline": _round(m.skill(err, errors["B0"], mask, m.THERMOCLINE)),
            "skill_headline": _round(m.skill(err, errors["B0"], mask, m.HEADLINE)),
            "anomaly_corr_thermocline": _round(
                m.anomaly_correlation(np.where(mask, y, 0.0), pred, clim_pred, mask, m.THERMOCLINE)
            ),
            "d20_rmse_m": _round(d20, 2),
            "d20_n": n_d20,
            "bands": m.band_table(err, mask),
            "fit_seconds": round(time.time() - t0, 1),
        }
        sigmas = [s for _, s in runs if s is not None]
        if sigmas:
            sigma = np.sqrt(np.mean([s**2 for s in sigmas], axis=0))
            yy = np.where(mask, y, 0.0)
            idx = m.cols(m.THERMOCLINE)
            crps = m.crps_gaussian(yy, pred, sigma)
            entry["probabilistic"] = {
                "crps_thermocline": _round(float(np.mean(crps[:, idx][mask[:, idx]]))),
                "crps_headline": _round(
                    float(np.mean(crps[:, m.cols(m.HEADLINE)][mask[:, m.cols(m.HEADLINE)]]))
                ),
                "reliability": m.reliability(yy, pred, sigma, mask),
                "coverage_90": _round(
                    m.interval_scores(yy, pred - 1.645 * sigma, pred + 1.645 * sigma, mask)[
                        "coverage"
                    ]
                ),
                "mean_width_90": _round(
                    m.interval_scores(yy, pred - 1.645 * sigma, pred + 1.645 * sigma, mask)[
                        "mean_width"
                    ]
                ),
            }
        out[key] = entry
        logger.info("%s: thermocline RMSE %.3f °C (%.0fs)", key, boot_t["rmse"], time.time() - t0)

    comparisons = {
        k: m.paired_rmse_difference(
            errors[k], errors["B0"], mask, groups, m.THERMOCLINE, n_boot=2 * n_boot
        )
        for k in LADDER
        if k != "B0"
    }
    adjusted = m.holm({k: c["p"] for k, c in comparisons.items()})
    for k, c in comparisons.items():
        out[k]["vs_B0_thermocline"] = {
            **{n: _round(v) for n, v in c.items()},
            "p_holm": _round(adjusted[k]),
        }
    return out, errors


def strata(val: pd.DataFrame, errors: dict[str, np.ndarray], n_boot: int) -> list[dict[str, Any]]:
    """Region x monsoon season, with sample counts and the minimum detectable difference."""
    _, mask = targets(val)
    groups = val["float_id"].to_numpy()
    reg, sea = region(val["lon"]).to_numpy(), season(val["date"]).to_numpy()
    rows = []
    for r in ("Arabian Sea", "Bay of Bengal"):
        for s in ("NE monsoon", "Inter-monsoon", "SW monsoon"):
            sel = (reg == r) & (sea == s)
            n_floats = len(np.unique(groups[sel]))
            row: dict[str, Any] = {
                "region": r,
                "season": s,
                "profiles": int(sel.sum()),
                "floats": n_floats,
            }
            if sel.sum() == 0:
                rows.append({**row, "status": "empty"})
                continue
            row["thermocline_rmse"] = {
                k: _round(m.rmse(e[sel], mask[sel], m.THERMOCLINE)) for k, e in errors.items()
            }
            if n_floats >= 2:
                diff = m.paired_rmse_difference(
                    errors["B2"][sel],
                    errors["B0"][sel],
                    mask[sel],
                    groups[sel],
                    m.THERMOCLINE,
                    n_boot=n_boot,
                )
                row["mde_thermocline_c"] = _round(m.minimum_detectable_difference(diff["se"]), 3)
            row["status"] = (
                "confirmatory" if n_floats >= MIN_FLOATS_FOR_CLAIMS else "descriptive only"
            )
            rows.append(row)
    return rows


def e1_leakage(
    df: pd.DataFrame, models: tuple[str, ...] = ("B0", "B1", "B2", "B3"), seed: int = 0
) -> dict[str, Any]:
    """Same models, three ways of splitting the pre-test data (2015-2023). Test period untouched."""
    pre = df[df["period"].isin(["train", "val"])].reset_index(drop=True)
    rng = np.random.default_rng(seed)
    is_eval = rng.random(len(pre)) < 0.2
    flt_train, flt_eval, _ = make_float_grouped_split(
        pre, train_ratio=0.8, val_ratio=0.2, test_ratio=0.0, seed=seed
    )
    splits = {
        "random": (pre[~is_eval], pre[is_eval]),
        "float_grouped": (flt_train, flt_eval),
        "time_blocked_float_grouped": (partition(df, "train"), partition(df, "val")),
    }
    out: dict[str, Any] = {
        "splits": {k: {"train": len(a), "eval": len(b)} for k, (a, b) in splits.items()},
        "models": {},
    }
    for key in models:
        res = {}
        for name, (tr, ev) in splits.items():
            y, mask = targets(ev)
            pred, _ = fit_predict(key, tr, ev, seed)
            res[name] = _round(m.rmse(np.where(mask, pred - y, 0.0), mask, m.THERMOCLINE))
        blocked, rand = res["time_blocked_float_grouped"], res["random"]
        res["random_vs_blocked_pct"] = (
            _round(100 * (blocked - rand) / blocked, 1) if blocked and rand is not None else None
        )
        out["models"][key] = res
        logger.info("E1 %s: %s", key, res)
    return out


def ladder_markdown(report: dict[str, Any]) -> str:
    rows = [
        "# E2 baseline ladder (auto-generated by aquasphere.eval.report_v2, do not edit)",
        "",
        f"Validation {PERIODS['val'][0]} to {PERIODS['val'][1]}: {report['split']['profiles']['val']} profiles from "
        f"{report['split']['floats']['val']} floats never seen in training. Headline depths are 20 m and below "
        "(0-10 m depends on OISST, which ingests Argo). 95% CIs from a bootstrap over floats.",
        "",
        "| Rung | Model | Thermocline RMSE (°C) | 95% CI | Skill vs B0 | ≥20 m RMSE | D20 RMSE (m) | vs B0 p (Holm) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for k, r in report["e2"].items():
        cmp = r.get("vs_B0_thermocline", {})
        rows.append(
            f"| {k} | {r['name']} | {r['thermocline_rmse']:.3f} ± {r['thermocline_rmse_seed_std']:.3f} | "
            f"{r['thermocline_ci_95'][0]:.3f} to {r['thermocline_ci_95'][1]:.3f} | {r['skill_thermocline']:+.3f} | "
            f"{r['headline_rmse_20m_plus']:.3f} | {r['d20_rmse_m']} | {cmp.get('p_holm', '—')} |"
        )
    b4 = report["e2"].get("B4", {}).get("probabilistic")
    if b4:
        rows += [
            "",
            f"B4 calibration: 90% interval coverage {b4['coverage_90']:.1%}, mean width {b4['mean_width_90']:.2f} °C, thermocline CRPS {b4['crps_thermocline']:.3f} °C.",
        ]
    rows += [
        "",
        "## Strata (region by monsoon season)",
        "",
        "| Region | Season | Profiles | Floats | B0 | B2 | MDE (°C) | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in report["strata"]:
        t = s.get("thermocline_rmse", {})
        rows.append(
            f"| {s['region']} | {s['season']} | {s['profiles']} | {s['floats']} | {t.get('B0', '—')} | {t.get('B2', '—')} | {s.get('mde_thermocline_c', '—')} | {s['status']} |"
        )
    return "\n".join(rows) + "\n"


def leakage_markdown(e1: dict[str, Any]) -> str:
    rows = [
        "# E1 leakage gap (auto-generated by aquasphere.eval.report_v2, do not edit)",
        "",
        "Thermocline RMSE (°C) of the same models under three splits of the 2015-2023 data.",
        "",
        "| Model | Random | Float-grouped | Time-blocked + float-grouped | Random looks better by |",
        "|---|---|---|---|---|",
    ]
    for k, r in e1["models"].items():
        rows.append(
            f"| {k} | {r['random']} | {r['float_grouped']} | {r['time_blocked_float_grouped']} | {r['random_vs_blocked_pct']}% |"
        )
    return "\n".join(rows) + "\n"


def run(
    table: Path = TABLE, out_dir: Path = OUT, seeds: tuple[int, ...] = SEEDS, n_boot: int = 1000
) -> dict[str, Any]:
    df = assign(pd.read_parquet(table))
    train, val = partition(df, "train"), partition(df, "val")
    e2, errors = e2_ladder(train, val, seeds, n_boot)
    report = {
        "_note": "Auto-generated by aquasphere.eval.report_v2. Do not edit by hand.",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "protocol": {
            "periods": PERIODS,
            "rule": "time-blocked; each float in the first period it appears in",
            "test_locked": True,
        },
        "table": table.as_posix(),
        "split": summarise(df).as_dict(),
        "seeds": list(seeds),
        "e2": e2,
        "strata": strata(val, errors, n_boot),
        "depths": list(STANDARD_DEPTHS),
    }
    e1 = {"generated_at": report["generated_at"], **e1_leakage(df)}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics_v2.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out_dir / "baseline_table_v2.md").write_text(ladder_markdown(report), encoding="utf-8")
    (out_dir / "e1_leakage_v2.json").write_text(json.dumps(e1, indent=1), encoding="utf-8")
    (out_dir / "e1_leakage_v2.md").write_text(leakage_markdown(e1), encoding="utf-8")
    return {"report": report, "e1": e1}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Protocol v2 evaluation on train/validation")
    p.add_argument("--table", default=str(TABLE))
    p.add_argument("--n-boot", type=int, default=1000)
    a = p.parse_args()
    run(Path(a.table), n_boot=a.n_boot)


if __name__ == "__main__":
    main()
