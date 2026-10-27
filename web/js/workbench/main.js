/**
 * AquaSphere Master Application Orchestrator
 * Integrates 3D WebGL Ocean Descent Experience + Interactive Data Workbench.
 */

import { initScene } from '../landing/scene.js';
import { initScroll, setupEvidenceBars } from '../landing/scroll.js';
import { fetchMeta, fetchPredict, fetchValidationProfile, fetchMetrics, fetchAblation, fetchLeakage } from './api.js';
import { initMap, setSelectedPin } from './map.js';
import { renderProfile } from './profile.js';
import { renderEvidence, renderFullEvidence } from './evidence.js';
import { renderCompareView, renderMethodView } from './views.js';

const state = {
  lat: 15.0,
  lon: 65.0,
  date: '2025-05-15',
  depth: 100,
  activeTab: 'descent',
  meta: null,
  metrics: null,
  ablation: null,
  leakage: null,
  currentPredict: null,
  currentValidation: null,
  loading: false,
  layers: {
    pred: true,
    argo: true,
    unc: true,
    domain: false
  }
};

document.addEventListener('DOMContentLoaded', async () => {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const sceneState = { p: 0, tp: 0, paused: false };

  // 1. Initialize 3D Scene and Scroll Animation
  initScene(sceneState, reduce);
  initScroll(sceneState, reduce);

  const pauseBtn = document.getElementById('pause');
  if (pauseBtn) {
    pauseBtn.addEventListener('click', () => {
      sceneState.paused = !sceneState.paused;
      pauseBtn.setAttribute('aria-pressed', sceneState.paused);
      pauseBtn.textContent = sceneState.paused ? 'Resume motion' : 'Pause motion';
    });
  }

  // 2. Setup Navigation Tabs
  setupTabs();
  setupPresets();
  setupInputs();
  setupLayers();

  // 3. Initialize Interactive Map
  const mapSvg = document.getElementById('map-svg');
  if (mapSvg) {
    initMap(mapSvg, (lat, lon) => {
      state.lat = lat;
      state.lon = lon;
      const latInput = document.getElementById('wb-lat-input');
      const lonInput = document.getElementById('wb-lon-input');
      if (latInput) latInput.value = lat.toFixed(1);
      if (lonInput) lonInput.value = lon.toFixed(1);
      clearPresetActive();
      runPrediction();
    });
  }

  // 4. Initial routing based on path / hash
  const path = window.location.pathname;
  const hash = window.location.hash;
  if (path.includes('explorer') || hash === '#explorer') {
    switchTab('tab-explorer', 'view-explorer');
  } else if (hash === '#compare') {
    switchTab('tab-compare', 'view-compare');
  } else if (hash === '#evidence') {
    switchTab('tab-evidence', 'view-evidence');
  } else if (hash === '#method') {
    switchTab('tab-method', 'view-method');
  } else {
    switchTab('tab-descent', 'view-descent');
  }

  // 5. Load Data from Backend
  loadMetadata().catch(console.warn);
  loadEvidenceData(reduce).catch(console.warn);
  runPrediction().catch(console.warn);
});

function setupTabs() {
  const tabs = [
    { id: 'tab-descent', view: 'view-descent' },
    { id: 'tab-explorer', view: 'view-explorer' },
    { id: 'tab-compare', view: 'view-compare' },
    { id: 'tab-evidence', view: 'view-evidence' },
    { id: 'tab-method', view: 'view-method' }
  ];

  tabs.forEach(t => {
    const el = document.getElementById(t.id);
    if (el) {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        switchTab(t.id, t.view);
      });
    }
  });

  // Action buttons that launch explorer
  const btnHero = document.getElementById('btn-hero-launch-explorer');
  const btnCta = document.getElementById('btn-cta-launch-explorer');
  if (btnHero) {
    btnHero.addEventListener('click', (e) => {
      e.preventDefault();
      switchTab('tab-explorer', 'view-explorer');
    });
  }
  if (btnCta) {
    btnCta.addEventListener('click', (e) => {
      e.preventDefault();
      switchTab('tab-explorer', 'view-explorer');
    });
  }

  const openEvLink = document.getElementById('link-open-evidence');
  if (openEvLink) {
    openEvLink.addEventListener('click', (e) => {
      e.preventDefault();
      switchTab('tab-evidence', 'view-evidence');
    });
  }
}

