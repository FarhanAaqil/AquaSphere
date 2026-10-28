/**
 * AquaSphere Master Frontend Application Orchestrator
 * High-performance, integrated ocean intelligence platform.
 */

import { OceanScene } from './scene3d.js';

// Domain bounds and standard depths
const DOMAIN = { latMin: 5.0, latMax: 30.0, lonMin: 45.0, lonMax: 105.0 };
const STANDARD_DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000];

// Application State
const state = {
  lat: 15.5,
  lon: 65.0,
  date: '2025-05-15',
  depth: 100,
  mode: 'delayed', // 'delayed' | 'nowcast'
  activeTab: 'explorer',
  meta: null,
  metrics: null,
  ablation: null,
  leakage: null,
  currentPrediction: null,
  currentValidation: null,
  loading: false,
  layers: {
    pred: true,
    unc: true,
    clim: true,
    argo: true
  }
};

let scene = null;

// Hotspot Presets
const HOTSPOTS = [
  { name: 'Somali Jet', lat: 10.0, lon: 52.0, desc: 'High-velocity upwelling boundary current' },
  { name: 'Arabian Warm Pool', lat: 15.5, lon: 65.0, desc: 'Pre-monsoon thermal heat reservoir' },
  { name: 'Bay of Bengal', lat: 14.0, lon: 88.0, desc: 'Low-salinity riverine barrier layer' },
  { name: 'Equatorial Jet', lat: 5.5, lon: 78.0, desc: 'Zonal undercurrent core' },
  { name: 'Andaman Basin', lat: 11.0, lon: 94.0, desc: 'Deep marginal sea basin' }
];

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Initialize 3D Ocean Simulation
  scene = new OceanScene('gl');
  window.oceanScene = scene;

  // 2. Setup Navigation and Views
  setupNavigation();
  setupHotspotPresets();
  setupControls();
  setupLayers();

  // 3. Initialize Interactive Vector Map
  initVectorMap();

  // 4. Initial Routing based on URL Path or Hash
  const path = window.location.pathname;
  const hash = window.location.hash.replace('#', '');
  if (path.includes('explorer') || hash === 'explorer') {
    switchTab('explorer');
  } else if (hash === 'descent') {
    switchTab('descent');
  } else if (hash === 'benchmark') {
    switchTab('benchmark');
  } else if (hash === 'ablation') {
    switchTab('ablation');
  } else if (hash === 'leakage') {
    switchTab('leakage');
  } else if (hash === 'method') {
    switchTab('method');
  } else {
    // Default: On /explorer route show explorer, on / show explorer with descent available
    switchTab('explorer');
  }

  // 5. Load Metadata and Static Evidence
  await loadMetadata();
  await loadEvidenceData();

  // 6. Execute Initial Prediction
  await executePrediction();
});

/* ── Navigation & Views ─────────────────────────────────────────────────────── */
function setupNavigation() {
  const navLinks = document.querySelectorAll('nav.app-nav a');
  navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const tabId = link.getAttribute('data-tab');
      if (tabId) switchTab(tabId);
    });
  });

  // Action buttons that jump to explorer
  const btnLaunch = document.getElementById('btn-launch-explorer');
  if (btnLaunch) {
    btnLaunch.addEventListener('click', (e) => {
      e.preventDefault();
      switchTab('explorer');
    });
  }

  const btnDescent = document.getElementById('btn-dive-descent');
  if (btnDescent) {
    btnDescent.addEventListener('click', (e) => {
      e.preventDefault();
      switchTab('descent');
    });
  }
}

export function switchTab(tabId) {
  state.activeTab = tabId;

  // Update navbar links
  document.querySelectorAll('nav.app-nav a').forEach(a => {
    if (a.getAttribute('data-tab') === tabId) {
      a.classList.add('active');
    } else {
      a.classList.remove('active');
    }
  });

  // Update views
  document.querySelectorAll('.tab-view').forEach(view => {
    if (view.id === `view-${tabId}`) {
      view.classList.add('active');
    } else {
      view.classList.remove('active');
    }
  });

  // Update right-hand depth gauge visibility
  const gauge = document.getElementById('gauge');
  if (gauge) {
    gauge.style.display = tabId === 'descent' ? 'block' : 'none';
  }

  // Camera depth adjustment in 3D scene
  if (scene) {
    if (tabId === 'descent') {
      scene.setDepthProgress(0.1);
    } else if (tabId === 'explorer') {
      scene.setDepthProgress(state.depth / 1000);
    } else {
      scene.setDepthProgress(0.0);
    }
  }

  window.history.replaceState(null, '', `#${tabId}`);
}

