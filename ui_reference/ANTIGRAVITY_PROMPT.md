# AquaSphere UI Rebuild: Build Instructions for the Coding Agent

Read this whole file before touching any code. Work in the steps at the bottom, one at a time, and stop after each step.

---

## 1. Goal (one paragraph)

Replace the current AquaSphere frontend with a new one that looks **exactly like the two reference files** in this folder:

- `landing_reference.html` is the cinematic scroll page ("Descent"): a 3D ocean you dive into as you scroll.
- `workbench_reference.html` is the data dashboard ("Explorer"): controls, map, depth profile, evidence strip.

**These two files are the visual source of truth.** Your job is to **port** them into the project structure below and wire the workbench to the real API. You are **not** redesigning anything. Do not "improve", restyle or reinterpret them.

---

## 2. Hard rules (read twice)

1. **Copy, don't reinvent.** Move the reference CSS, markup and JavaScript into the new files **verbatim**, only splitting them into modules. If a value is in the reference, keep it.
2. **Keep the 3D.** The background is a real Three.js scene (wave-shader ocean surface, depth strata, drifting particles, an Argo float, a satellite orbit ring). **Never** replace it with CSS gradients, blobs, a video, or an image.
3. **No new libraries.** Allowed: Three.js r128 (UMD build), GSAP 3.12.5 + ScrollTrigger. Nothing else. **No React, no Tailwind, no Vite/webpack, no UI kits, no icon packs.**
4. **No build step.** Plain HTML + CSS + ES modules/classic scripts. The FastAPI app serves the files from `web/`.
5. **Never invent data.** No made-up numbers, units, resolutions, sensor readings, place names, statistics or marketing claims. Every number on screen comes from the API or `docs/results/metrics.json`. If a value is missing, show `—` or `[from /endpoint]`.
6. **Keep the honesty labels.** The `SAMPLE / SYNTHETIC` badge stays on every map, chart and number group until the satellite store is replaced with real data. Keep the "Limits" section text (see section 7).
7. **Colours and fonts are fixed** (section 3). Do not add purple, pink or rainbow gradients, neon outlines, extra glows, or emoji icons.
8. **Keep the copy.** Headings, labels and paragraphs in the references are final. Do not rewrite them or add filler text.
9. **Accessibility stays:** the "Pause motion" button, `prefers-reduced-motion` handling, keyboard focus, 44 px minimum touch targets, text alternatives for the charts, a no-WebGL fallback background.
10. If something is unclear, **keep the reference behaviour** and tell me; do not guess.

---

## 3. Design tokens (do not change)

```css
:root{
  --bg:#060b14; --bg1:#0d1726; --fg:#eaf2ff; --fg2:#9fb0c8;
  --acc:#2dd4bf;            /* the only accent */
  --warm:#f5a524;           /* ONLY for: thermocline highlight, SYNTHETIC badge, "Limits" label */
  --r-md:14px; --r-lg:20px;
  --ease-out:cubic-bezier(.22,1,.36,1);
}
```

- Fonts (Google Fonts): **Space Grotesk** 500/700 for headings, **Inter** 400/500/600 for text, **JetBrains Mono** 400/500 for numbers and small caps labels.
- Panels: `background:#0d1726; border:1px solid rgba(255,255,255,.08); border-radius:14px; padding:16px`.
- Landing cards: `background:rgba(6,11,20,.6); backdrop-filter:blur(14px); border:1px solid rgba(255,255,255,.12); border-radius:20px; padding:32px`.
- Map colour ramp: `#1e4e8c → #2dd4bf → #fde7b0` (cool to warm). Amber is **never** used for temperature.

---

## 4. Files to create

```
web/
├─ index.html                 ← landing (from landing_reference.html)
├─ explorer.html              ← workbench (from workbench_reference.html)
├─ css/
│  ├─ tokens.css              ← the :root block above
│  ├─ landing.css             ← landing styles, moved verbatim
│  └─ workbench.css           ← workbench styles, moved verbatim
├─ js/
│  ├─ landing/
│  │  ├─ scene.js             ← the whole Three.js block, moved verbatim
│  │  ├─ scroll.js            ← GSAP + ScrollTrigger block, moved verbatim
│  │  └─ main.js              ← imports scene + scroll, pause button, content loader
│  └─ workbench/
│     ├─ api.js               ← fetch wrappers (section 6)
│     ├─ map.js               ← SVG map render + click-to-select
│     ├─ profile.js           ← depth profile chart render
│     ├─ evidence.js          ← evidence bars
│     └─ main.js              ← state + wiring
├─ vendor/                    ← three.min.js (r128), gsap.min.js + ScrollTrigger.min.js (3.12.5), local copies
└─ data/metrics.json          ← copied from docs/results/metrics.json by a make target (section 6.4)
```