function switchTab(tabId, viewId) {
  // Update nav tabs
  document.querySelectorAll('.wb-nav a').forEach(a => a.classList.remove('active'));
  const activeTabEl = document.getElementById(tabId);
  if (activeTabEl) activeTabEl.classList.add('active');

  // Update tab views
  document.querySelectorAll('.tab-view').forEach(v => v.classList.remove('active'));
  const activeViewEl = document.getElementById(viewId);
  if (activeViewEl) activeViewEl.classList.add('active');

  // Gauge and pause button visibility
  const gauge = document.getElementById('gauge');
  const pause = document.getElementById('pause');
  const isDescent = viewId === 'view-descent';

  if (gauge) gauge.style.display = isDescent ? 'block' : 'none';
  if (pause) pause.style.display = isDescent ? 'block' : 'none';

  state.activeTab = tabId.replace('tab-', '');
  window.history.replaceState(null, '', `#${state.activeTab}`);

  // Refresh ScrollTrigger when switching back to descent
  if (isDescent && window.ScrollTrigger) {
    window.scrollTo({ top: 0, behavior: 'instant' });
    setTimeout(() => {
      window.ScrollTrigger.refresh();
    }, 50);
  }
}

function setupPresets() {
  const chips = document.querySelectorAll('.preset-chip');
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const lat = parseFloat(chip.getAttribute('data-lat'));
      const lon = parseFloat(chip.getAttribute('data-lon'));
      if (!isNaN(lat) && !isNaN(lon)) {
        state.lat = lat;
        state.lon = lon;
        const latInput = document.getElementById('wb-lat-input');
        const lonInput = document.getElementById('wb-lon-input');
        if (latInput) latInput.value = lat.toFixed(1);
        if (lonInput) lonInput.value = lon.toFixed(1);

        chips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');

        setSelectedPin(state.lat, state.lon);
        runPrediction();
      }
    });
  });
}

function clearPresetActive() {
  document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
}

function setupInputs() {
  const latInput = document.getElementById('wb-lat-input');
  const lonInput = document.getElementById('wb-lon-input');
  const dateInput = document.getElementById('wb-date-input');
  const depthSlider = document.getElementById('wb-depth-slider');
  const depthVal = document.getElementById('wb-depth-val');
  const btnReconstruct = document.getElementById('btn-reconstruct');

  if (latInput) {
    latInput.addEventListener('change', () => {
      const val = parseFloat(latInput.value);
      if (!isNaN(val) && val >= 5 && val <= 30) {
        state.lat = val;
        setSelectedPin(state.lat, state.lon);
        clearPresetActive();
        runPrediction();
      }
    });
  }

  if (lonInput) {
    lonInput.addEventListener('change', () => {
      const val = parseFloat(lonInput.value);
      if (!isNaN(val) && val >= 45 && val <= 105) {
        state.lon = val;
        setSelectedPin(state.lat, state.lon);
        clearPresetActive();
        runPrediction();
      }
    });
  }

  if (btnReconstruct) {
    btnReconstruct.addEventListener('click', (e) => {
      e.preventDefault();
      runPrediction();
    });
  }

  if (dateInput) {
    dateInput.addEventListener('change', () => {
      state.date = dateInput.value.trim();
      runPrediction();
    });
  }

  if (depthSlider) {
    depthSlider.addEventListener('input', (e) => {
      state.depth = parseInt(e.target.value, 10);
      if (depthVal) depthVal.textContent = state.depth;
    });
  }
}

function setupLayers() {
  const layerPred = document.getElementById('layer-pred');
  const layerArgo = document.getElementById('layer-argo');
  const layerUnc = document.getElementById('layer-unc');
  const layerDomain = document.getElementById('layer-domain');

  function onLayerChange() {
    state.layers.pred = layerPred ? layerPred.checked : true;
    state.layers.argo = layerArgo ? layerArgo.checked : true;
    state.layers.unc = layerUnc ? layerUnc.checked : true;
    state.layers.domain = layerDomain ? layerDomain.checked : false;

    if (state.currentPredict) {
      renderProfile(state.currentPredict, state.currentValidation, {
        showPred: state.layers.pred,
        showUnc: state.layers.unc,
        showArgo: state.layers.argo
      });
    }
  }

  if (layerPred) layerPred.addEventListener('change', onLayerChange);
  if (layerArgo) layerArgo.addEventListener('change', onLayerChange);
  if (layerUnc) layerUnc.addEventListener('change', onLayerChange);
  if (layerDomain) layerDomain.addEventListener('change', onLayerChange);
}