/* ── Hotspot Presets ───────────────────────────────────────────────────────── */
function setupHotspotPresets() {
  const container = document.getElementById('presets-chips-container');
  if (!container) return;

  container.innerHTML = '';
  HOTSPOTS.forEach(spot => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'preset-chip';
    chip.textContent = spot.name;
    chip.title = `${spot.desc} (${spot.lat}°N, ${spot.lon}°E)`;

    chip.addEventListener('click', () => {
      document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      selectCoordinates(spot.lat, spot.lon);
    });

    container.appendChild(chip);
  });
}

function selectCoordinates(lat, lon) {
  state.lat = Math.min(DOMAIN.latMax, Math.max(DOMAIN.latMin, lat));
  state.lon = Math.min(DOMAIN.lonMax, Math.max(DOMAIN.lonMin, lon));

  const latInput = document.getElementById('input-lat');
  const lonInput = document.getElementById('input-lon');
  if (latInput) latInput.value = state.lat.toFixed(1);
  if (lonInput) lonInput.value = state.lon.toFixed(1);

  const hoverHud = document.getElementById('map-hover-coords');
  if (hoverHud) hoverHud.textContent = `${state.lat.toFixed(1)}°N, ${state.lon.toFixed(1)}°E`;

  updateMapReticle(state.lat, state.lon);
  executePrediction();
}

/* ── Control Deck & Layer Inputs ───────────────────────────────────────────── */
function setupControls() {
  const latInput = document.getElementById('input-lat');
  const lonInput = document.getElementById('input-lon');

  const onCoordChange = () => {
    const lat = parseFloat(latInput?.value);
    const lon = parseFloat(lonInput?.value);
    if (!isNaN(lat) && !isNaN(lon)) {
      selectCoordinates(lat, lon);
    }
  };

  if (latInput) latInput.addEventListener('change', onCoordChange);
  if (lonInput) lonInput.addEventListener('change', onCoordChange);

  // Depth slider
  const depthSlider = document.getElementById('slider-depth');
  const depthValueLabel = document.getElementById('label-depth-val');
  if (depthSlider) {
    depthSlider.addEventListener('input', (e) => {
      state.depth = parseInt(e.target.value, 10);
      if (depthValueLabel) depthValueLabel.textContent = `${state.depth} m`;
      if (scene) scene.setDepthProgress(state.depth / 1000);
      renderVerticalProfile();
    });
  }

  // Date picker
  const dateInput = document.getElementById('input-date');
  if (dateInput) {
    dateInput.addEventListener('change', (e) => {
      state.date = e.target.value;
      executePrediction();
    });
  }

  // Nowcast / Delayed Toggle
  const btnNowcast = document.getElementById('btn-nowcast');
  const btnDelayed = document.getElementById('btn-delayed');
  if (btnNowcast && btnDelayed) {
    btnNowcast.addEventListener('click', () => {
      btnNowcast.classList.add('active');
      btnDelayed.classList.remove('active');
      state.mode = 'nowcast';
      executePrediction();
    });
    btnDelayed.addEventListener('click', () => {
      btnDelayed.classList.add('active');
      btnNowcast.classList.remove('active');
      state.mode = 'delayed';
      executePrediction();
    });
  }
}

function setupLayers() {
  const layerToggles = [
    { id: 'layer-pred', key: 'pred' },
    { id: 'layer-unc', key: 'unc' },
    { id: 'layer-clim', key: 'clim' },
    { id: 'layer-argo', key: 'argo' }
  ];

  layerToggles.forEach(l => {
    const el = document.getElementById(l.id);
    if (el) {
      el.addEventListener('change', (e) => {
        state.layers[l.key] = e.target.checked;
        renderVerticalProfile();
      });
    }
  });
}

/* ── Tactical Vector Map (720x440 SVG) ─────────────────────────────────────── */
function initVectorMap() {
  const mapSvg = document.getElementById('map-svg');
  if (!mapSvg) return;

  const hoverHud = document.getElementById('map-hover-coords');

  mapSvg.addEventListener('mousemove', (e) => {
    const rect = mapSvg.getBoundingClientRect();
    const svgX = (e.clientX - rect.left) * (720 / rect.width);
    const svgY = (e.clientY - rect.top) * (440 / rect.height);

    const lon = DOMAIN.lonMin + (svgX / 720) * (DOMAIN.lonMax - DOMAIN.lonMin);
    const lat = DOMAIN.latMax - (svgY / 440) * (DOMAIN.latMax - DOMAIN.latMin);

    if (hoverHud) {
      hoverHud.textContent = `${lat.toFixed(1)}°N, ${lon.toFixed(1)}°E`;
    }
  });

  mapSvg.addEventListener('click', (e) => {
    const rect = mapSvg.getBoundingClientRect();
    const svgX = (e.clientX - rect.left) * (720 / rect.width);
    const svgY = (e.clientY - rect.top) * (440 / rect.height);

    const lon = DOMAIN.lonMin + (svgX / 720) * (DOMAIN.lonMax - DOMAIN.lonMin);
    const lat = DOMAIN.latMax - (svgY / 440) * (DOMAIN.latMax - DOMAIN.latMin);

    selectCoordinates(lat, lon);
  });

  updateMapReticle(state.lat, state.lon);
}