- First **inspect `web/`** as it is today. If three.js / gsap already exist in a vendor folder with these versions, reuse them. If not, install `three@0.128.0` and `gsap@3.12.5` with npm in a temporary folder and copy only the built files into `web/vendor/`. Do not leave `node_modules` in the repo.
- Delete the old frontend files only **after** the new pages match the references (Step 5).
- FastAPI: serve `index.html` at `/` and `explorer.html` at `/explorer`, with `web/` mounted as static files. Change only what is needed.

---

## 5. The landing page: facts you must not change

Everything is in `landing_reference.html`. These are the numbers that define its look:

| Item | Value |
|---|---|
| Canvas | `position:fixed; inset:0; z-index:0`, pixel ratio `min(devicePixelRatio, 1.5)` |
| Camera | FOV 55, position `(cx·1.4, 3 − 38p, 16 − 6p)`, looks at `(0, camY − 1.5, 0)`; `p` is smoothed scroll progress 0 to 1 (ease factor 0.06) |
| Depth to scene units | `Y(d) = −(d ≤ 300 ? d·0.06 : 18 + (d − 300)·0.0229)` |
| Surface | 90×90 plane, 128×128 segments, wave shader, double-sided, opacity 0.88 |
| Strata | Translucent planes + faint grid at 50, 100, 150, 200, 300, 500, 700, 1000 m. The 50–150 m planes are **amber** (opacity 0.10), the rest are cyan-blue (opacity 0.07) |
| Particles | 1600 points (700 if width < 700 px), additive, drifting up, shader-driven |
| Fog | `FogExp2`, colour lerps `#2a6fa8 → #03060c` over `min(1, p·1.6)`, density `0.03 + 0.02p` |
| Satellite | Thin torus ring (radius 11) tilted, small box orbiting it |
| Argo float | White cylinder + teal cap + antenna, bobbing around the 500 m level |
| Mouse | Subtle camera x-parallax (disabled under reduced motion) |
| Depth gauge | Fixed on the right: a thin line that fills with scroll and a mono label "N m" (N = round(p·1000)) |
| Pause button | Fixed bottom-left, toggles motion time |
| Reveals | Every `.rv` element: from `y:28, opacity:0`, 0.9 s, `power3.out`, trigger `top 88%`, once |
| Pipeline line | `#hline` scaleY 0 → 1, scrubbed across the "How it works" section |
| Evidence bars | Width animates from 0 and the number counts up (2 decimals) when the bar enters view |
| Sections | Hero · Problem · How it works · Evidence · Limits · CTA |

Visual check for the first screen: bright blue water surface with white-cyan wave highlights, big two-line title "See beneath the surface.", a thin orbit ring and tiny satellite at the top, small mono label "North Indian Ocean · 0–1000 m". Scrolling down turns the water darker and fills the view with floating particles.

---

## 6. The workbench: wiring to the real API

Match `workbench_reference.html` first (static), then wire it.

### 6.1 Layout (do not change)
- Top bar: brand, 4 tabs, Nowcast/Delayed toggle (Delayed active), date input, `SAMPLE / SYNTHETIC` badge.
- Grid: `300px | flexible | 400px`, 16 px gaps; below 1180 px it stacks to one column.
- Left: Location (lat/lon), Map depth slider 0–1000 m, Layers checkboxes, short mode note.
- Centre: map panel (SVG, viewBox 720×440, domain 5–30°N, 45–105°E).
- Right: Profile chart (0–1000 m, depth axis stretched above 300 m), legend, four stat tiles.
- Bottom (full width): Evidence bars + provenance footer.

### 6.2 Endpoints
Before writing `api.js`, **read `src/aquasphere/serve/schemas.py` and `app.py`** and use the exact field names found there. Do not invent fields.

| UI element | Endpoint |
|---|---|
| Date range, domain bounds, depths, model and data version | `GET /meta` |
| Selected-point profile, uncertainty, embedding info, D20/MLD/heat content if provided | `POST /predict` |
| Map field for chosen depth and date | `GET /grid` |
| Nearest **held-out** Argo profile + distance | `GET /validation/profile` |
| Evidence numbers | `GET /validation` or `web/data/metrics.json` |

