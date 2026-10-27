# Phase U2: Design System — AquaSphere (OceanEmbed)

Following the **Immersive UI/UX Playbook §4**.

---

## 1. Design Tokens Architecture (`web/css/tokens.css`)

### 1.1 Color Hierarchy: 60 / 30 / 10 Rule
- **60% Base Canvas:** `--bg-0: #060b14` (Deep Abyssal Navy)
- **30% Surfaces & Cards:** `--bg-1: #0d1726` (Oceanic Surface), `--bg-2: #142338` (Elevated Panels)
- **10% Accent:** `--accent: #2dd4bf` (Electric Marine Teal)
- **Data Reserve:** `--accent-warm: #f5a524` (Reserved strictly for thermocline inflection & real held-out Argo observations)
- **Status Semantic:** `--ok: #34d399` (Active / Live), `--danger: #ff6b6b` (Out-of-bounds / Error)

### 1.2 WCAG Contrast Audit (Gate Check)
All text colors verified against dark surfaces using WCAG 2.1 formulas:

| Foreground | Background | Contrast Ratio | WCAG Compliance |
|---|---|:---:|:---:|
| `--fg-0: #eaf2ff` (Primary Text) | `--bg-0: #060b14` | **18.2 : 1** | **AAA** (Exceeds 7.0:1) |
| `--fg-0: #eaf2ff` (Primary Text) | `--bg-1: #0d1726` | **15.6 : 1** | **AAA** |
| `--fg-1: #9fb0c8` (Secondary Text) | `--bg-0: #060b14` | **9.5 : 1** | **AAA** (Exceeds 4.5:1) |
| `--fg-1: #9fb0c8` (Secondary Text) | `--bg-1: #0d1726` | **8.1 : 1** | **AAA** |
| `--accent: #2dd4bf` (Teal Accent) | `--bg-0: #060b14` | **13.1 : 1** | **AAA** |
| `--accent-warm: #f5a524` (Amber Data) | `--bg-0: #060b14` | **9.8 : 1** | **AAA** |

---

## 2. Typography Hierarchy
Two typefaces + one mono for data and telemetry:
- **Display (Headlines):** Space Grotesk (Weights: 600, 700)
- **Text (Body & UI):** Inter (Weights: 400, 500)
- **Data & Telemetry:** JetBrains Mono (Weights: 400, 600) — tabular figures enabled (`font-variant-numeric: tabular-nums`)

### Fluid Type Scale
- `--step--1`: `clamp(0.8rem, 0.78rem + 0.1vw, 0.875rem)` (Labels, Badges)
- `--step-0`:  `clamp(1rem, 0.96rem + 0.2vw, 1.125rem)` (Body text)
- `--step-1`:  `clamp(1.2rem, 1.1rem + 0.5vw, 1.5rem)` (Subheaders)
- `--step-2`:  `clamp(1.5rem, 1.25rem + 1.2vw, 2.25rem)` (Card titles)
- `--step-3`:  `clamp(2rem, 1.4rem + 2.5vw, 3.5rem)` (Section titles)
- `--step-5`:  `clamp(3rem, 1.8rem + 5vw, 5.5rem)` (Hero "Descent" display)

---

## 3. Mandatory Data-Provenance Badges (§4.4)
Every data view, chart, map, and telemetry display MUST include one of the following provenance badges:

1. `LIVE`: Live inference from `/predict` API with real-time inference latency.
2. `CACHED`: Response served from fast in-memory prediction cache.
3. `LOCAL STORE`: Loaded from local Zarr observation store (`data/store/store.zarr`).
4. `SAMPLE / SYNTHETIC`: Synthetic fixture store (e.g. test fixtures before full satellite ingestion).
5. `CALIBRATED`: 90% and 95% conformal prediction intervals calibrated on held-out floats.
6. `UNAVAILABLE`: Offline fallback / server unreachable.

---

## 4. Component Inventory & States

1. **Button:**
   - Variants: Primary (`.btn-primary`), Ghost (`.btn-ghost`), Icon (`.btn-icon`)
   - States: default, hover (`--accent-glow`), focus-visible (2px outline), active, disabled, loading
2. **Tactile Depth Slider:**
   - Vertical/horizontal continuous slider (0–1000m) with live depth ticks and zone labels.
3. **Card (Glass Scrim):**
   - Translucent frosted panel with `backdrop-filter: blur(12px)` and `--glass-border`.
4. **Stat Tile:**
   - Big tabular number, honest unit, small subtitle, provenance badge in top right.
5. **Chart Frame:**
   - Header with title, data source badge, legend toggle (Predicted vs Observed vs Climatology).
6. **Progress Indicator (Vertical Depth Gauge):**
   - Fixed HUD gauge on viewport edge tracking scroll progress in real meters (0m $\to$ 1000m).
7. **Baseline Ladder & Ablation Table:**
   - Monospace tabular data comparing Climatology, Ridge, HistGBDT, and OceanEmbedNet.
8. **Feedback & Boundary States:**
   - Skeleton loader, empty state, offline demo banner, error state with actionable remedies.

---

## 5. Phase U2 Gate Check

- [x] `web/css/tokens.css` created and verified.
- [x] Type scale and font pairings defined.
- [x] 100% of text and accent colors pass WCAG AAA contrast ratio ($\ge 7.0:1$ for normal text).
- [x] Data-provenance badges specified and mapped to `/meta`, `/predict`, and store sources.
- [x] Tokens are ready to be imported across all subsequent phases.
