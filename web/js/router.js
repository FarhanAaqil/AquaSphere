// Hash router. Each tab module default-exports { mount(root, ctx) }.
// ctx.signal aborts in-flight requests when the user leaves; ctx.cleanup(fn) registers
// teardown (Plotly.purge, three.js dispose, listeners) that runs on every tab switch.

export const ROUTES = [
  { id: 'overview', label: 'Overview', icon: 'i-overview', load: () => import('./tabs/overview.js') },
  { id: 'predict', label: 'Predict', icon: 'i-predict', load: () => import('./tabs/predict.js') },
  { id: 'explorer', label: 'Profile Explorer', icon: 'i-explorer', load: () => import('./tabs/explorer.js') },
  { id: 'cube', label: 'Ocean Cube', icon: 'i-cube', load: () => import('./tabs/cube.js') },
  { id: 'products', label: 'Ocean Products', icon: 'i-products', load: () => import('./tabs/products.js') },
  { id: 'sections', label: 'Sections', icon: 'i-sections', load: () => import('./tabs/sections.js') },
  { id: 'uncertainty', label: 'Uncertainty', icon: 'i-uncertainty', load: () => import('./tabs/uncertainty.js') },
  { id: 'ablation', label: 'Sensors & Modes', icon: 'i-ablation', load: () => import('./tabs/ablation.js') },
  { id: 'experiments', label: 'Experiments', icon: 'i-experiments', load: () => import('./tabs/experiments.js') },
  { id: 'explain', label: 'Explain', icon: 'i-explain', load: () => import('./tabs/explain.js') },
  { id: 'cards', label: 'Data & Model Cards', icon: 'i-cards', load: () => import('./tabs/cards.js') },
];

let current = null; // { id, ctrl, cleanups }
let onChange = () => {};

function teardown() {
  if (!current) return;
  current.ctrl.abort();
  for (const fn of current.cleanups.reverse()) {
    try { fn(); } catch (e) { console.warn('cleanup failed', e); }
  }
  current = null;
}

async function navigate() {
  const id = location.hash.replace(/^#\/?/, '').split('?')[0] || 'overview';
  const route = ROUTES.find((r) => r.id === id) || ROUTES[0];
  if (current?.id === route.id) return;

  teardown();
  const view = document.getElementById('view');
  const ctrl = new AbortController();
  const cleanups = [];
  current = { id: route.id, ctrl, cleanups };
  const ctx = { signal: ctrl.signal, cleanup: (fn) => cleanups.push(fn), route };

  onChange(route);
  view.replaceChildren();
  window.scrollTo(0, 0);

  try {
    const mod = await route.load();
    if (ctrl.signal.aborted) return;
    const page = document.createElement('div');
    page.className = 'page';
    page.dataset.tab = route.id;
    view.append(page);
    await mod.default.mount(page, ctx);
  } catch (err) {
    if (ctrl.signal.aborted) return;
    console.error(err);
    view.innerHTML = '<div class="page"><div class="state state--error" role="alert"><div class="state__title">This view failed to load</div><div class="state__detail"></div></div></div>';
    view.querySelector('.state__detail').textContent = String(err?.message || err);
  }
}

export function startRouter(handler) {
  onChange = handler;
  window.addEventListener('hashchange', navigate);
  navigate();
}

/** Re-mount the current tab (e.g. after demo mode is toggled). */
export function reload() {
  const id = current?.id;
  teardown();
  if (id) navigate();
}