### 6.3 Behaviour
1. On load: call `/meta`, set the date input to the allowed range, show model and data version in the footer.
2. Click on the map: convert the click position to lat/lon (linear mapping of the 720×440 viewBox to 45–105°E and 30–5°N), move the pin, call `/predict`, draw the profile.
3. Profile chart: predicted line (teal, 2.5 px), uncertainty band (teal, 22% opacity), climatology (grey dashed) **only if the API returns it**, held-out Argo points (white hollow circles) from `/validation/profile`. Amber band at 50–150 m with the label "THERMOCLINE 50–150 m".
4. Stat tiles show API values; if a value is not provided, show `—`.
5. Nowcast/Delayed toggle sends the corresponding mode to the API if it supports it; if it does not, disable the toggle and add a tooltip "not available yet". Do not fake it.
6. **Source badge:** read `data_source` from the response. Show `LOCAL STORE`, `CACHED`, `LIVE` or `UNAVAILABLE`; show `SAMPLE / SYNTHETIC` while the satellite fields come from the synthetic fixture.
7. Every request has a loading skeleton, and a visible error message if it fails (what failed + what to try). Never show fake fallback data.
8. If the API answers `503`, show "Data source unavailable" and keep the page usable.

### 6.4 Numbers come from one place
- Evidence bars and counts ("242 profiles · 15 floats") must be read from `metrics.json`, not typed into HTML.
- Add a `make ui-data` target that copies `docs/results/metrics.json` to `web/data/metrics.json`.
- Inspect the file's real structure first and map the four bars (climatology, climatology + ridge, v1 network, gradient-boosted trees) to their real keys. If a key is missing, say so instead of inventing it.

---

## 7. Text that must stay exactly as written

The "Limits" section on the landing page (update only when the underlying fact changes, and tell me when you do):

- Satellite inputs in this build are a sample fixture, not real SMAP, altimetry or ERA5 fields.
- Training data: 2,253 Argo profiles from March to September 2025.
- Self-supervised pre-training has not improved results in our first test.
- The final held-out test year has not been evaluated.

Also keep: "Trees currently beat our neural network. We show that on purpose."

---

## 8. Things models often get wrong here (avoid all of these)

- Replacing the Three.js scene with a CSS gradient or a static image. **Not allowed.**
- Rebuilding the page in React or adding Tailwind "to make it easier". **Not allowed.**
- Centering everything and turning sections into a card grid. Keep the left/right card placement from the reference.
- Adding stats strips, testimonials, "trusted by", fake logos, fake metrics or marketing hype.
- Rewriting the headline, the section titles or the labels.
- Making every element glassy or glowing. Glass is only for the landing cards.
- Using more than one accent colour, or using amber for anything except the three allowed places.
- Changing the map into a generic tile map. It stays the schematic SVG until real coastline data is added.
- Leaving the old frontend half-deleted. Keep it until Step 5.

---

## 9. Steps (stop after each one and report)

**Step 0: Read only.** Read both reference files and the existing `web/`, `src/aquasphere/serve/`, and `docs/results/metrics.json`. Reply with: the list of files you will create, the libraries already available, any conflicts you see. Change nothing.

**Step 1: Landing port.** Create `index.html`, `css/tokens.css`, `css/landing.css`, `js/landing/*`, `vendor/*`. Open the page in a browser (use the browser tool if you have it). Take screenshots at scroll 0%, 20%, 42%, 62%, 82% and compare each with the same scroll position of `landing_reference.html`. Fix differences until they match. Report the screenshots.

**Step 2: Landing content from data.** Make the evidence bars read from `web/data/metrics.json` (section 6.4). Check that no number is typed directly in the HTML.

**Step 3: Workbench port (static).** Create `explorer.html`, `css/workbench.css`. Match `workbench_reference.html` at 1440 px and at 900 px width. Report screenshots.

**Step 4: Workbench wiring.** Implement `api.js`, `map.js`, `profile.js`, `evidence.js`, `main.js` as in section 6. Test: load, click a point, error state (stop the API), loading state.

**Step 5: Switch over.** Serve the new pages from FastAPI, delete the old frontend files, update README screenshots section if present, run the existing tests.

**Step 6: Quality pass.** Check: keyboard navigation, reduced-motion mode, no-WebGL fallback (force an error), no console errors, no horizontal scroll at 360 px width, page stays smooth while scrolling, no memory growth after 2 minutes of scrolling.

After **every task** inside a step, give me **one commit message**: short, written like a person, **no prefixes** such as feat, fix, chore, docs, refactor, and not starting with "add", "update" or "implement". Example: `landing page scene now lives in its own module and looks the same as the reference`.

---

## 10. Definition of done

- [ ] Landing and workbench look the same as the references in side-by-side screenshots
- [ ] 3D scene runs, dive-through scroll works, reduced-motion and pause work
- [ ] Workbench loads real data from the API; errors and loading states shown
- [ ] No hard-coded stats in HTML; no invented labels anywhere
- [ ] `SAMPLE / SYNTHETIC` badge present wherever synthetic data appears
- [ ] No new libraries, no build step, old frontend removed, tests still pass
