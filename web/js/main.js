import { state, set, subscribe, allow3D } from './state.js';
import * as api from './api.js';
import { startRouter, reload } from './router.js';
import { initSidebar } from './ui/sidebar.js';
import { initTopbar, populateDates } from './ui/topbar.js';
import { toast } from './ui/toasts.js';
import { DOMAIN } from './geo.js';

const body = document.body;
const STATUS_POLL_MS = 30000;

function paintFlags() {
  body.classList.toggle('perf', state.perf);
  body.classList.toggle('reduced', state.reduced);
  body.classList.toggle('lite', state.lite);
}

// ── Background scene (three.js), only when 3D is allowed ──────────────────────
let bg = null;
async function syncBackground() {
  const want = allow3D() && !state.reduced;
  if (want && !bg) {
    try {
      const mod = await import('./three/background.js');
      if (!(allow3D() && !state.reduced)) return;
      bg = mod.createBackground(document.getElementById('bg-canvas'));
      body.classList.add('has-3d');
    } catch (err) {
      console.warn('3D background disabled:', err);
      body.classList.remove('has-3d');
    }
  } else if (!want && bg) {
    bg.dispose();
    bg = null;
    body.classList.remove('has-3d');
  }
}
export const background = () => bg;

// ── API status ────────────────────────────────────────────────────────────────
async function refreshStatus() {
  try {
    const health = await api.health();
    const ready = await api.ready().catch(() => null);
    set({ health, ready, api: ready?.ready ? 'ok' : 'degraded' });
  } catch {
    set({ health: null, ready: null, api: 'down' });
  }
}

async function loadMeta() {
  try {
    const meta = await api.meta();
    set({ meta });
  } catch (err) {
    if (state.demo) {
      // Demo mode without the API: bounds come from the shipped date index, flagged as demo.
      set({ meta: { model_version: 'demo', data_version: 'demo', min_date: '2025-01-01', max_date: '2025-12-31', domain: DOMAIN, standard_depths: [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000], available_sources: ['demo_synthetic'], _demo: true } });
    } else {
      set({ meta: null });
      const picker = document.getElementById('date-picker');
      picker.innerHTML = '<option>No dates (API offline)</option>';
      toast('The AquaSphere API is not reachable, so live views will show an offline state. You can turn on Offline demo in display settings.', { kind: 'warn', timeout: 9000 });
      set({ metaSettled: true, date: null });
      return;
    }
  }
  await populateDates(state.meta);
  set({ metaSettled: true });
}

// ── Export: print the current view to PDF with a provenance header ────────────
function exportView() {
  const page = document.querySelector('#view > .page');
  if (!page) return;
  const header = document.createElement('div');
  header.className = 'print-header';
  const sources = [...new Set([...page.querySelectorAll('.badge[data-source]')].map((b) => b.textContent))];
  header.innerHTML = `<h2>AquaSphere · ${document.getElementById('view-title').textContent}</h2>
    <p class="mono"></p>`;
  header.querySelector('p').textContent =
    `Exported ${new Date().toISOString()} · date ${state.date || '—'} · mode ${state.mode} · model ${state.meta?.model_version || '—'} · sources: ${sources.join(', ') || 'none'}` +
    (state.demo ? ' · OFFLINE DEMO (SYNTHETIC)' : '') +
    ' · Decision-support prototype; not validated for operational use.';
  page.prepend(header);
  const done = () => { header.remove(); window.removeEventListener('afterprint', done); };
  window.addEventListener('afterprint', done);
  window.print();
}

function init() {
  paintFlags();
  const sidebar = initSidebar();
  initTopbar({ onExport: exportView });

  startRouter((route) => {
    sidebar.setActive(route.id);
    document.getElementById('view-title').textContent = route.label;
    document.title = route.id === 'overview' ? 'AquaSphere' : `${route.label} · AquaSphere`;
    bg?.setDepth?.(0);
  });

  subscribe((s, changed) => {
    if ('perf' in changed || 'reduced' in changed || 'lite' in changed) {
      paintFlags();
      syncBackground();
      if ('perf' in changed) reload(); // tabs re-mount with or without their 3D
    }
    if ('demo' in changed) {
      if (!s.meta || s.meta._demo) loadMeta().then(reload);
      else reload();
      toast(s.demo ? 'Offline demo on: views now show synthetic data, labelled as such.' : 'Offline demo off: views use the API again.');
    }
  });

  syncBackground();
  refreshStatus();
  loadMeta();
  setInterval(() => { if (!document.hidden) refreshStatus(); }, STATUS_POLL_MS);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
