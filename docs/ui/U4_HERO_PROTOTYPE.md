# Phase U4: 3D Hero Prototype — AquaSphere (OceanEmbed)

Following the **Immersive UI/UX Playbook §5, §7.2, and §8**.

---

## 1. "Descent" 3D Scene Architecture (`web/js/components/descent3d.js`)

The hero 3D scene directly embodies the signature metaphor:
- **Surface Mesh (Epipelagic 0m):** High-efficiency displaced plane geometry with flat-shaded procedural oceanic wave dynamics and ACES Filmic tone mapping.
- **Orbital Satellite Tracks:** Dual elliptical 3D line arcs overhead representing altimetry (SWOT, Jason-3) and SST passes.
- **Thermal Strata Cylinders (0–1000m):**
  - Epipelagic layer (0–100m, deep ocean blue)
  - **Thermocline Stratum (100–150m):** Highlighted with warm amber material (`#f5a524`, `--accent-warm`) with glowing torus indicator ring.
  - Mesopelagic layer (200–500m)
  - Bathypelagic & Benthic Grid (500–1000m, wireframe seabed plane)
- **Autonomous Argo Profiling Float:**
  - Yellow cylinder body, dark CTD sensor head, teal antenna, and expanding telemetry pulse ring.
  - Sinks and rises through the water column dynamically as the user scrolls.
- **Particle Field (Marine Snow & Plankton):**
  - Point cloud drifting with gentle upward buoyancy and orbital flow.
- **Scroll Camera Path:**
  - Lerps smoothly from surface ($y = +1.2$, looking at water surface) down to abyssal floor ($y = -5.2$, looking into benthic strata).

---

## 2. Automated Quality Tiers (`web/js/components/quality.js`)

Implements **Playbook §8.1** auto-selection without user configuration:

| Tier | Hardware Criteria | DPR Cap | Particle Count | Mesh Segments | Downgrade Threshold |
|---|---|:---:|:---:|:---:|:---:|
| **High** | $\ge 8$ cores & $\ge 8$ GB RAM | 2.0 | 16,000 | $160 \times 160$ | Downgrades if FPS < 24 |
| **Medium** | $\ge 4$ cores & $\ge 4$ GB RAM, or high-end mobile | 1.5 | 6,000 | $96 \times 96$ | Downgrades if FPS < 20 |
| **Low** | Budget mobile / low memory | 1.0 | 1,500 | $48 \times 48$ | Static fallback if < 15 |

*Note: In accordance with Playbook §8.1, the engine will automatically downgrade during FPS dips, but will never upgrade mid-session.*

---

## 3. Render Loop, Lazy Load & Resource Protection

- **Single Animation Loop:** One `requestAnimationFrame` loop for the entire scene.
- **Off-Screen Pause:** `IntersectionObserver` disconnects rendering when canvas scrolls out of viewport.
- **Tab Inactivity Pause:** `document.visibilityState` pauses animation when the tab is hidden.
- **No In-Loop Allocations:** All vectors and matrices are pre-allocated and reused to guarantee zero garbage-collection stutter.
- **Static Canvas Fallback:** Full 2D canvas gradient fallback if WebGL is disabled or fails initialization.

---

## 4. Phase U4 Gate Check

- [x] "Descent" hero scene built with procedural Three.js geometry and custom materials.
- [x] Auto-tiering controller (`quality.js`) integrated.
- [x] Single render loop with offscreen & background tab pausing.
- [x] Static 2D fallback implemented.
- [x] Zero external heavy 3D assets loaded (100% procedural, total asset payload = 0 KB, well within the 3 MB budget).
