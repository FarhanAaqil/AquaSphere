# Phase U8: Demo Package — AquaSphere (OceanEmbed)

Following the **Immersive UI/UX Playbook §11 & §14**.

---

## 1. 60-Second Demo Walkthrough Script

| Time | View / Action | What to Say / Focus | Key Visual Element |
|:---:|---|---|---|
| **0:00–0:12** | **Hero: Surface (0m)** | *"AquaSphere addresses the subsurface ocean observation gap: satellites observe only the sea skin, while 99% of oceanic heat content is hidden beneath. We reconstruct 0–1000m vertical profiles with calibrated uncertainty."* | Procedural sunlit wave shader + orbital satellite arcs + headline *"SEE BENEATH THE SURFACE"*. |
| **0:12–0:24** | **Descent: The Problem (20m)** | *"Scrolling initiates our Descent into the water column. Here we contrast dense satellite swaths against sparse in-situ Argo floats across the 15 million km² North Indian Ocean basin."* | Split contrast cards; Depth Gauge HUD moves from 0m to 20m. |
| **0:24–0:36** | **Mid-Depth: Pipeline & Live Proof (150m–300m)** | *"At 150m, we pass through the thermocline ribbon. Our 4-stage ML pipeline extracts satellite features into a 16-D latent embedding to predict 15 standard pressure levels with split conformal calibration."* | Warm amber thermocline ring + floating Argo float + live inference preset buttons. |
| **0:36–0:48** | **Deep Abyss: Honest Evidence (600m–900m)** | *"Unlike typical benchmark cherry-picking, our baseline ladder reflects honest leak-free float-grouped holdouts: HistGBDT achieves 0.954°C RMSE beating the deep neural net at 1.184°C across 242 held-out profiles."* | Verifiable baseline ladder table read directly from `metrics.json`. |
| **0:48–1:00** | **Ascent: Data Workbench Handoff** | *"Clicking 'Data Workbench' transitions to our full analytical workbench: 2D spatial bathymetry, 0–1000m profile chart with 95% conformal bounds, and strict data provenance badges on every data point."* | Full analytical workbench with profile chart, uncertainty envelope, and provenance badges. |

---

## 2. Reproducible Run & Deployment Guide

### Local Native Run
```bash
# 1. Activate environment
.venv\Scripts\activate

# 2. Run test suite (verifies 93 passed tests, >= 80% coverage)
pytest --cov=src/aquasphere tests/

# 3. Launch local production server
python -m aquasphere.serve.app --host 127.0.0.1 --port 8000
```
Open browser to `http://127.0.0.1:8000/`.

### Docker Container Run
```bash
# Build production image
docker build -t aquasphere:latest .

# Run with container health checks on port 8000
docker run -p 8000:8000 aquasphere:latest
```

---

## 3. Playbook Workflow Complete Summary (Phases U1–U8)

| Phase | Title | Artifact / Code | Gate Status |
|:---:|---|---|:---:|
| **U1** | Brief and Direction | `docs/ui/U1_BRIEF_AND_DIRECTION.md` + 6 Reference Visuals | **PASSED** |
| **U2** | Design System | `web/css/tokens.css` + `docs/ui/U2_DESIGN_SYSTEM.md` | **PASSED** (WCAG AAA) |
| **U3** | Storyboard & Layout | `docs/ui/U3_STORYBOARD_AND_LAYOUT.md` | **PASSED** |
| **U4** | 3D Hero Prototype | `web/js/components/descent3d.js` + `quality.js` | **PASSED** |
| **U5** | Landing Sections & Motion | `web/js/views/landing.js` + `web/css/landing.css` | **PASSED** |
| **U6** | Workbench Layer | `web/js/views/location.js` + Playbook Badges | **PASSED** |
| **U7** | Polish & QA Audit | `docs/ui/U7_POLISH_AND_QA.md` + 93 Pytest Suite | **PASSED** (89.05%) |
| **U8** | Demo Package | `docs/ui/U8_DEMO_PACKAGE.md` + `docs/DEMO_SCRIPT.md` | **PASSED** |