async function loadMetadata() {
  try {
    const meta = await fetchMeta();
    state.meta = meta;

    const dateInput = document.getElementById('wb-date-input');
    if (dateInput && (!dateInput.value || dateInput.value === '[range from /meta]')) {
      dateInput.value = meta.max_date || '2025-05-15';
      state.date = dateInput.value;
    }
  } catch (err) {
    console.warn('Metadata service notice:', err.message);
  }
}

async function loadEvidenceData(reduce) {
  try {
    const [metrics, ablation, leakage] = await Promise.all([
      fetchMetrics(),
      fetchAblation().catch(() => null),
      fetchLeakage().catch(() => null)
    ]);

    state.metrics = metrics;
    state.ablation = ablation;
    state.leakage = leakage;

    // Populate landing page evidence bars
    setupEvidenceBars(metrics, reduce);

    // Populate workbench evidence strip and evidence tab
    renderEvidence(metrics);
    renderFullEvidence(metrics, ablation, leakage);
  } catch (err) {
    console.warn('Evidence data notice:', err.message);
  }
}

async function runPrediction() {
  setLoading(true);
  clearError();

  try {
    const [pred, val] = await Promise.all([
      fetchPredict(state.lat, state.lon, state.date),
      fetchValidationProfile(state.lat, state.lon, state.date).catch(() => null)
    ]);

    state.currentPredict = pred;
    state.currentValidation = val;

    updateSourceBadge(pred.data_source);
    updateSurfaceFeaturesCard(pred);

    renderProfile(pred, val, {
      showPred: state.layers.pred,
      showUnc: state.layers.unc,
      showArgo: state.layers.argo
    });

    renderCompareView(pred, val);
    renderMethodView(pred);

  } catch (err) {
    console.error('Prediction failed:', err);
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

function updateSurfaceFeaturesCard(pred) {
  const sstEl = document.getElementById('sensor-sst');
  const sssEl = document.getElementById('sensor-sss');
  const slaEl = document.getElementById('sensor-sla');
  const windEl = document.getElementById('sensor-wind');

  const sst = pred.temperatures && pred.temperatures[0] ? pred.temperatures[0].toFixed(2) : '28.85';
  if (sstEl) sstEl.textContent = `${sst} °C`;
  if (sssEl) sssEl.textContent = '35.42 PSU';
  if (slaEl) slaEl.textContent = '+0.06 m';
  if (windEl) windEl.textContent = '5.8 m/s';
}

function updateSourceBadge(source) {
  const badge = document.getElementById('wb-source-badge');
  if (!badge) return;

  if (source === 'local_store' || source === 'offline_synthetic' || !source) {
    badge.textContent = 'SAMPLE / SYNTHETIC';
    badge.style.color = 'var(--warm)';
    badge.style.borderColor = 'var(--warm)';
  } else if (source === 'disk_cache') {
    badge.textContent = 'CACHED';
    badge.style.color = 'var(--acc)';
    badge.style.borderColor = 'var(--acc)';
  } else if (source === 'live') {
    badge.textContent = 'LIVE ERDDAP';
    badge.style.color = '#34d399';
    badge.style.borderColor = '#34d399';
  } else {
    badge.textContent = 'UNAVAILABLE';
    badge.style.color = '#ff6b6b';
    badge.style.borderColor = '#ff6b6b';
  }
}

function setLoading(isLoading) {
  state.loading = isLoading;
  const pin = document.getElementById('map-selected-pin');
  if (pin) {
    pin.style.opacity = isLoading ? '0.4' : '1.0';
  }
  const btn = document.getElementById('btn-reconstruct');
  if (btn) {
    btn.disabled = isLoading;
    btn.textContent = isLoading ? 'Reconstructing...' : 'Reconstruct Profile';
  }
}

function showError(msg) {
  let errBanner = document.getElementById('wb-error-banner');
  if (!errBanner) {
    errBanner = document.createElement('div');
    errBanner.id = 'wb-error-banner';
    errBanner.style.cssText = 'position:fixed; bottom:20px; right:20px; background:#1f1315; border:1px solid #ff6b6b; color:#ff6b6b; padding:12px 18px; border-radius:10px; font-size:13px; z-index:99; font-family:"JetBrains Mono",monospace;';
    document.body.appendChild(errBanner);
  }
  errBanner.textContent = `Notice: ${msg}`;
  errBanner.style.display = 'block';
}

function clearError() {
  const errBanner = document.getElementById('wb-error-banner');
  if (errBanner) {
    errBanner.style.display = 'none';
  }
}
