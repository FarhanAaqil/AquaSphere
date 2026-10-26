/**
 * AquaSphere Main Application Entrypoint & Orchestrator
 */

import { fetchMeta, formatSourceBadge, regionName } from './api.js';
import { state, subscribe, setPage, setLocation } from './state.js';
import { renderOverview } from './views/overview.js';
import { renderExplore } from './views/explore.js';
import { renderLocation } from './views/location.js';
import { renderDepth } from './views/depth.js';
import { renderTime } from './views/time.js';
import { renderCompare } from './views/compare.js';
import { renderEmbedding } from './views/embedding.js';
import { renderValidation } from './views/validation.js';
import { renderReports } from './views/reports.js';

const NAV = [
  { id: 'overview', label: 'Overview', icon: 'grid' },
  { id: 'explore', label: 'Explore', icon: 'map' },
  { id: 'location', label: 'Location', icon: 'pin' },
  { id: 'depth', label: 'Depth', icon: 'layers' },
  { id: 'time', label: 'Time', icon: 'clock' },
  { id: 'compare', label: 'Compare', icon: 'split' },
  { id: 'embedding', label: 'Embed', icon: 'orbit' },
  { id: 'validation', label: 'Validate', icon: 'check' },
  { id: 'reports', label: 'Reports', icon: 'doc' },
];

const ICONS = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  map: '<path d="M9 3 3 5v16l6-2 6 2 6-2V3l-6 2-6-2Z"/><path d="M9 3v16M15 5v16"/>',
  pin: '<path d="M12 22s7-6.5 7-12a7 7 0 1 0-14 0c0 5.5 7 12 7 12Z"/><circle cx="12" cy="10" r="2.4"/>',
  layers: '<path d="M12 3 2 9l10 6 10-6-10-6Z"/><path d="M2 15l10 6 10-6M2 12l10 6 10-6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
  split: '<path d="M12 3v18M4 8h5M15 8h5M4 16h5M15 16h5"/>',
  orbit: '<circle cx="12" cy="12" r="2.4"/><ellipse cx="12" cy="12" rx="9" ry="4"/><ellipse cx="12" cy="12" rx="4" ry="9" transform="rotate(45 12 12)"/>',
  check: '<path d="M4 12l5 5L20 6"/>',
  doc: '<path d="M6 2h9l5 5v15H6Z"/><path d="M15 2v5h5"/><path d="M9 13h6M9 17h6"/>',
};

// Global Chart.js theme defaults
if (window.Chart) {
  window.Chart.defaults.color = '#8fa5ad';
  window.Chart.defaults.font.family = "'IBM Plex Sans', sans-serif";
  window.Chart.defaults.font.size = 11;
  window.Chart.defaults.borderColor = '#1d3d4b';
}

function buildRail() {
  const rail = document.getElementById('rail');
  if (!rail) return;

  const brand = document.getElementById('brandBtn');
  if (brand) brand.onclick = () => setPage('overview');

  NAV.forEach(n => {
    const btn = document.createElement('button');
    btn.className = `navbtn ${state.page === n.id ? 'active' : ''}`;
    btn.dataset.page = n.id;
    btn.title = n.label;
    btn.innerHTML = `<svg viewBox="0 0 24 24">${ICONS[n.icon]}</svg><span>${n.label}</span>`;
    btn.onclick = () => setPage(n.id);
    rail.appendChild(btn);
  });
}

function renderContextBar() {
  const bar = document.getElementById('ctxbar');
  if (!bar) return;

  const region = regionName(state.lat, state.lon);
  const source = state.isOfflineDemo ? 'offline_synthetic' : 'local_store';
  const badge = formatSourceBadge(source);

  bar.innerHTML = `
    <div class="item"><span class="lbl">Region</span><b>${region}</b></div>
    <div class="item"><span class="lbl">Location</span><b>${state.lat.toFixed(1)}°N, ${state.lon.toFixed(1)}°E</b></div>
    <div class="item"><span class="lbl">Date</span><b>${state.date}</b></div>
    <div class="item"><span class="lbl">Depth</span><b>${state.depth} m</b></div>
    <div style="margin-left: auto; display: flex; align-items: center; gap: 12px;">
      ${badge}
      <div class="relbadge">
        <span class="dot high"></span>
        <span style="font-size: 11.5px;">Confidence: <b style="font-family:var(--mono);">Calibrated</b></span>
      </div>
    </div>
  `;
}

