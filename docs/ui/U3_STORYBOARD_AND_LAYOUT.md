# Phase U3: Storyboard and Layout — AquaSphere (OceanEmbed)

Following the **Immersive UI/UX Playbook §3 and §11**.

---

## 1. Cinematic Storyboard ("Descent" Narrative Spine)

```
[Scroll: 0%  — 0m]       SECTION 1: HERO (Sunlit surface waves & orbital tracks)
                             │
                             ▼
[Scroll: 18% — 20m]      SECTION 2: THE PROBLEM (Satellite Swath vs Sparse Floats)
                             │
                             ▼
[Scroll: 36% — 150m]     SECTION 3: HOW IT WORKS (Sensors -> Embedding -> Profile -> CI)
                             │
                             ▼
[Scroll: 54% — 300m]     SECTION 4: LIVE EXPLORER TEASER (Interactive mini-query)
                             │
                             ▼
[Scroll: 72% — 600m]     SECTION 5: EVIDENCE & BASELINE LADDER (Honest metrics.json)
                             │
                             ▼
[Scroll: 88% — 900m]     SECTION 6: LIMITATIONS & APPLICABILITY DOMAIN (Bounds)
                             │
                             ▼
[Scroll: 100% — 1000m]   SECTION 7: ASCENT & CTA (Launch Workbench, Docs, Repo)
```

---

## 2. Detailed Section Specifications

| # | Section | Depth / State | 3D Scene Action | Content & Real Data | Measurable Takeaway |
|---|---|---|---|---|---|
| **1** | **Hero** | Surface (0m) | Camera rests at sea level; gentle sunlit wave displacement, golden reflections, faint satellite orbital trajectory rings overhead. | Headline: *See Beneath the Surface.* Subtitle: Reconstructing 0–1000m subsurface ocean heat from satellite observations. CTA: "Launch Explorer" | Understands what AquaSphere does in 5 seconds. |
| **2** | **The Problem** | Epipelagic (20–50m) | Camera submerges below water surface; split visualization contrasting wide satellite swath bands with rare isolated vertical Argo float points. | The Subsurface Observation Void: Satellites see only the skin; in-situ Argo floats sample only sparse points across 15 million km². | Grasps why subsurface reconstruction from surface data is critical. |
| **3** | **How It Works** | Thermocline (150m) | Camera enters glowing warm-amber thermocline strata; an autonomous Argo float drifts while a 4-step pipeline draws on scroll. | 4-Step Architecture: (1) Satellite surface features (SST, SLA, SSS, Wind) $\to$ (2) Multi-sensor latent embedding $\to$ (3) MLP/Patch-CNN profile decoder $\to$ (4) Conformal calibration. | Transparent explanation of the scientific pipeline. |
| **4** | **Live Proof** | Mesopelagic (300m) | Water column darkens to deep navy; a glowing depth slice plane highlights the active query depth. | Interactive Mini-Slice: Pick Arabian Sea or Bay of Bengal $\to$ triggers real API predict $\to$ live D20, MLD, and conformal bounds with `LIVE` badge. | Verifies live working ML model without leaving the narrative. |
| **5** | **Evidence** | Bathypelagic (600m) | Deep calm waters; floating chart layers elevate into view. | Honest Baseline Ladder from `metrics.json`: HistGBDT (0.954°C) beating neural net (1.184°C), Climatology (1.925°C), Ridge (1.776°C). 242 held-out profiles across 15 unseen floats. | Uncompromising scientific honesty without inflated claims. |
| **6** | **Limitations** | Abyssal (900m) | Dim deep-ocean atmosphere with drifting marine snow particles. | Operational Boundaries: North Indian Ocean domain (5°–30°N, 45°–105°E), 0–1000m depth cap, seasonal monsoon extremes, synthetic fixture disclosure. | Clear understanding of model limitations and applicability. |
| **7** | **CTA** | Ascent (1000m $\to$ 0m) | Camera smoothly ascends back toward the surface light. | Launch Full Workbench (`/explorer`), Inspect Data Card, View GitHub Source. | Seamless transition to the analytical workbench layer. |

---

## 3. Workbench Architecture (`/explorer`)

- **Header:** Coordinate HUD, active date, region badge, and global data provenance badge (`LIVE` / `LOCAL STORE` / `SAMPLE`).
- **Left Column (Spatial Navigation):**
  - High-performance 2D SVG/Canvas map of the North Indian Ocean with bathymetric contours.
  - Interactive click-to-place coordinate crosshairs.
  - Quick region presets: Arabian Sea Upwelling, Bay of Bengal Plume, Equatorial Channel.
- **Right Column (Vertical Subsurface Reconstruction):**
  - Vertical 0–1000m profile chart.
  - Teal curve: Model reconstructed temperature profile.
  - Teal envelope: 90% and 95% conformal uncertainty bounds.
  - Amber markers: Real held-out Argo float observation points (when available within radius).
  - Gray dashed curve: Historical climatology baseline.
- **Bottom Ribbon (Derived Physical Metrics):**
  - Thermocline Depth ($D_{20}$ in meters)
  - Mixed Layer Depth (MLD in meters)
  - Ocean Heat Content ($OHC_{300}$ in $GJ/m^2$)
  - Applicability domain alert (in-bounds vs out-of-bounds warning).

---

## 4. Phase U3 Gate Check

- [x] All 7 sections defined with precise scroll depths and 3D camera states.
- [x] Every section has an explicit, measurable takeaway grounded in real data.
- [x] Workbench layout mapped to existing API endpoints (`/meta`, `/predict`, `/grid`, `/validation/profile`).
- [x] Zero invented metrics or sci-fi labels; all numbers reference `metrics.json` and API contracts.
