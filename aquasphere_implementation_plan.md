# AquaSphere (OceanEmbed — SIH 26066) — Implementation Plan v2

> **Problem:** SIH 26066 — Satellite-embedding deep learning to reconstruct subsurface ocean temperature from surface observations (MoES / INCOIS)
> **Domain:** North Indian Ocean, 5–30°N, 45–105°E · 15 depths (0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000 m)
> **Repo:** `github.com/FarhanAaqil/AquaSphere`
> **Plan status:** v2 — supersedes v1. Section 0 explains what changed and why.

---

## Roadmap at a Glance — 8 Phases

| # | Phase | What gets done | Gate to pass |
|---|---|---|---|
| **1** | **Foundation** | Commit + tag current state as `v0.2-baseline`; restructure into `src/aquasphere/`; `pyproject.toml`, ruff, mypy, pre-commit, CI skeleton | CI green on empty suite |
| **2** | **Evaluation framework** | Float-grouped + time-blocked splits; metrics (RMSE, skill score, D20, MLD); baselines (climatology, ridge, LightGBM); v1 re-evaluated | Leak tests pass; honest baseline table exists |
| **3** | **Data pipeline** | Multi-year Argo (2015–2025) with QC + depth masks; Zarr store (SST, SLA, SSS, winds); `verify_sources.py`; manifests + hashes | Store opens offline; data-contract tests pass |
| **4** | **Tier A model** | Multi-sensor MLP, masked heteroscedastic loss, ablation ladder (3 seeds), conformal calibration | Beats climatology at every depth on val; coverage 85–95% |
| **5** | **Tier B + C (novelty)** | Patch-CNN encoder; SSL pre-training; low-data learning curve | Go/no-go on SSL; negative result is reported, not hidden |
| **6** | **Serving layer** | FastAPI endpoints (`/meta`, `/predict_batch`, `/grid`, `/validation/profile`, `/explain`); offline-first resolver; Pydantic validation; startup checksum checks | API contract + offline-mode tests pass |
| **7** | **Frontend + packaging** | ES-module split; all 9 tabs on real data; `/meta` date picker; source badges; uncertainty bands; Dockerfile | No silent simulation; `/ready` = 200 in Docker |
| **8** | **Final eval + docs** | Test year run once; auto-generated README tables; model/data cards; `REPRODUCE.md`; demo script, pitch, backup recording | `make reproduce` works from a clean clone |

**Execution rule:** when you say *"complete phase N"*, I work through that phase one task at a time, and after **each task** I give you one commit message (see §8.3a) plus the files it touched.

If time is short, drop phase 5 and the Tier B/C parts of phase 4 (see §10.2).

---

## 0. What Was Wrong With v1 (and What v2 Fixes)

v1 was a good *bug-fix list*. It was not yet a *capstone-grade plan*. The gaps:

| # | Issue in v1 | Why it matters | v2 fix |
|---|---|---|---|
| 1 | **Random train/val split on Argo profiles.** Profiles from the same float a few days apart are near-duplicates. | The headline `r = 0.9923` / RMSE `0.928 °C` is almost certainly inflated by leakage. Judges who know ocean ML will probe this first. | Float-grouped + time-blocked splits, plus a held-out final year (§3). |
| 2 | **No baselines.** | RMSE alone is meaningless without climatology / persistence / simple-ML comparisons. | Baseline ladder + skill score vs climatology (§3.3). |
| 3 | **Overall `r` is dominated by the vertical gradient** (warm surface, cold deep). | High `r` is trivial. Real skill is in *anomalies*. | Report anomaly correlation + skill score per depth (§3.2). |
| 4 | **Data = 2,253 profiles over ~7 months of 2025.** | Cannot learn seasonal or interannual behaviour; the model effectively memorises one monsoon season. | Multi-year Argo (2015–2025, SMAP era) via bulk download (§4). |
| 5 | **"Embedding" = 16-d bottleneck of a pointwise MLP.** | Weak claim for a problem statement literally about *satellite embeddings*. No spatial context (eddies, fronts). | Patch-based multi-sensor encoder + self-supervised pre-training (§5). |
| 6 | **Phase 1 pre-loads the training CSV into the SST cache; `/nearest_argo` searches the same CSV.** | Demo would show *training* profiles as if they were predictions → looks perfect, is dishonest. | Serve only held-out profiles for validation views; flag in-training points (§7). |
| 7 | **SSS dataset ID `erdQAstress…` looks like a wind-stress product, not salinity.** | Phase 3 data plan would fail at ingestion. | Verify every dataset ID programmatically; add fallbacks (§4.2). |
| 8 | **Internal inconsistency:** table says 50–150 m `r = 0.926`, text says `r = 0.612 at 100 m`. | Undermines credibility. | Single source of truth: metrics JSON → auto-generated README tables (§9). |
| 9 | **Target "thermocline RMSE < 0.85 °C" set before re-evaluating under honest splits.** | Honest-split RMSE will likely be *worse* than 0.928 °C. A fixed number is a trap. | Targets expressed relative to baselines + statistical tests (§3.4). |
| 10 | **Hard-coding new dates** to match cache. | Patches the symptom. | Offline-first Zarr store + `/meta` endpoint that tells the UI which dates exist (§6). |
| 11 | **7-day timeline for everything.** | Not feasible at this scope. | 5-week plan with go/no-go gates + a 7-day MVP cut (§10). |
| 12 | **Section 3 of v1 is chat-transcript text about a sandbox**, not project planning. | Doesn't belong in a plan document. | Replaced by a real Git/CI workflow (§8). |