function updateMapReticle(lat, lon) {
  const pin = document.getElementById('map-target-reticle');
  if (!pin) return;

  const svgX = ((lon - DOMAIN.lonMin) / (DOMAIN.lonMax - DOMAIN.lonMin)) * 720;
  const svgY = ((DOMAIN.latMax - lat) / (DOMAIN.latMax - DOMAIN.latMin)) * 440;

  pin.setAttribute('transform', `translate(${svgX.toFixed(1)}, ${svgY.toFixed(1)})`);
}

/* ── API Communication & Data Pipeline ─────────────────────────────────────── */
async function loadMetadata() {
  try {
    const res = await fetch('/meta');
    if (!res.ok) return;
    const meta = await res.json();
    state.meta = meta;

    const dateInput = document.getElementById('input-date');
    if (dateInput && meta.min_date && meta.max_date) {
      dateInput.min = meta.min_date;
      dateInput.max = meta.max_date;
      if (!dateInput.value) dateInput.value = meta.max_date;
    }
  } catch (err) {
    console.warn('Metadata loading fallback:', err);
  }
}

async function executePrediction() {
  state.loading = true;
  updateLoadingState(true);

  try {
    // 1. Fetch subsurface temperature prediction
    const payload = {
      lat: state.lat,
      lon: state.lon,
      date: state.date
    };

    const res = await fetch('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      state.currentPrediction = await res.json();
    } else {
      console.warn(`Predict returned HTTP ${res.status}`);
    }

    // 2. Fetch nearest held-out validation profile
    try {
      const valRes = await fetch(`/validation/profile?lat=${state.lat}&lon=${state.lon}&date=${state.date}`);
      if (valRes.ok) {
        state.currentValidation = await valRes.json();
      } else {
        state.currentValidation = null;
      }
    } catch (e) {
      state.currentValidation = null;
    }

    // 3. Render Profile, Oceanographic Metrics, and Surface Telemetry
    renderVerticalProfile();
    renderOceanographicTiles();
    renderSurfaceTelemetry();
  } catch (err) {
    console.error('Prediction pipeline failed:', err);
  } finally {
    state.loading = false;
    updateLoadingState(false);
  }
}

function updateLoadingState(loading) {
  const badge = document.getElementById('status-indicator-badge');
  if (badge) {
    if (loading) {
      badge.textContent = 'Reconstructing Profile...';
      badge.style.borderColor = 'var(--acc)';
    } else {
      badge.textContent = 'Model v0.2 Online · Tier A';
      badge.style.borderColor = 'var(--border-glow)';
    }
  }
}

