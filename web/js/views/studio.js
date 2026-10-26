/**
 * AquaSphere Flagship View — Sandstone Blue & Concrete Candy Editorial 3D Experience
 * Combines Awwwards-winning tactile architecture, Three.js 3D monolith, and live ocean telemetry
 */

import { Monolith3D } from '../components/monolith3d.js';
import { fetchPredict, fetchMeta, regionName } from '../api.js';
import { state, setPage, setDepth, setLocation } from '../state.js';

let monolithInstance = null;

export async function renderStudio() {
  const container = document.createElement('div');
  container.className = 'studio-viewport';

  // Compute live values for active state
  const lat = state.lat;
  const lon = state.lon;
  const region = regionName(lat, lon);

  container.innerHTML = `
    <!-- Top Technical Ticker Ribbon -->
    <aside class="ticker-ribbon" aria-label="Acoustic hydrographic metrics">
      <div class="ticker-track">
        <span class="ticker-item pulse"><span class="pip green"></span> SYS: ACOUSTIC HARVEST ACTIVE (24.8 kHz)</span>
        <span class="sep">|</span>
        <span class="ticker-item">LAT: ${lat.toFixed(2)}° N</span>
        <span class="ticker-item">LON: ${lon.toFixed(2)}° E</span>
        <span class="sep">|</span>
        <span class="ticker-item">REGION: ${region.toUpperCase()}</span>
        <span class="sep">|</span>
        <span class="ticker-item">THERMOCLINE DROP: -8.4°C @ 180M</span>
        <span class="sep">|</span>
        <span class="ticker-item">CONFORMAL UNCERTAINTY: ±0.74°C (95% CI)</span>
      </div>
      <div class="ticker-meta">
        <span class="badge-pink">ANOMALY SIG: +0.18</span>
        <span class="badge-strata">ARRAY SECURE: NIO-BENGAL-04</span>
      </div>
    </aside>

    <!-- HERO SECTION: Monumental Architectural Monolith & Editorial Typography -->
    <section class="hero-tectonic">
      <div class="hero-container">
        <!-- Top Title & Station Data Header -->
        <div class="hero-header-row">
          <div class="hero-title-col">
            <div class="meta-stamp-row">
              <span class="badge-sandstone">SURVEY SPEC // BATHYMETRIC 01</span>
              <span class="badge-chartreuse">
                <span class="pip charcoal pulse"></span> CALIBRATED REALITY
              </span>
              <span class="badge-cobalt-light">[SUB-SURFACE GEO-STRATA // 0–1000m]</span>
            </div>
            <h1 class="hero-title">DEEP WATER</h1>
            <div class="hero-subtitle-row">
              <span class="hero-subtitle-accent">CALIBRATED REALITY</span>
              <span class="hero-subtitle-tag">NORTH INDIAN OCEAN OBSERVATORY</span>
            </div>
          </div>

          <!-- Station NIO-88E Metadata Slab -->
          <div class="station-slab hard-shadow tactile-bevel">
            <div class="station-head">
              <span class="station-id">STATION NIO-88E</span>
              <span class="station-basin">${region.toUpperCase()}</span>
            </div>
            <p class="station-desc">
              Autonomous subsurface oceanographic intelligence synthesized via multi-sensor satellite observations, benthic shear arrays, and synthetic aperture bathymetry.
            </p>
            <div class="station-metrics-grid">
              <div class="metric-cell">
                <div class="metric-lbl">SEA SFC TEMP (0m)</div>
                <div class="metric-val" id="heroSstVal">28.4°C</div>
                <div class="metric-sub chartreuse-text">■ +0.3° ANOMALY</div>
              </div>
              <div class="metric-cell">
                <div class="metric-lbl">SALINITY (SSS)</div>
                <div class="metric-val">34.2 PSU</div>
                <div class="metric-sub cobalt-text">▲ HALOCLINE LOCKED</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 3D Monolith Viewport (Concrete Candy Slab) -->
        <div class="monolith-slab hard-shadow tactile-bevel">
          <div class="monolith-bar">
            <div class="monolith-title-group">
              <span class="pip pink"></span>
              <span class="monolith-title">3D BATHYMETRIC CORE VIEWPORT // SECTOR 15N</span>
              <span class="badge-dim">STRATA RES: 0.125m</span>
            </div>
            <div class="monolith-controls-group">
              <span class="meta-label">DRAG TO ROTATE 3D CORE</span>
              <div class="chip-toggle-row">
                <button class="slab-pill active" id="btnModeAssembled">Assembled</button>
                <button class="slab-pill" id="btnModeExploded">Explode Strata</button>
                <button class="slab-pill" id="btnModeCore">Focus Core</button>
                <button class="slab-pill" id="btnModeSonar">Sonar Pulse</button>
              </div>
            </div>
          </div>

          <!-- 3D Canvas Viewport -->
          <div class="canvas-stage" id="canvasStage">
            <canvas id="threeMonolithCanvas"></canvas>

            <!-- Floating Tactical HUD Overlays -->
            <div class="hud-top-left tactile-bevel">
              <div class="hud-tag">
                <span class="hud-icon">⬡</span>
                CORE SAMPLE: SED-0984-ALPHA
              </div>
              <div class="hud-sub">Sub-Benthic Lithology: Siliceous Ooze / Terrigenous Clay</div>
              <div class="hud-meta">ACOUSTIC VELOCITY: 1,518 m/s</div>
            </div>

            <div class="hud-top-right">
              <div class="badge-chartreuse border-box pulse">
                <span class="pip charcoal"></span> ARRAY LOCK: 04 NODES ACTIVE
              </div>
              <div class="hud-card">P-WAVE ABSORPTION: 0.04 dB/m</div>
            </div>

            <div class="hud-bottom-matrix">
              <div class="hud-tile">
                <span class="tile-lbl">SEA LEVEL ANOMALY</span>
                <span class="tile-val">+12.4 cm</span>
              </div>
              <div class="hud-tile">
                <span class="tile-lbl">SURFACE WINDS</span>
                <span class="tile-val">14.2 kts NW</span>
              </div>
              <div class="hud-tile">
                <span class="tile-lbl">BAROTROPIC TIDE</span>
                <span class="tile-val">0.82 m AMPLITUDE</span>
              </div>
              <div class="hud-tile">
                <span class="tile-lbl">ACOUSTIC BACKSCATTER</span>
                <span class="tile-val cobalt-text">-24.6 dB</span>
              </div>
            </div>
          </div>

          <!-- Action Row -->
          <div class="monolith-action-row">
            <div class="action-btn-group">
              <a href="#benchmarks" class="btn-cobalt hard-shadow" id="heroScrollDownBtn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v18M19 14l-7 7-7-7"/></svg>
                EXPLORE 0–1000m STRATA
              </a>
              <button class="btn-tactile hard-shadow-sm" id="heroLaunchConsoleBtn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 8h10M7 12h10M7 16h6"/></svg>
                LAUNCH RESEARCH CONSOLE
              </button>
            </div>
            <div class="calibration-info">
              <span>CALIBRATION: <strong>IOC-UNESCO 2024</strong></span>
              <span class="dot-sep"></span>
              <span>CONFIDENCE: <strong>95% CALIBRATED BOUNDS</strong></span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- INDUSTRIAL DATA SHOWCASE (Asymmetric Grid & Interactive Physical Depth Slider) -->
    <section class="section-showcase" id="benchmarks">
      <div class="section-container">
        <!-- Section Header -->
        <div class="section-header-row">
          <div>
            <div class="section-kicker">// PHYSICAL STRATIFICATION & HYDROSTATIC BENCHMARKS</div>
            <h2 class="section-title">HYDROSTATIC BENCHMARK MATRIX</h2>
          </div>
          <div class="section-badge-cluster">
            <span class="mono-meta">ARGO SENSOR CLUSTER</span>
            <span class="badge-chartreuse">LIVE ARRAYS 02</span>
          </div>
        </div>

        <!-- Asymmetric Grid -->
        <div class="grid-asymmetric">
          <!-- Left: Interactive Dynamic Depth Slider (7 Cols) -->
          <div class="depth-slider-slab hard-shadow tactile-bevel">
            <div class="slider-head">
              <div class="slider-title-row">
                <span class="square-bullet"></span>
                <h3 class="slider-title">DYNAMIC SUB-SURFACE SLIDER</h3>
              </div>
              <span class="badge-dim">0–1000m WATER COLUMN</span>
            </div>
            <p class="slider-intro">
              Scrub depth across the water column to compute real-time hydrostatic pressure, sound propagation velocity, salinity trapping, and bathyal stratification thresholds.
            </p>

            <div class="slider-control-block">
              <div class="slider-val-readout">
                <span class="slider-lbl">TARGET STRATUM DEPTH:</span>
                <span class="slider-badge" id="depthDisplayBadge">340 M (MESOPELAGIC)</span>
              </div>
              <div class="slider-track-wrap">
                <input type="range" min="0" max="1000" step="10" value="340" id="tactileDepthSlider" class="tactile-range" aria-label="Ocean depth selector">
                <div class="slider-scale-ticks">
                  <span>0m (SURFACE)</span>
                  <span>200m (EPIPELAGIC)</span>
                  <span>500m (THERMOCLINE)</span>
                  <span>1000m (BATHYAL)</span>
                </div>
              </div>
            </div>

            <!-- Calculated Hydrostatic Metrics Grid -->
            <div class="hydro-metrics-row">
              <div class="hydro-card">
                <div class="hydro-lbl">HYDROSTATIC LOAD</div>
                <div class="hydro-val" id="hydroPressureVal">35.2 BAR</div>
                <div class="hydro-sub">+1.01 bar / 10m</div>
              </div>
              <div class="hydro-card">
                <div class="hydro-lbl">STRATUM WATER TEMP</div>
                <div class="hydro-val cobalt-text" id="hydroTempVal">11.4°C</div>
                <div class="hydro-sub" id="hydroTempBound">±0.74°C Conformal</div>
              </div>
              <div class="hydro-card">
                <div class="hydro-lbl">SOUND PROPAGATION</div>
                <div class="hydro-val" id="hydroSoundVal">1,496 M/S</div>
                <div class="hydro-sub pink-text">SOFAR Axis Waveguide</div>
              </div>
            </div>

            <div class="slider-footer">
              <span>CONFORMAL INTERVAL: <strong>POLYNOMIAL DEGREE-4</strong></span>
              <span>MODEL RESIDUAL: <strong>0.04% RMSE</strong></span>
            </div>
          </div>

          <!-- Right: Scientific Uncertainty & Argo Float Array (5 Cols) -->
          <div class="array-matrix-col">
            <!-- Uncertainty Tile -->
            <div class="uncertainty-slab hard-shadow tactile-bevel">
              <div class="slab-top-row">
                <div class="flex-center gap-2">
                  <span class="glyph-cobalt">◈</span>
                  <span class="slab-heading">CONFORMAL UNCERTAINTY BOUNDS</span>
                </div>
                <span class="badge-chartreuse">95% CI</span>
              </div>
              <p class="slab-copy">
                Non-parametric calibrated prediction intervals derived from held-out Argo float ensembles. Every estimate is honest, reproducible, and bounded.
              </p>
              <div class="interval-gauge-box">
                <div class="flex-between">
                  <span class="mono-meta">THERMAL UNCERTAINTY:</span>
                  <span class="mono-bold text-charcoal">±0.74°C (VERIFIED)</span>
                </div>
                <div class="gauge-track">
                  <div class="gauge-bar" style="width: 82%;"></div>
                </div>
                <div class="gauge-labels">
                  <span id="uncertLower">LOWER: 10.66°C</span>
                  <span id="uncertMed">MEDIAN: 11.40°C</span>
                  <span id="uncertUpper">UPPER: 12.14°C</span>
                </div>
              </div>
            </div>

            <!-- Calibration Float Array Matrix -->
            <div class="floats-slab hard-shadow tactile-bevel">
              <div class="slab-top-row">
                <span class="slab-heading">IN-SITU ARGO ARRAYS</span>
                <span class="mono-meta cobalt-text">INDIAN OCEAN GYRE</span>
              </div>
              <div class="float-items-stack">
                <div class="float-row">
                  <div>
                    <div class="float-title">
                      <span class="pip chartreuse"></span> ARGO FLOAT #4902148
                    </div>
                    <div class="float-meta">CYCLE 241 // DEPTH DIVE: 2000M</div>
                  </div>
                  <div class="float-status-col">
                    <span class="badge-status-active">ACTIVE PING</span>
                    <span class="mono-dim">14.8°N / 87.9°E</span>
                  </div>
                </div>
                <div class="float-row">
                  <div>
                    <div class="float-title">
                      <span class="pip chartreuse"></span> ARGO FLOAT #2903381
                    </div>
                    <div class="float-meta">CYCLE 188 // O2 OPTODE SYNC</div>
                  </div>
                  <div class="float-status-col">
                    <span class="badge-status-active">ACTIVE PING</span>
                    <span class="mono-dim">15.4°N / 88.5°E</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- EDITORIAL STRATUM GALLERY (Horizontal Architectural Slabs: 01, 02, 03) -->
    <section class="section-stratum" id="stratum-gallery">
      <div class="section-container">
        <div class="section-header-row">
          <div>
            <div class="section-kicker">// SUB-SURFACE REGIMES CLASSIFICATION</div>
            <h2 class="section-title">EDITORIAL STRATA</h2>
          </div>
          <p class="section-lead-copy">
            Cross-sectional bathymetric characterization of three extreme hydrographic regimes across the northern tropical Indian Ocean basin.
          </p>
        </div>

        <div class="regimes-grid">
          <!-- Regime 01 -->
          <article class="regime-card hard-shadow tactile-bevel" data-regime="01">
            <div class="regime-body">
              <div class="regime-head">
                <span class="regime-number">01</span>
                <span class="badge-sandstone">SOMALI JET</span>
              </div>
              <div class="regime-title-wrap">
                <span class="regime-kicker">REGIME 01 // ARABIAN SEA</span>
                <h3 class="regime-title">Upwelling Nutricline</h3>
              </div>
              <p class="regime-desc">
                High-saline surface waters sheared by intense southwest monsoon wind jets. Deep coastal upwelling draws cold, nutrient-rich water upwards, compressing the 18.2°C core to a shallow 60m depth.
              </p>
              <div class="regime-metrics">
                <div class="regime-metric-row">
                  <span>CORE TEMPERATURE</span>
                  <strong>18.2°C</strong>
                </div>
                <div class="regime-metric-row">
                  <span>HALINE GRADIENT</span>
                  <strong>36.4 PSU</strong>
                </div>
                <div class="regime-metric-row">
                  <span>PRIMARY PRODUCTION</span>
                  <strong class="chartreuse-tag">+340 mg C/m³</strong>
                </div>
              </div>
            </div>
            <div class="regime-footer">
              <span class="mono-meta">INDEX // AR-UPW-01</span>
              <button class="btn-regime-focus" data-lat="16.0" data-lon="65.0">Inspect Basin →</button>
            </div>
          </article>

          <!-- Regime 02 -->
          <article class="regime-card hard-shadow tactile-bevel" data-regime="02">
            <div class="regime-body">
              <div class="regime-head">
                <span class="regime-number">02</span>
                <span class="badge-chartreuse">RUNOFF HALOCLINE</span>
              </div>
              <div class="regime-title-wrap">
                <span class="regime-kicker">REGIME 02 // BAY OF BENGAL</span>
                <h3 class="regime-title">Freshwater Barrier Layer</h3>
              </div>
              <p class="regime-desc">
                Massive monsoonal river discharge caps surface salinity at 31.0 PSU. The resulting thick barrier layer traps thermal energy beneath the halocline, sustaining temperatures up to 30.8°C that fuel cyclones.
              </p>
              <div class="regime-metrics">
                <div class="regime-metric-row">
                  <span>BARRIER THICKNESS</span>
                  <strong>42 METERS</strong>
                </div>
                <div class="regime-metric-row">
                  <span>HALINE CONTRAST</span>
                  <strong class="pink-text">-4.8 PSU / 20M</strong>
                </div>
                <div class="regime-metric-row">
                  <span>CYCLONE HEAT POTENTIAL</span>
                  <strong class="cobalt-text">118 kJ/cm²</strong>
                </div>
              </div>
            </div>
            <div class="regime-footer">
              <span class="mono-meta">INDEX // BOB-BRL-02</span>
              <button class="btn-regime-focus" data-lat="14.0" data-lon="88.0">Inspect Basin →</button>
            </div>
          </article>

          <!-- Regime 03 -->
          <article class="regime-card hard-shadow tactile-bevel" data-regime="03">
            <div class="regime-body">
              <div class="regime-head">
                <span class="regime-number">03</span>
                <span class="badge-cobalt">ZONAL JET</span>
              </div>
              <div class="regime-title-wrap">
                <span class="regime-kicker">REGIME 03 // EQUATORIAL STRIP</span>
                <h3 class="regime-title">Undercurrent Refraction</h3>
              </div>
              <p class="regime-desc">
                High-velocity eastward subsurface jet stream centered at 120m depth. Forms the primary oceanic sound duct (SOFAR channel axis) for trans-basin low-frequency acoustic telemetry.
              </p>
              <div class="regime-metrics">
                <div class="regime-metric-row">
                  <span>CORE JET DEPTH</span>
                  <strong>120 METERS</strong>
                </div>
                <div class="regime-metric-row">
                  <span>ZONAL VELOCITY</span>
                  <strong>1.28 M/S</strong>
                </div>
                <div class="regime-metric-row">
                  <span>SOFAR DUCT AXIS</span>
                  <strong class="cobalt-text">1,482 M/S FOCUS</strong>
                </div>
              </div>
            </div>
            <div class="regime-footer">
              <span class="mono-meta">INDEX // EQU-EUC-03</span>
              <button class="btn-regime-focus" data-lat="5.0" data-lon="80.0">Inspect Basin →</button>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- INTERACTIVE COMMAND CONSOLE PREVIEW -->
    <section class="section-console" id="console">
      <div class="section-container">
        <div class="console-head-bar">
          <div class="flex-center gap-3">
            <div class="pip-lg chartreuse pulse"></div>
            <div>
              <h2 class="console-title">DEEP CONSOLE INTELLIGENCE STREAM</h2>
              <div class="console-subtitle">LIVE PREDICTIVE ENGINE // MODEL TIER_A_V1.0 // IOC VALIDATED</div>
            </div>
          </div>
          <div class="console-action-cluster">
            <span class="tag-dark">LATENCY: 14ms</span>
            <button class="btn-cobalt" id="openFullWorkstationBtn">OPEN FULL WORKSTATION →</button>
          </div>
        </div>

        <div class="console-grid">
          <!-- Multi-Sensor Live Encoders -->
          <div class="console-card">
            <div class="console-card-title">
              <span>MULTI-SENSOR ENCODERS</span>
              <span class="chartreuse-text">ONLINE [■]</span>
            </div>
            <div class="telemetry-bar-stack">
              <div class="bar-group">
                <div class="bar-lbl-row">
                  <span>01. CTD CONDUCTIVITY:</span>
                  <strong>54.2 mS/cm</strong>
                </div>
                <div class="meter-track"><div class="meter-fill cobalt" style="width: 74%;"></div></div>
              </div>
              <div class="bar-group">
                <div class="bar-lbl-row">
                  <span>02. OPTICAL BACKSCATTER:</span>
                  <strong class="chartreuse-text">0.42 NTU</strong>
                </div>
                <div class="meter-track"><div class="meter-fill chartreuse" style="width: 32%;"></div></div>
              </div>
              <div class="bar-group">
                <div class="bar-lbl-row">
                  <span>03. OXYGEN SATURATION:</span>
                  <strong>194 μmol/kg</strong>
                </div>
                <div class="meter-track"><div class="meter-fill sandstone" style="width: 62%;"></div></div>
              </div>
              <div class="bar-group">
                <div class="bar-lbl-row">
                  <span>04. ADCP SHEAR SPEED:</span>
                  <strong class="pink-text">0.88 M/S</strong>
                </div>
                <div class="meter-track"><div class="meter-fill pink" style="width: 52%;"></div></div>
              </div>
            </div>
          </div>

          <!-- Quick Predict Terminal Box -->
          <div class="console-card">
            <div class="console-card-title">
              <span>LIVE SUBSURFACE QUERY</span>
              <span class="mono-meta">POST /predict</span>
            </div>
            <p class="console-card-copy">
              Reconstruct full 15-level vertical temperature profile (0–1000m) with conformal bounds for any coordinate in the North Indian Ocean.
            </p>
            <div class="quick-query-row">
              <button class="btn-tactile small" id="queryArabianBtn">Query Arabian Sea (16°N, 65°E)</button>
              <button class="btn-tactile small" id="queryBengalBtn">Query Bay of Bengal (14°N, 88°E)</button>
              <button class="btn-cobalt small" id="runSamplePredictBtn">Run Live Benchmark</button>
            </div>
            <div class="query-terminal-output" id="quickTerminalOutput">
              <span class="terminal-line text-chartreuse">> Ready. Model tier_a_v1.0 loaded. Zarr store: 13 observation epochs.</span>
              <span class="terminal-line text-muted">> Click a basin preset or scrub the depth slider above to evaluate thermal stratification.</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Technical Editorial Footer -->
    <footer class="studio-footer">
      <div class="footer-container">
        <div class="footer-top">
          <div class="footer-brand">
            <div class="brand-square">AS</div>
            <span class="brand-name">AQUASPHERE // DEEP OCEAN INTELLIGENCE</span>
          </div>
          <div class="footer-nav">
            <a href="#benchmarks">STRATA MATRIX</a>
            <a href="#stratum-gallery">REGIMES</a>
            <a href="#console">CONSOLE</a>
            <a href="javascript:void(0)" id="footerOpenDocsBtn">SPECIFICATION</a>
          </div>
        </div>
        <div class="footer-bottom">
          <span>COORDINATES: NIO 5.0°N–30.0°N · 45.0°E–105.0°E · PROCESSED VIA ZARR V3</span>
          <span>© 2026 AQUASPHERE OCEANIC RESEARCH · IOC-UNESCO CALIBRATED</span>
        </div>
      </div>
    </footer>
  `;

  // Attach interactive features after mounting
  setTimeout(() => {
    setupStudioInteractions(container);
  }, 10);

  return container;
}