---

## 1. Project Thesis & Novelty (what we claim, honestly)

**One-sentence claim:**
> *AquaSphere learns self-supervised multi-sensor satellite embeddings of the North Indian Ocean surface and decodes them into calibrated, uncertainty-aware subsurface temperature profiles — evaluated under strict spatiotemporal hold-out and delivered as a reproducible, offline-capable decision-support tool.*

**Novelty components (ranked by defensibility):**

| Contribution | Why it's novel / useful | Risk |
|---|---|---|
| **N1. Self-supervised pre-training on unlabeled satellite patches, fine-tuned on sparse Argo** | Argo is label-scarce (~10⁴ profiles) but satellite fields are abundant (~10⁸ cell-days). Directly attacks the core bottleneck. | Medium — gated by go/no-go (§10). |
| **N2. Regime-aware evaluation for the NIO** (Arabian Sea vs Bay of Bengal, SW/NE monsoon, barrier layers, D20 / thermocline depth) | Most reconstruction papers report global/basin RMSE only. NIO monsoon reversal is the hard case. | Low. |
| **N3. Calibrated uncertainty** (heteroscedastic head + conformal calibration) with reliability diagrams | Useful for INCOIS-style decision support; most prototypes report point estimates only. | Low. |
| **N4. Multi-sensor ablation ladder** (SST → +SLA → +SSS → +wind → +patch → +SSL) | Quantifies *what each sensor adds* — scientifically publishable result even if absolute gains are modest. | Low. |
| **N5. Offline-first, reproducible, tested delivery** | Rare in hackathon/capstone ML; strong on the engineering rubric. | Low. |

**Negative results are acceptable and reportable.** If SSL (N1) does not beat supervised-from-scratch, the ablation table says so and the project still stands on N2–N5.

---

## 2. Scoring Rubric — What "9/10" Means Here

Scores are my rough judgement of v1's repo state vs the v2 target.

| Dimension | v1 (est.) | v2 target | Evidence required for the target |
|---|---|---|---|
| Novelty | 4 | 8–9 | N1 + N4 results tables; related-work paragraph |
| Scientific validity | 3 | 9 | Leak-free splits, baselines, skill scores, CIs |
| Feasibility | 6 | 9 | Tiered scope, gates, CPU-reproducible MVP |
| Code quality | 5 | 9 | Package layout, typing, lint/type CI clean, config-driven |
| Testing | 2 | 9 | ≥80% coverage on core pkg, ML + API + data-contract tests, CI green |
| Reliability | 4 | 9 | Offline mode, no silent simulation, version checks, timeouts/retries |
| Reproducibility | 3 | 9 | `make reproduce`, pinned deps, data manifest with hashes, seeds |
| Demo / UX | 6 | 8–9 | All 9 tabs real-data, honest source badges, report export |

---

## 3. Evaluation Protocol (build this FIRST — everything else is judged by it)