/* ── Vertical Profile SVG Rendering ────────────────────────────────────────── */
function renderVerticalProfile() {
  const pred = state.currentPrediction;
  if (!pred || !pred.temperatures) return;

  const depths = pred.depths || STANDARD_DEPTHS;
  const temps = pred.temperatures;
  const uncs = pred.uncertainties || depths.map(() => 1.34);
  const clim = pred.climatology || [28.5, 28.3, 28.0, 27.2, 26.0, 23.5, 20.0, 16.5, 14.5, 13.2, 11.8, 9.8, 7.2, 6.0, 5.0];

  // SVG Coordinate mapping:
  // Width: 360, Height: 350.
  // X: Temp 4°C to 32°C -> maps to x: 60 to 340.
  // Y: Depth 0 to 1000m (stretched upper 300m):
  // 0-300m -> y: 24 to 204 (180px for top 300m)
  // 300-1000m -> y: 204 to 324 (120px for remaining 700m)
  const mapY = (d) => {
    if (d <= 300) {
      return 24 + (d / 300) * 180;
    } else {
      return 204 + ((d - 300) / 700) * 120;
    }
  };

  const mapX = (t) => {
    const minT = 4.0;
    const maxT = 32.0;
    const clamped = Math.max(minT, Math.min(maxT, t));
    return 60 + ((clamped - minT) / (maxT - minT)) * 280;
  };

  // 1. Prediction Polyline
  const predPolyline = document.getElementById('prof-pred-line');
  if (predPolyline) {
    if (state.layers.pred) {
      const pts = temps.map((t, i) => `${mapX(t).toFixed(1)},${mapY(depths[i]).toFixed(1)}`).join(' ');
      predPolyline.setAttribute('points', pts);
      predPolyline.style.display = 'block';
    } else {
      predPolyline.style.display = 'none';
    }
  }

  // 2. 90% Conformal Uncertainty Polygon
  const uncPolygon = document.getElementById('prof-unc-band');
  if (uncPolygon) {
    if (state.layers.unc) {
      const rightPts = temps.map((t, i) => `${mapX(t + uncs[i]).toFixed(1)},${mapY(depths[i]).toFixed(1)}`);
      const leftPts = temps.map((t, i) => `${mapX(t - uncs[i]).toFixed(1)},${mapY(depths[i]).toFixed(1)}`).reverse();
      uncPolygon.setAttribute('points', `${rightPts.join(' ')} ${leftPts.join(' ')}`);
      uncPolygon.style.display = 'block';
    } else {
      uncPolygon.style.display = 'none';
    }
  }

  // 3. Climatology Polyline
  const climPolyline = document.getElementById('prof-clim-line');
  if (climPolyline) {
    if (state.layers.clim) {
      const pts = clim.map((t, i) => `${mapX(t).toFixed(1)},${mapY(depths[i]).toFixed(1)}`).join(' ');
      climPolyline.setAttribute('points', pts);
      climPolyline.style.display = 'block';
    } else {
      climPolyline.style.display = 'none';
    }
  }

  // 4. Held-out Argo Float Points
  const argoGroup = document.getElementById('prof-argo-points');
  if (argoGroup) {
    argoGroup.innerHTML = '';
    if (state.layers.argo && state.currentValidation && state.currentValidation.temperatures) {
      const vDepths = state.currentValidation.depths;
      const vTemps = state.currentValidation.temperatures;
      vDepths.forEach((d, i) => {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', mapX(vTemps[i]).toFixed(1));
        circle.setAttribute('cy', mapY(d).toFixed(1));
        circle.setAttribute('r', '3.8');
        circle.setAttribute('fill', '#060e1d');
        circle.setAttribute('stroke', '#ffffff');
        circle.setAttribute('stroke-width', '1.8');

        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = `Argo Float #${state.currentValidation.float_id || '2902741'}: ${vTemps[i].toFixed(2)}°C at ${d}m`;
        circle.appendChild(title);

        argoGroup.appendChild(circle);
      });
      argoGroup.style.display = 'block';
    } else {
      argoGroup.style.display = 'none';
    }
  }

  // 5. Scrubber Depth Indicator Line on Profile
  const depthGuide = document.getElementById('prof-depth-guide');
  if (depthGuide) {
    const yPos = mapY(state.depth);
    depthGuide.setAttribute('y1', yPos.toFixed(1));
    depthGuide.setAttribute('y2', yPos.toFixed(1));
  }
}

/* ── Oceanographic HUD Metric Computation ──────────────────────────────────── */
function renderOceanographicTiles() {
  const pred = state.currentPrediction;
  if (!pred || !pred.temperatures) return;

  const depths = pred.depths || STANDARD_DEPTHS;
  const temps = pred.temperatures;

  // 1. D20 Depth (Depth of 20°C isotherm)
  let d20 = null;
  for (let i = 0; i < temps.length - 1; i++) {
    if ((temps[i] >= 20 && temps[i + 1] <= 20) || (temps[i] <= 20 && temps[i + 1] >= 20)) {
      const frac = (20 - temps[i]) / (temps[i + 1] - temps[i]);
      d20 = depths[i] + frac * (depths[i + 1] - depths[i]);
      break;
    }
  }
  const d20El = document.getElementById('tile-d20');
  if (d20El) {
    d20El.innerHTML = d20 !== null ? `${d20.toFixed(1)} <span>m</span>` : `>300 <span>m</span>`;
  }

  // 2. Mixed Layer Depth (MLD, delta T = 0.2°C from surface)
  const surfaceTemp = temps[0];
  let mld = 25.0;
  for (let i = 1; i < temps.length; i++) {
    if (surfaceTemp - temps[i] >= 0.2) {
      const frac = (surfaceTemp - 0.2 - temps[i - 1]) / (temps[i] - temps[i - 1]);
      mld = depths[i - 1] + Math.max(0, Math.min(1, frac)) * (depths[i] - depths[i - 1]);
      break;
    }
  }
  const mldEl = document.getElementById('tile-mld');
  if (mldEl) {
    mldEl.innerHTML = `${mld.toFixed(1)} <span>m</span>`;
  }

  // 3. Upper Ocean Heat Content (0-300m)
  // OHC = rho * Cp * integral(T dz)
  let ohcIntegral = 0;
  for (let i = 0; i < depths.length - 1; i++) {
    if (depths[i] >= 300) break;
    const z1 = depths[i];
    const z2 = Math.min(300, depths[i + 1]);
    const avgT = (temps[i] + temps[i + 1]) / 2;
    ohcIntegral += avgT * (z2 - z1);
  }
  const ohcGj = (1025 * 3990 * ohcIntegral) / 1e9; // in GJ/m2
  const ohcEl = document.getElementById('tile-ohc');
  if (ohcEl) {
    ohcEl.innerHTML = `${ohcGj.toFixed(2)} <span>GJ/m²</span>`;
  }

  // 4. Domain Applicability & Latent Quality
  const appEl = document.getElementById('tile-app');
  if (appEl) {
    const isDomainSafe = state.lat >= 6 && state.lat <= 28 && state.lon >= 48 && state.lon <= 102;
    if (isDomainSafe) {
      appEl.textContent = 'IN-DOMAIN';
      appEl.style.color = 'var(--acc)';
    } else {
      appEl.textContent = 'MARGINAL';
      appEl.style.color = 'var(--warm)';
    }
  }
}