async function renderCurrentView() {
  // Update nav active classes
  document.querySelectorAll('.navbtn').forEach(b => {
    b.classList.toggle('active', b.dataset.page === state.page);
  });

  renderContextBar();

  const content = document.getElementById('content');
  if (!content) return;

  let viewEl = null;
  switch (state.page) {
    case 'overview':
      viewEl = await renderOverview();
      break;
    case 'explore':
      viewEl = await renderExplore();
      break;
    case 'location':
      viewEl = await renderLocation();
      break;
    case 'depth':
      viewEl = await renderDepth();
      break;
    case 'time':
      viewEl = await renderTime();
      break;
    case 'compare':
      viewEl = await renderCompare();
      break;
    case 'embedding':
      viewEl = await renderEmbedding();
      break;
    case 'validation':
      viewEl = await renderValidation();
      break;
    case 'reports':
      viewEl = await renderReports();
      break;
    default:
      viewEl = await renderOverview();
  }

  content.innerHTML = '';
  const panel = document.createElement('div');
  panel.className = 'panel active';
  panel.appendChild(viewEl);
  content.appendChild(panel);

  if (state.demo.active) {
    renderGuidedDemo();
  }
}

// Guided Demonstration Steps
const DEMO_STEPS = [
  { page: 'overview', text: 'Step 1: System Overview — Multi-sensor surface ingestion and decision summary.' },
  { page: 'explore', text: 'Step 2: Interactive Exploration — Basin-wide satellite fields with dynamic date bounding.', set: () => setLocation(14.5, 89.5) },
  { page: 'location', text: 'Step 3: Location Profile — 0–1000m reconstructed profile with conformal uncertainty bands.' },
  { page: 'depth', text: 'Step 4: Depth View — Vertical slicing across 15 standard pressure levels.' },
  { page: 'compare', text: 'Step 5: Regime Comparison — Arabian Sea high-salinity vs. Bay of Bengal river plume.' },
  { page: 'embedding', text: 'Step 6: Ocean Embedding — 16-D latent manifold projecting regional regimes.' },
  { page: 'validation', text: 'Step 7: Held-Out Benchmark — Direct verification against unseen Argo floats.' },
  { page: 'reports', text: 'Step 8: Intelligence Export — Verifiable report with data provenance and limitations.' },
];

function renderGuidedDemo() {
  const badge = document.getElementById('demoBadge');
  if (!badge) return;
  const s = DEMO_STEPS[state.demo.step];
  if (!s) return;

  badge.style.display = 'block';
  badge.innerHTML = `
    <div class="step-n">Guided Tour · Step ${state.demo.step + 1} of ${DEMO_STEPS.length}</div>
    <div style="font-size: 13px; line-height: 1.5; margin-top: 6px;">${s.text}</div>
    <div class="row">
      ${state.demo.step < DEMO_STEPS.length - 1
        ? '<button class="btn small" id="nextDemoBtn">Next Step →</button>'
        : '<button class="btn small" id="endDemoBtn">Finish Tour</button>'
      }
      <button class="btn ghost small" id="exitDemoBtn">Exit</button>
    </div>
  `;

  badge.querySelector('#nextDemoBtn')?.addEventListener('click', () => {
    state.demo.step++;
    const nextStep = DEMO_STEPS[state.demo.step];
    if (nextStep && nextStep.set) nextStep.set();
    if (nextStep) setPage(nextStep.page);
  });

  badge.querySelector('#endDemoBtn')?.addEventListener('click', () => {
    state.demo.active = false;
    badge.style.display = 'none';
  });

  badge.querySelector('#exitDemoBtn')?.addEventListener('click', () => {
    state.demo.active = false;
    badge.style.display = 'none';
  });
}

// App Initialization
async function init() {
  buildRail();

  // Load server metadata
  const meta = await fetchMeta();
  state.meta = meta;
  if (meta.is_offline) {
    state.isOfflineDemo = true;
    const banner = document.getElementById('offlineBanner');
    if (banner) banner.style.display = 'flex';
  }

  // Subscribe to central state changes
  subscribe(() => {
    renderCurrentView();
  });

  // Initial render
  await renderCurrentView();

  window.addEventListener('resize', () => {
    if (state.page === 'explore' || state.page === 'depth') {
      renderCurrentView();
    }
  });
}

// Boot on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