### 3.1 Splits (no leakage)
- **Temporal hold-out:** Train 2015–2022 · Val 2023 · **Test 2024–2025 (never touched until final).**
- **Float-grouped:** a float ID appears in exactly one split. Enforced by an automated test (§11).
- **Spatial stress test (secondary):** hold out a box (e.g., central Bay of Bengal) to measure geographic transfer.
- **Optional independent check:** RAMA moorings / any INCOIS-available in-situ series not used in training.

### 3.2 Metrics (per depth, per region, per season)
- RMSE, MAE, bias.
- **Anomaly correlation** (vs climatology) and **skill score** `SS = 1 − MSE_model / MSE_clim`.
- **Derived oceanographic metrics:** mixed-layer depth error, **D20** (20 °C isotherm depth) error, upper-300 m heat content error.
- **Uncertainty:** 90% interval coverage, reliability diagram, mean interval width (sharpness).
- **Confidence intervals:** block bootstrap over floats (not over profiles).

### 3.3 Baseline ladder (all evaluated on the same test split)
1. Climatology (WOA23 monthly, or training-set monthly mean if WOA unavailable)
2. Climatology + SST anomaly regression (per depth, ridge)
3. Gradient-boosted trees (LightGBM) per depth, same inputs as v2 MLP
4. **v1 `OceanEmbedNet` (5→64→16→64→15)** re-evaluated under the new splits
5. Optional external reference: a public reanalysis/analysis product (e.g., CMEMS ARMOR3D or GLORYS) on the test period, if free access is available — framed as an *upper-reference*, not a competitor.

### 3.4 Acceptance targets (relative, not magic numbers)
- Beats climatology skill score > 0 at **every** depth on test.
- Beats v1 under identical splits with block-bootstrap 95% CI excluding zero for thermocline (50–150 m) RMSE.
- 90% prediction intervals achieve 85–95% empirical coverage.
- Absolute thermocline RMSE target (`< 0.85 °C`) is **kept as a stretch goal only**, re-set after the honest baseline is measured.

> **Expect v1's numbers to get worse under honest splits.** That is the point; the story becomes "here is the true baseline, here is what each sensor and each method adds."

---

## 4. Data Pipeline

### 4.1 Argo (labels)
- Source: Argo GDAC bulk via `argopy` (or Ifremer ERDDAP); Argovis kept as a fallback only.
- Use **delayed-mode adjusted** variables where available; keep only QC flag 1 (good) [2 optional]; position/time QC passed.
- Vertical: PCHIP interpolation to the 15 standard depths. **Do not drop profiles that don't reach 1000 m** — store a **depth mask** and use a masked loss (more data, no bias from only keeping deep floats).
- Output: `data/processed/argo_profiles.parquet` with `float_id, cycle, lat, lon, time, T[15], mask[15]`.

### 4.2 Satellite predictors
Replace per-profile point queries (the source of the 60 s timeouts) with **bulk gridded downloads → one local Zarr store**.

| Variable | Primary | Fallback | Notes |
|---|---|---|---|
| SST | NOAA OISST v2.1 | — | Already working |
| SSS | SMAP L3 (NASA RSS / JPL) | CMEMS multi-obs SSS; ESA CCI SSS | SMAP era starts 2015; coastal RFI flagged → availability mask |
| SLA + geostrophic currents | CMEMS DUACS L4 (free registration) | NOAA/AVISO mirrors on ERDDAP | "No login" is not a hard requirement; free registration is fine |
| Winds | ERA5 or NOAA blended winds | CCMP | Also derive wind-stress curl |

**Rules:**
- A script `data/verify_sources.py` fetches each dataset's metadata and asserts the variable name, units and coverage **before** any download (prevents the wrong-dataset-ID failure from v1).
- Every download writes to a **manifest** (`data/manifest.json`: URL, date range, SHA-256, row/cell counts).
- Store as `data/store/surface.zarr` (dims: `time, lat, lon`; vars: `sst, sss, sla, ug, vg, u10, v10`), 0.25° grid. Rough size: ~24k cells/day → well under 5 GB for a decade; the demo subset (2024–2025) is < 1 GB.
- Large artefacts are **not committed to Git** (see §8).

### 4.3 Collocation
- For each Argo profile: extract a **9×9 patch (≈ 2.25°)** per variable centred on the profile, at profile date; plus a scalar-feature fallback (centre pixel).
- Availability mask per channel (e.g., SSS missing near coast).

---

