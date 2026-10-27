# Phase U5: Landing Sections and Motion — AquaSphere (OceanEmbed)

Following the **Immersive UI/UX Playbook §3, §6, and §10**.

---

## 1. Landing Sections Overview (`web/js/views/landing.js`)

All 7 narrative sections of "Descent" are fully mounted and connected to the 3D WebGL engine:

1. **Hero (0m):**
   - Displaced procedural surface ocean waves with sun glints and overhead satellite orbit tracks.
   - Oversized editorial typography: *"SEE BENEATH THE SURFACE."*
   - Direct CTA: "OPEN DATA WORKBENCH →" and "BEGIN DESCENT ↓".
2. **The Problem (20m):**
   - High-contrast visual cards comparing wide, dense satellite swaths (15,000,000 km² horizontal coverage, blind below 1mm) vs sparse vertical Argo float arrays (only ~15–30 active floats in the NIO, 10-day sampling period).
3. **How It Works (150m):**
   - 4-step pipeline drawn on scroll:
     1. Multi-modal surface ingestion (SST, SLA, SSS, Wind)
     2. 16-D continuous oceanographic latent embedding
     3. 15-level vertical profile decoder
     4. Split conformal calibration guaranteeing 90% and 95% marginal coverage.
4. **Live Proof (300m):**
   - Real-time interactive slice: Preset selectors (Bay of Bengal, Arabian Sea, Equatorial NIO).
   - Queries the local model resolver and displays true inferred values for SST, D20, MLD, and conformal CI bounds with the `LIVE` badge.
5. **Evidence & Honest Baseline Ladder (600m):**
   - Verifiable tabular evaluation from `metrics.json` on 242 held-out profiles across 15 unseen Argo floats:
     - HistGBDT (0.954°C Overall RMSE, 1.460°C Thermocline RMSE, +0.754 Skill Score)
     - v1 OceanEmbedNet (1.184°C Overall RMSE, 1.590°C Thermocline RMSE, +0.622 Skill Score)
     - Climatology + Ridge (1.776°C Overall RMSE)
     - Climatology (1.925°C Overall RMSE)
   - Discloses honest negative finding: GBDT outperforms neural net on float-grouped holdouts due to tabular feature regularization.
6. **Limitations & Operational Boundaries (900m):**
   - Precise boundaries: Geographic box (5°–30°N, 45°–105°E), 0–1000m depth cap, cyclonic shear mixing edge cases, and synthetic fixture disclosures.
7. **Ascent & CTA (1000m $\to$ 0m):**
   - Smooth transition into the analytical workbench layer (`/explorer` / Profile view) with links to reproducibility specs and MIT open source license.

---

## 2. Motion System & Depth Gauge HUD

- **Depth Gauge HUD (`#depthHudGauge`):**
  - Fixed HUD on viewport right tracking real depth in meters ($0\text{m} \to 1000\text{m}$) and oceanographic zones (Epipelagic $\to$ Thermocline $\to$ Mesopelagic $\to$ Abyssal).
- **GSAP ScrollTrigger:**
  - One continuous master timeline scrubbing camera dive and fog absorption.
  - Zero scroll-jacking; standard browser smooth scrolling.
- **Reduced Motion Support:**
  - Full `@media (prefers-reduced-motion: reduce)` override in CSS.

---

## 3. Phase U5 Gate Check

- [x] All 7 story sections implemented with real data and honest provenance.
- [x] Scroll timeline coupled to `descent3d.js` engine and Depth Gauge HUD.
- [x] Zero invented metrics or sci-fi labels; numbers match `metrics.json`.
- [x] Reduced-motion fallback verified.
