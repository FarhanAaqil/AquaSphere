/**
 * AquaSphere Workbench Main Orchestrator
 * Connects UI interactions, SVG map, profile rendering, and FastAPI backend.
 */

import { fetchMeta, fetchPredict, fetchValidationProfile, fetchMetrics } from './api.js';
import { initMap, setSelectedPin, setArgoMarkers } from './map.js';
import { renderProfile } from './profile.js';
import { renderEvidence } from './evidence.js';

const state = {
  lat: 15.0,
  lon: 65.0,
  date: '2025-05-15',
  depth: 100,
  meta: null,
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
  const mapSvg = document.getElementById('map-svg');
  const latInput = document.getElementById('wb-lat-input');
  const lonInput = document.getElementById('wb-lon-input');
  const dateInput = document.getElementById('wb-date-input');
  const depthSlider = document.getElementById('wb-depth-slider');
  const depthVal = document.getElementById('wb-depth-val');

  // Layer checkboxes
  const layerPred = document.getElementById('layer-pred');
  const layerArgo = document.getElementById('layer-argo');
  const layerUnc = document.getElementById('layer-unc');
  const layerDomain = document.getElementById('layer-domain');

  // Initialize Map
  initMap(mapSvg, (lat, lon) => {
    state.lat = lat;
    state.lon = lon;
    if (latInput) latInput.value = lat.toFixed(1);
    if (lonInput) lonInput.value = lon.toFixed(1);
    runPrediction();
  });

  // Manual Coordinates
  if (latInput) {
    latInput.addEventListener('change', () => {
      const val = parseFloat(latInput.value);
      if (!isNaN(val) && val >= 5 && val <= 30) {
        state.lat = val;
        setSelectedPin(state.lat, state.lon);
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
        runPrediction();
      }
    });
  }

  // Date input
  if (dateInput) {
    dateInput.addEventListener('change', () => {
      state.date = dateInput.value.trim();
      runPrediction();
    });
  }

  // Depth slider
  if (depthSlider) {
    depthSlider.addEventListener('input', (e) => {
      state.depth = parseInt(e.target.value, 10);
      if (depthVal) depthVal.textContent = state.depth;
    });
  }

  // Layer checkbox listeners
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

  // Initial load
  await loadMetadata();
  await loadEvidenceData();
  await runPrediction();
});

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

async function loadEvidenceData() {
  try {
    const metrics = await fetchMetrics();
    renderEvidence(metrics);
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

    // Update source badge
    updateSourceBadge(pred.data_source);

    // Update profile chart
    renderProfile(pred, val, {
      showPred: state.layers.pred,
      showUnc: state.layers.unc,
      showArgo: state.layers.argo
    });

  } catch (err) {
    console.error('Prediction failed:', err);
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

function updateSourceBadge(source) {
  const badge = document.getElementById('wb-source-badge');
  if (!badge) return;

  // Rule 6.3 #6: Keep SAMPLE / SYNTHETIC while fixture is active, or show store
  if (source === 'local_store' || source === 'offline_synthetic' || !source) {
    badge.textContent = 'SAMPLE / SYNTHETIC';
    badge.style.color = 'var(--warm)';
    badge.style.borderColor = 'var(--warm)';
  } else if (source === 'disk_cache') {
    badge.textContent = 'CACHED';
    badge.style.color = 'var(--acc)';
    badge.style.borderColor = 'var(--acc)';
  } else if (source === 'live') {
    badge.textContent = 'LIVE';
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
    pin.style.opacity = isLoading ? '0.5' : '1.0';
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
  errBanner.textContent = `Error: ${msg}`;
  errBanner.style.display = 'block';
}

function clearError() {
  const errBanner = document.getElementById('wb-error-banner');
  if (errBanner) {
    errBanner.style.display = 'none';
  }
}