## 5. Model Architecture (tiered so there's always a shippable result)

### Tier A — Strong supervised baseline (MUST-HAVE)
- Input: `[lat, lon, sin_doy, cos_doy, sst, sss, sla, ug, vg, u10, v10]` + 7 availability masks.
- Encoder: `Linear → GELU → LayerNorm → ResidualBlock → Linear(16)`; L2-normalised embedding.
- Decoder: `Linear → GELU → ResidualBlock → Linear(30)` → mean `T̂` and `log σ²` for 15 depths.
- Predict **anomaly vs climatology**, then add climatology back (reduces what the net must learn; makes skill scores meaningful).

### Tier B — Spatial-context encoder (SHOULD-HAVE; core of "embedding" claim)
- Small CNN (3 conv blocks, ≤ 300k params) over the 9×9×C patch + scalar features → 16–32-d embedding → same decoder.
- Optional: decode to **EOF coefficients** (≈ 5–8 vertical modes) instead of 15 raw depths → smoother, physically plausible profiles. Evaluate as an ablation.

### Tier C — Self-supervised pre-training (STRETCH; gated)
- Stage 1 (no Argo): masked-patch / masked-channel reconstruction on millions of random patches from the Zarr store (e.g., hide 50% of pixels or an entire channel, reconstruct it).
- Stage 2: attach decoder, fine-tune on Argo (encoder frozen for N epochs, then unfrozen with lower LR).
- **Gate:** keep only if it improves test thermocline RMSE over Tier B-from-scratch with CI excluding zero **or** is clearly better in the low-data regime (train on 10/25/50% of Argo → learning-curve plot). Otherwise report as a negative result.

### Loss (masked, heteroscedastic, physics-regularised)

$$
\mathcal{L}=\sum_{k=1}^{15} m_k\,w_k\Big[\tfrac{(\hat T_k-T_k)^2}{2\sigma_k^2}+\tfrac12\log\sigma_k^2\Big]
+\lambda_{\text{grad}}\sum_{k=1}^{14} m_k m_{k+1}\big|\Delta\hat T_k-\Delta T_k\big|
+\lambda_{\text{phys}}\sum_{k=1}^{14}\mathrm{ReLU}\big(\hat T_{k+1}-\hat T_k-\epsilon_{\text{inv}}\big)
$$

- `m_k` = depth mask; `w_k = 2` for 50–150 m.
- Stability: **MSE warm-up for the first ~10 epochs**, then switch to NLL (or use β-NLL); clamp `log σ²`.
- `ε_inv` and `λ`s are **tuned on validation, with the physics term ablated** (with/without) — don't assume it helps.
- Post-hoc **conformal calibration** of intervals on the validation year.

### Ablation table (the central results artefact)

| Run | SST | +SLA | +SSS | +Wind/Curr | +Patch | +SSL | Thermo RMSE | SS | Coverage |
|---|---|---|---|---|---|---|---|---|---|
| Climatology | | | | | | | | | |
| v1 re-eval | ✓ | | | | | | | | |
| A1 … A4 | ✓ | ✓ | ✓ | ✓ | | | | | |
| B | ✓ | ✓ | ✓ | ✓ | ✓ | | | | |
| C | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | | |

Every row: 3 seeds, mean ± std. Generated by script; never hand-typed.

---

## 6. Serving Layer (FastAPI) — Reliability Design

### 6.1 Data-source resolution (never fabricate)
```
request(lat, lon, date)
  1. local Zarr store           → data_source = "local_store"
  2. disk cache (hashed keys)   → data_source = "disk_cache"
  3. live ERDDAP (timeout 5 s, 2 retries, exp. backoff, circuit breaker) → "live"
  4. none available             → HTTP 503 with explicit message  (NO silent simulation)
```
Every response carries `data_source`, `model_version`, `data_version`, `in_training_set: bool`.