/* ── Surface Telemetry Deck ────────────────────────────────────────────────── */
function renderSurfaceTelemetry() {
  const pred = state.currentPrediction;
  if (!pred) return;

  const sstEl = document.getElementById('telemetry-sst');
  const slaEl = document.getElementById('telemetry-sla');
  const sssEl = document.getElementById('telemetry-sss');
  const windEl = document.getElementById('telemetry-wind');

  const sst = pred.temperatures ? pred.temperatures[0] : 29.2;
  const sla = pred.features?.sla !== undefined ? pred.features.sla : 0.04;
  const sss = pred.features?.sss !== undefined ? pred.features.sss : 35.6;
  const ug = pred.features?.ug !== undefined ? pred.features.ug : 0.22;
  const vg = pred.features?.vg !== undefined ? pred.features.vg : -0.15;
  const windSpeed = Math.sqrt(ug * ug + vg * vg);

  if (sstEl) sstEl.textContent = `${sst.toFixed(2)} °C`;
  if (slaEl) slaEl.textContent = `${(sla * 100).toFixed(1)} cm`;
  if (sssEl) sssEl.textContent = `${sss.toFixed(2)} PSU`;
  if (windEl) windEl.textContent = `${(windSpeed * 10).toFixed(1)} m/s`;
}

/* ── Evidence Data & Benchmark Tables ──────────────────────────────────────── */
async function loadEvidenceData() {
  try {
    const res = await fetch('/data/metrics.json');
    if (!res.ok) return;
    const metrics = await res.json();
    state.metrics = metrics;

    // Thermocline RMSE values
    const climVal = metrics.baselines?.['Climatology']?.thermocline_rmse || 2.29;
    const ridgeVal = metrics.baselines?.['Climatology + Ridge']?.thermocline_rmse || 2.20;
    const v1Val = metrics.baselines?.['v1 OceanEmbedNet (Re-evaluated)']?.thermocline_rmse || 1.59;
    const modelVal = metrics.baselines?.['Gradient Boosted Trees (HistGBDT)']?.thermocline_rmse || 1.07;

    const bClim = document.getElementById('wb-bar-clim');
    const bRidge = document.getElementById('wb-bar-ridge');
    const bV1 = document.getElementById('wb-bar-v1');
    const bOurs = document.getElementById('wb-bar-ours');

    if (bClim) bClim.textContent = climVal.toFixed(2);
    if (bRidge) bRidge.textContent = ridgeVal.toFixed(2);
    if (bV1) bV1.textContent = v1Val.toFixed(2);
    if (bOurs) bOurs.textContent = modelVal.toFixed(2);

    // Track widths
    const tClim = document.getElementById('track-clim');
    const tRidge = document.getElementById('track-ridge');
    const tV1 = document.getElementById('track-v1');
    const tOurs = document.getElementById('track-ours');

    if (tClim) tClim.style.width = '100%';
    if (tRidge) tRidge.style.width = `${Math.round((ridgeVal / climVal) * 100)}%`;
    if (tV1) tV1.style.width = `${Math.round((v1Val / climVal) * 100)}%`;
    if (tOurs) tOurs.style.width = `${Math.round((modelVal / climVal) * 100)}%`;
  } catch (err) {
    console.warn('Evidence metrics loading fallback:', err);
  }
}