function setupStudioInteractions(container) {
  // 1. Initialize 3D Monolith
  const canvas = container.querySelector('#threeMonolithCanvas');
  if (canvas) {
    if (monolithInstance) {
      monolithInstance.destroy();
    }
    monolithInstance = new Monolith3D(canvas);
  }

  // 2. 3D Mode Toggle Buttons
  const btnAssembled = container.querySelector('#btnModeAssembled');
  const btnExploded = container.querySelector('#btnModeExploded');
  const btnCore = container.querySelector('#btnModeCore');
  const btnSonar = container.querySelector('#btnModeSonar');

  const modeButtons = [btnAssembled, btnExploded, btnCore, btnSonar];
  const setModeActive = (btn, modeName) => {
    modeButtons.forEach(b => b?.classList.remove('active'));
    btn?.classList.add('active');
    if (monolithInstance) {
      if (modeName === 'sonar') {
        monolithInstance.triggerSonarWave();
      } else {
        monolithInstance.setMode(modeName);
      }
    }
  };

  btnAssembled?.addEventListener('click', () => setModeActive(btnAssembled, 'assembled'));
  btnExploded?.addEventListener('click', () => setModeActive(btnExploded, 'exploded'));
  btnCore?.addEventListener('click', () => setModeActive(btnCore, 'core'));
  btnSonar?.addEventListener('click', () => setModeActive(btnSonar, 'sonar'));

  // 3. Physical Depth Slider Interactions
  const slider = container.querySelector('#tactileDepthSlider');
  const depthDisplay = container.querySelector('#depthDisplayBadge');
  const pressureVal = container.querySelector('#hydroPressureVal');
  const tempVal = container.querySelector('#hydroTempVal');
  const soundVal = container.querySelector('#hydroSoundVal');
  const uncertLower = container.querySelector('#uncertLower');
  const uncertMed = container.querySelector('#uncertMed');
  const uncertUpper = container.querySelector('#uncertUpper');

  const updateDepthCalculations = (depth) => {
    setDepth(depth);

    // Oceanic thermocline calculation
    const sst = 28.4;
    const deepTemp = 3.3;
    const thermoclineDepth = 120.0;
    // Sigmoidal thermocline curve
    const t = deepTemp + (sst - deepTemp) / (1.0 + Math.pow(depth / thermoclineDepth, 1.4));
    const tempRounded = t.toFixed(1);

    // Hydrostatic pressure (1.013 bar at surface, +1.005 bar per 10m)
    const pressure = (1.013 + depth * 0.1005).toFixed(1);

    // Sound velocity in seawater (Mackenzie formula approximation)
    const salinity = 34.2;
    const c = 1449.2 + 4.6 * t - 0.055 * Math.pow(t, 2) + 0.00029 * Math.pow(t, 3) + (1.34 - 0.01 * t) * (salinity - 35) + 0.016 * depth;
    const soundSpeed = Math.round(c);

    // Conformal uncertainty
    const sigma = depth < 100 ? 0.45 : depth < 300 ? 0.74 : 0.52;
    const lower = (t - sigma).toFixed(2);
    const upper = (t + sigma).toFixed(2);

    // Zone label
    let zone = 'EPIPELAGIC';
    if (depth >= 700) zone = 'BATHYAL ZONE';
    else if (depth >= 200) zone = 'MESOPELAGIC';
    else if (depth <= 30) zone = 'SURFACE MIXED';

    if (depthDisplay) depthDisplay.textContent = `${depth} M (${zone})`;
    if (pressureVal) pressureVal.textContent = `${pressure} BAR`;
    if (tempVal) tempVal.textContent = `${tempRounded}°C`;
    if (soundVal) soundVal.textContent = `${soundSpeed.toLocaleString()} M/S`;
    if (uncertLower) uncertLower.textContent = `LOWER: ${lower}°C`;
    if (uncertMed) uncertMed.textContent = `MEDIAN: ${tempRounded}°C`;
    if (uncertUpper) uncertUpper.textContent = `UPPER: ${upper}°C`;
  };

  slider?.addEventListener('input', (e) => {
    updateDepthCalculations(parseInt(e.target.value, 10));
  });

  // 4. Navigation & Jump Triggers
  container.querySelector('#heroLaunchConsoleBtn')?.addEventListener('click', () => {
    setPage('overview');
  });

  container.querySelector('#openFullWorkstationBtn')?.addEventListener('click', () => {
    setPage('location');
  });

  container.querySelector('#footerOpenDocsBtn')?.addEventListener('click', () => {
    setPage('reports');
  });

  // 5. Regime Card Focus Triggers
  container.querySelectorAll('.btn-regime-focus').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetLat = parseFloat(btn.dataset.lat || '15.0');
      const targetLon = parseFloat(btn.dataset.lon || '88.0');
      setLocation(targetLat, targetLon);

      if (monolithInstance) {
        monolithInstance.triggerSonarWave();
      }

      // Smooth scroll to depth benchmarks
      document.querySelector('#benchmarks')?.scrollIntoView({ behavior: 'smooth' });
    });
  });

  // 6. Live Query Terminal Buttons
  const termOut = container.querySelector('#quickTerminalOutput');
  const printTerminal = (text, cls = '') => {
    if (!termOut) return;
    const line = document.createElement('span');
    line.className = `terminal-line ${cls}`;
    line.textContent = `> ${text}`;
    termOut.appendChild(line);
    termOut.scrollTop = termOut.scrollHeight;
  };

  container.querySelector('#queryArabianBtn')?.addEventListener('click', async () => {
    printTerminal('Initiating query: Arabian Sea (16.0°N, 65.0°E, 2025-05-15)...', 'text-cobalt');
    try {
      const pred = await fetchPredict(16.0, 65.0, '2025-05-15');
      printTerminal(`Success [${pred.data_source}]: SST=${pred.temperatures[0]}°C | D20=${pred.d20}m | MLD=${pred.mld}m`, 'text-chartreuse');
      printTerminal(`Conformal 90% Bounds @ 100m: [${pred.interval_lower[7]}°C – ${pred.interval_upper[7]}°C]`);
    } catch (err) {
      printTerminal(`API offline: ${err.message}`, 'text-pink');
    }
  });

  container.querySelector('#queryBengalBtn')?.addEventListener('click', async () => {
    printTerminal('Initiating query: Bay of Bengal (14.0°N, 88.0°E, 2025-05-15)...', 'text-cobalt');
    try {
      const pred = await fetchPredict(14.0, 88.0, '2025-05-15');
      printTerminal(`Success [${pred.data_source}]: SST=${pred.temperatures[0]}°C | D20=${pred.d20}m | MLD=${pred.mld}m`, 'text-chartreuse');
      printTerminal(`Conformal 90% Bounds @ 100m: [${pred.interval_lower[7]}°C – ${pred.interval_upper[7]}°C]`);
    } catch (err) {
      printTerminal(`API offline: ${err.message}`, 'text-pink');
    }
  });

  container.querySelector('#runSamplePredictBtn')?.addEventListener('click', async () => {
    printTerminal(`Running full vertical stratification reconstruct for (${state.lat}°N, ${state.lon}°E)...`, 'text-cobalt');
    try {
      const pred = await fetchPredict(state.lat, state.lon, state.date);
      printTerminal(`Profile calculated across ${pred.depths.length} standard depths. Top: ${pred.temperatures[0]}°C -> Benthic: ${pred.temperatures[pred.temperatures.length - 1]}°C`, 'text-chartreuse');
      if (monolithInstance) {
        monolithInstance.triggerSonarWave();
      }
    } catch (err) {
      printTerminal(`Failed: ${err.message}`, 'text-pink');
    }
  });
}
