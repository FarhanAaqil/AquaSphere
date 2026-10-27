# Phase U1: Brief and Direction — AquaSphere (OceanEmbed)

## 1. Filled Project Brief

```
PRODUCT NAME:               AquaSphere (OceanEmbed)
ONE-LINE PURPOSE:           Reconstruct subsurface ocean temperature (0–1000 m) from satellite surface
                            data for the North Indian Ocean, with calibrated uncertainty.
AUDIENCE & CONTEXT:         Hackathon judges and ocean scientists; mostly desktop projector + some phones.
TONE (3 words):             Calm, scientific, deep.
SIGNATURE METAPHOR:         "Descent": scrolling dives from the sunlit satellite view down through
                            temperature layers to 1000 m, where Argo floats take their measurements.
PRIMARY USER TASK:          Pick a place and date in the NIO and see the predicted temperature profile,
                            its uncertainty, and how it compares with a real held-out Argo profile.
REAL DATA / CONTENT:        API endpoints (/meta, /predict, /grid, /validation/profile), metrics.json,
                            baseline and ablation tables, model and data cards.
MUST NEVER BE INVENTED:     Any metric, profile value, sensor reading, resolution or location label.
SECTIONS:                   Hero · Problem · How it works · Live explorer · Evidence · Limits · CTA
CONSTRAINTS:                Works offline (local data store); must label synthetic data; reproducible build.
PERFORMANCE TIER TARGET:    B (laptop + mid phone).
```

---

## 2. Tone & Aesthetics
- **Tone (3 words):** Calm, scientific, deep.
- **Palette Seed:**
  - Base: Deep Midnight Navy `--bg-0: #060b14` (60%)
  - Surfaces: Dark Oceanic Navy `--bg-1: #0d1726` (30%)
  - Accent: Electric Marine Teal `--accent: #2dd4bf` (10%)
  - Thermocline Reserve: Warm Amber `--accent-warm: #f5a524` (reserved strictly for thermocline inflection & real observation points)
  - Typography: Space Grotesk (display), Inter (body), JetBrains Mono (data/coordinates)

---

## 3. Signature Metaphor
> **"Descent": As you scroll, your perspective dives continuously from sunlit surface waves and orbital satellite paths down through glowing temperature strata to the 1000 m abyssal floor where autonomous Argo floats take in-situ measurements.**

---

## 4. Visual Reference Direction & Moodboard

1. **Surface Hero & Satellite Orbital Pass:**
   Sunlit ocean surface with gentle water caustics, subtle wave displacement, and faint glowing satellite orbital trajectories against twilight sky.
2. **Subsurface Thermal Strata:**
   Translucent 3D vertical water column (0–1000m) with layered temperature gradients and warm amber thermocline ribbon at 100–150m.
3. **Autonomous Argo Profiling Float:**
   Yellow NOAA/INCOIS profiling float descending with sensor CTD telemetry points and delicate drifting marine snow particles.
4. **The Observation Problem (Swath vs Sparse Points):**
   Dense wide satellite altimetry and SST swaths crossing sparse, discrete vertical Argo float dive profiles across the North Indian Ocean basin.
5. **Calm Scientific Data Workbench (`/explorer`):**
   High-contrast, distraction-free 2D bathymetric map, depth scrubber, conformal uncertainty bands, and strict data provenance badges (`LIVE`, `CALIBRATED`, `LOCAL STORE`, `SAMPLE / SYNTHETIC`).
6. **Abyssal 1000m Stillness:**
   Deep ocean calm at the benthic floor with drifting plankton particles and soft telemetry illumination.

---

## 5. Phase U1 Gate Check

- [x] Filled Project Brief completed (10 lines).
- [x] 6 Visual reference renders generated and aligned with palette seed.
- [x] Palette seed mapped to semantic ocean variables (teal = model / accent, warm amber = thermocline & ground truth).
- [x] Metaphor explained in one clear sentence:
  > *"As you scroll, your perspective dives continuously from sunlit surface waves and orbital satellite paths down through glowing temperature strata to the 1000 m abyssal floor where autonomous Argo floats take in-situ measurements."*