### 6.2 Endpoints
| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /ready` | readiness: model + scaler checksum match, Zarr store opens |
| `GET /meta` | available date range, domain bounds, depths, model/data versions (UI date picker is driven by this — fixes v1's hard-coded dates properly) |
| `POST /predict` | single point: profile, σ, 16-d embedding, MLD, D20 |
| `POST /predict_batch` | vectorised; max 5,000 points per call |
| `GET /grid` | bbox + step + date → fields + PCA coords (PCA fitted offline, stored in checkpoint) |
| `GET /validation/profile` | nearest **held-out** (val/test) Argo profile + model prediction + distance (km) + float ID |
| `GET /validation` | metrics JSON (from the evaluation run, not computed live) |
| `GET /explain` | attribution — **integrated gradients or permutation importance** rather than raw `|∂T/∂x·x|` (the latter is unstable for sin/cos and lat/lon inputs) |

### 6.3 Hardening
- Pydantic v2 request/response models; reject out-of-domain lat/lon and out-of-range dates with `422`.
- Cache keys are **hashed** (no raw URL → filename; avoids path issues); atomic writes (temp file + rename).
- LRU/TTL in-memory cache with a size cap; `httpx` async client with explicit timeouts.
- CORS restricted to configured origins (open `*` only in a `DEMO_MODE` flag).
- Structured JSON logs with request IDs; `/metrics` (Prometheus) optional.
- **Fail fast at startup** if `model.pt` / `scaler.json` / config hashes don't match the manifest.
- Frontend served by FastAPI `StaticFiles` from `web/` (not a one-off `FileResponse`).

---

## 7. Frontend — Honest De-Simulation

1. Split the 1,000+ line HTML into ES modules (`web/js/{api,state,views/*}.js`) — **no build step required**.
2. Replace `_lastApiResponse` with `Map` cache keyed `lat_lon_date` + request de-duplication (in-flight promise map) to stop race conditions.
3. Explore / Depth / Embedding / Compare / Overview alerts → batch endpoints (one call per view/date).
4. **Date picker bounded by `/meta`** — no hard-coded dates.
5. Validation tab uses `/validation/profile` (held-out only) and shows float ID, date, distance.
6. **Source badge on every chart:** `local_store | disk_cache | live | unavailable`. If the backend is down, show an explicit *"Offline demo (synthetic)"* banner — synthetic data is allowed **only** in that labelled mode.
7. Show uncertainty bands on profiles and a "in training set" marker where applicable.
8. Report export (`reportText()`) includes model version, data source, split used, and the limitations paragraph.
9. Accessibility basics: colour-blind-safe colormap, keyboard focus, alt text.

---

## 8. Repository Structure, Tooling & Git Workflow

### 8.1 Layout
```
AquaSphere/
├─ pyproject.toml            # deps, ruff, mypy, pytest config
├─ Makefile                  # make setup | data | train | eval | serve | test | reproduce
├─ configs/                  # YAML: data.yaml, model_a.yaml, model_b.yaml, ssl.yaml
├─ src/aquasphere/
│  ├─ data/      (argo.py, satellite.py, collocate.py, splits.py, store.py)
│  ├─ models/    (encoder.py, decoder.py, losses.py, ssl.py)
│  ├─ train/     (train.py, calibrate.py)
│  ├─ eval/      (metrics.py, baselines.py, report.py)
│  └─ serve/     (app.py, schemas.py, resolver.py, cache.py)
├─ web/                      # static frontend (ES modules)
├─ tests/        (unit/, ml/, api/, data/, e2e/)
├─ docs/         (ARCHITECTURE.md, MODEL_CARD.md, DATA_CARD.md, REPRODUCE.md, results/)
├─ .github/workflows/ci.yml
├─ Dockerfile · docker-compose.yml · .pre-commit-config.yaml
```

### 8.2 Code-quality standards
- Python 3.11, **type hints everywhere**, `mypy --strict` on `src/aquasphere/{data,models,eval}`.
- `ruff` (lint + format), `pre-commit` hooks; no notebooks in `src/`.
- **Config-driven** runs (no magic numbers in code); every run saves `config.yaml + git SHA + seed + data manifest hash` next to the checkpoint.
- Pinned lockfile (`uv lock` / `pip-compile`), `pip-audit` in CI.
- Deterministic training: seeds for `random/numpy/torch`, `torch.use_deterministic_algorithms` where feasible.
- Docstrings with units on every public function (°C, m, km).

### 8.3 Git workflow
- Trunk-based: short-lived branches named after the work (e.g. `leak-free-splits`, `offline-resolver`) → PR → squash merge; **humanized commit messages** (§8.3a); PR template with checklist (tests, docs, metrics regenerated). Squash-merge titles follow the same style.
- **Do not store large binaries/data in plain Git history.** Use Git LFS or DVC for `model.pt`; publish datasets and the demo Zarr as **GitHub Release assets** with SHA-256 in the manifest.
- First action: commit your current working-tree changes and tag them as the reference baseline:

```powershell
cd D:\EDU\Projects\AquaSphere
git add data/argo_sst_training.csv model/model.pt model/scaler.json model/validation_metrics.json
git commit -m "snapshot of the v1 model before the rebuild: 2253 profiles and retrained weights"
git tag v0.2-baseline
git push origin main --tags
```
- Auth: `gh auth login` (HTTPS, browser) is the simplest on Windows; PAT with `Contents: read/write` as fallback.

### 8.3a Commit message rules (one commit per task)

**Process:** every task in a phase ends with exactly one commit, and one commit message handed to you right after the task is done. No batching several tasks into one commit.

**Style rules:**
- Written like a developer talking, not like a changelog generator.
- **No type prefixes or scopes:** no `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`, and no `(scope)` brackets.
- **Don't open with stock verbs** like *add, update, implement, create, refactor, resolve*. Start with the thing itself or what it does now.
- Say what changed and, when it isn't obvious, why. One line, roughly 70 characters or fewer.
- No emojis, no "This commit…", no buzzwords, no trailing full stop.

| Instead of (AI boilerplate) | Write (humanized) |
|---|---|
| `feat(data): add Argo loader` | argo loader now keeps only delayed-mode profiles with good QC flags |
| `fix: resolve data leakage in split` | splits keep every float in exactly one bucket, and a test fails if one slips across |
| `chore: update dependencies` | pinned torch and numpy so training gives the same numbers on every machine |
| `test: add API tests` | api tests cover out-of-domain inputs and the no-network case |
| `docs: update README metrics` | README tables now come straight from metrics.json, no more hand-edited numbers |
| `feat(server): add /meta endpoint` | the date picker reads its range from /meta instead of hard-coded dates |

### 8.4 CI (`.github/workflows/ci.yml`)
Jobs on every PR: **lint → type-check → unit/API/data tests with coverage gate (≥ 80% on `src/aquasphere`) → 2-epoch smoke train on a 200-profile fixture → Docker build + `/ready` check.** Nightly (optional): full evaluation regression gate.

---

## 9. Documentation as a Generated Artefact (kills doc drift)

- `eval/report.py` writes `docs/results/metrics.json` and **regenerates the benchmark tables** inside `README.md` / `walkthrough.md` between marker comments (`<!-- METRICS:START -->` … `END`). CI fails if committed tables differ from the regenerated ones.
- `MODEL_CARD.md`: intended use, training data, splits, metrics by region/season, uncertainty calibration, **known failure modes** (coastal SSS, eddy-rich zones, monsoon transitions, depth > 700 m sparsity), not for operational use without INCOIS validation.
- `DATA_CARD.md`: sources, licences, QC rules, manifests.
- `ARCHITECTURE.md`: Mermaid diagram of data → store → train → eval → serve → UI.
- `REPRODUCE.md`: from clean clone to reported numbers in ≤ 6 commands.

---

## 10. Timeline, Gates & Risk Management

### 10.1 Five-week plan

| Week | Deliverable | Exit gate |
|---|---|---|
| **1** | Repo restructure, CI, tag baseline, **leak-free splits + baselines + metrics code**, v1 re-evaluated | CI green; honest baseline table exists |
| **2** | Multi-year Argo + Zarr surface store + manifests + data-contract tests | Store opens offline; split-leak test passes |
| **3** | Tier A training + ablation ladder (A1–A4), uncertainty + conformal | Beats climatology at all depths on val |
| **4** | Tier B (patch CNN) → **go/no-go** on Tier C SSL; API v2 + `/meta` + batch + held-out validation | API contract tests pass; offline mode test passes |
| **5** | Frontend de-simulation, Docker, docs/cards, final test-set run (once), demo script, 5-min pitch | `make reproduce` works from clean clone |

### 10.2 If you only have 7 days (MVP cut)
Days 1–2: splits + baselines + commit/CI skeleton · Day 3: Argo 2022–2025 + SST/SLA/SSS bulk store · Day 4: Tier A + uncertainty · Day 5: API (`/meta`, `/predict_batch`, held-out validation) + offline resolver · Day 6: frontend wiring + source badges · Day 7: tests/Docker/docs. **Skip Tier B/C; the ablation (SST → +SLA → +SSS → +wind) is still a legitimate novelty result.**

### 10.3 Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SMAP/altimetry access or ID problems | Med | High | `verify_sources.py`; fallbacks in §4.2; start with SST+SLA only |
| Honest-split metrics are poor | High | Med | Expected; frame as baseline; report skill vs climatology, not absolute RMSE |
| SSL doesn't help | Med | Low | Gated; report as negative result |
| Compute limits | Med | Med | Models ≤ 300k params; CPU-trainable; Colab/Kaggle GPU optional |
| Time overrun | High | High | Tiers + gates; MVP cut in §10.2 |
| ERDDAP/network flakiness at demo | High | High | Offline-first Zarr store; Docker image with demo data baked in |
| Test-set peeking | Med | High | Test year touched once; `tests/data` asserts test split unused in training/tuning scripts |

---

## 11. Test Strategy

| Layer | What | Examples |
|---|---|---|
| **Unit** | Pure functions | depth interpolation (PCHIP) on known profiles; normaliser round-trip; EOF projection; MLD/D20 on synthetic profiles; masked loss with all-zero mask = 0 |
| **Data contract** (`pandera`) | Schemas & invariants | no NaN in unmasked targets; lat/lon/time within domain; QC flags; **no float ID appears in >1 split**; **all test dates > all train dates**; manifest hashes match files |
| **ML behaviour** | Model correctness | overfits a 32-sample batch to near-zero loss; deterministic given seed; batch-vs-single inference equal (≤1e-5); masked channel doesn't change output when mask=0; embedding is unit-norm and 16-d; gradients finite; σ² > 0 |
| **Physics / property** (`hypothesis`) | Invariants over random valid inputs | outputs finite for any in-domain input; no inversion larger than ε beyond tolerance on ≥ 99% of grid |
| **Regression gate** | Quality | frozen test-set metrics must not degrade beyond tolerance vs `docs/results/metrics.json` (tolerance, not a fixed `< 1.0 °C`) |
| **API** (`TestClient`) | Contracts | schemas, `422` on out-of-domain, `503` (not fake data) when no source; `data_source` always present; **offline test: block network, still serves from store**; p95 latency < 100 ms warm, < 500 ms cold on fixture |
| **Frontend smoke** (Playwright, optional) | Wiring | each of 9 tabs renders with mocked API; source badge visible; offline banner appears when API down |
| **Container** | Packaging | image builds, `/ready` returns 200, image < 600 MB (CPU torch) |

Coverage gate ≥ 80% on `src/aquasphere`; ML/data tests use small fixtures (< 5 MB) committed to the repo.

---

## 12. Definition of Done (checklist)

- [ ] Leak-free splits enforced by tests; test year used exactly once
- [ ] Baseline ladder + v1 re-evaluation published
- [ ] ≥ 4-row ablation table with 3 seeds each, generated by script
- [ ] Uncertainty coverage 85–95% (90% nominal) with reliability plot
- [ ] Multi-year Argo + multi-sensor Zarr store with manifest & hashes
- [ ] No silent simulation anywhere; every view shows `data_source`
- [ ] Validation views use held-out profiles only
- [ ] CI green: ruff, mypy, tests (≥ 80% cov), smoke train, Docker build
- [ ] `make reproduce` works from a clean clone
- [ ] README/walkthrough tables auto-generated; no drift
- [ ] Model card, data card, architecture doc, limitations section
- [ ] Demo script + 5-minute pitch + backup screen recording (in case of network failure)

---

## 13. How to Present the Novelty (pitch / viva)

1. **Problem:** subsurface structure drives monsoon & cyclone intensity; Argo is sparse, satellites are dense.
2. **Gap:** most prototypes use random splits and point estimates; label scarcity unaddressed.
3. **Our approach:** multi-sensor patch embeddings (+ self-supervised pre-training) → calibrated profile reconstruction.
4. **Evidence:** leak-free test year, skill vs climatology, ablation of each sensor, regime breakdown (Arabian Sea vs Bay of Bengal, monsoon seasons), uncertainty coverage.
5. **Honesty slide:** limitations and failure modes.
6. **Delivery:** offline-capable dashboard + API + Docker, fully reproducible.