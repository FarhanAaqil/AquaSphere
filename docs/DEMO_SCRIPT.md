# AquaSphere: 5-minute pitch and live demo (SIH 26066)

> **Audience:** SIH evaluators, MoES / INCOIS ocean scientists
> **Setup:** `make serve` (or `python -m aquasphere.serve.app`) with the trained model and the
> 2015-2025 store in place, Chrome at `http://127.0.0.1:8000`, top-bar date 2024-07-15.
> **Backup:** a full recorded walkthrough (`python scripts/walkthrough.py`, video in
> `dist/demo/`) and Offline mode, which keeps the app working with the API down.

Every number below comes from `docs/results/final_eval.md` (test period, read once) or
`docs/results/phase4.md` (validation). Do not round them up.

---

## 0:00-0:45 · The problem

> "Argo floats tell us the temperature of the North Indian Ocean down to 1000 metres, but there
> are only a few hundred of them, each surfacing every ten days. Satellites see the whole ocean
> every day, but only its skin. Problem 26066 asks whether we can read the subsurface from space.
>
> AquaSphere learns that link from five satellite inputs: temperature, sea level, salinity,
> currents and winds. For any point and day it returns a temperature profile at 15 depths, a
> calibrated 90% interval at every depth, and a warning when the inputs look unlike anything it
> was trained on."

**Show:** Overview. Let the globe settle on the Arabian Sea and Bay of Bengal, then scroll the
descent from the surface to 1000 m.

---

## 0:45-2:15 · Live tour

1. **Predict** (30 s). Click the central Bay of Bengal. Point at the 90% band, D20 and the cyclone
   heat potential tile, then at the applicability check: "DI within the training-fold
   threshold". Flip the top-bar switch to **Nowcast**: the profile barely moves, because nowcast
   keeps all the skill (H1b).
2. **Ocean Products** (25 s). Cyclone heat potential layer, then Anomaly at 100 m, then tick
   Compare with a winter date: the difference map shows the monsoon reversal.
3. **Sections** (25 s). Click across the Arabian Sea to the Bay of Bengal: a depth x distance
   section with the 20 °C isotherm traced on it. Then the depth-time view at 15°N 65°E over a
   year.
4. **Profile Explorer** (10 s). A 2023 profile the model never saw, predicted vs observed.

---

## 2:15-3:45 · What the test period said

> "We trained on 2015-2022, calibrated on 2023, and locked 2024-2025. Before touching it we wrote
> down five hypotheses with thresholds, tagged them in git, and then read the test period
> exactly once. The access log has one line."

**Show:** Experiments, the Final evaluation card.

- **Three of five hypotheses supported**, after Holm correction:
  - adding sea-level anomaly to SST cuts thermocline error by **19.8%** (needed 15%);
  - nowcast mode keeps the full skill (ratio **1.03**, needed 0.85);
  - the 90% intervals cover **90.0%** of test observations (needed 87-93%).
- **Two not supported, and we say so:** self-supervised pre-training did not help (H2), and a
  random split flattered the baseline by only 3.2%, not 20% (H4).
- **Honest ranking:** the served model scores **1.26 °C** thermocline RMSE; LightGBM and a deep
  ensemble score 1.24 °C. We are level with the strongest baselines, not ahead of them. What we
  add is calibrated intervals per region and season, nowcast mode, and the applicability flag.

**Show:** Uncertainty: the reliability diagram on the diagonal, then coverage by stratum, and
point at the one weak cell: the Bay of Bengal in the NE monsoon covers 80%.

---

## 3:45-4:30 · Built to be trusted

- **Independent check:** at RAMA moorings, which no model ever saw, the error is 1.08 °C against
  1.05 °C for climatology. "At fixed moorings we do not beat climatology yet, and that is on the
  Experiments tab."
- **No invented data:** turn on Offline demo in settings: Ocean Products refuses with "Needs the
  live API". Every chart carries its source badge; a missing observation is a 503, not a guess.
- **Offline:** stop the server; the app still opens and says it is showing saved results, with
  the time they were saved.
- **Engineering:** ONNX serving, Prometheus metrics, rate limiting, CSV/NetCDF export with
  provenance, a regression gate and frozen result hashes in CI.

---

## 4:30-5:00 · Close

> "AquaSphere turns daily satellite data into calibrated subsurface temperature for the North
> Indian Ocean, and it tells you when not to trust it. Everything is open data, reproducible with
> one command, and every claim was tested once, on data it had never seen."

---

## Anticipated questions

**Why not report the best validation number?** Validation was used to tune and calibrate. The
only unbiased numbers are from the test period, which was read once after the hypotheses were
frozen.

**The model is not better than LightGBM. Why use it?** It matches the strongest baselines on
accuracy and adds what operations need: intervals calibrated by region and season (H3
supported), one model for nowcast and delayed inputs (H1b supported), an embedding for the
applicability flag, and ONNX serving.

**What about the Bay of Bengal?** Bay of Bengal strata have about 22 floats each in the test
period, too few for confirmatory claims. Coverage there is 87-88% except the NE monsoon (80%),
and the model card lists it as a known failure mode.

**Can this be used operationally today?** No. It is a decision-support prototype; operational use
needs independent INCOIS verification, a prospective run on the preliminary near-real-time SST
release, and longer mooring comparisons.

**How do you stop leakage?** Each float belongs to the first period it appears in; climatology and
normalisation use training years only; a static test fails if any code other than the final
evaluation asks for the test partition.
