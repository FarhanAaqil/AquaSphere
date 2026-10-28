// Tiny shared store. Tabs read from it and subscribe to changes (date, mode, perf, demo…).

const STORAGE_KEY = 'aquasphere.prefs';
const listeners = new Set();

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const smallScreen = window.matchMedia('(max-width: 760px), (pointer: coarse)');

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

function savePrefs() {
  try {
    const { perf, mode, demo } = state;
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ perf, mode, demo }));
  } catch {
    /* storage blocked: preferences just won't persist */
  }
}

const prefs = loadPrefs();

export const state = {
  meta: null,            // /meta payload once loaded
  metaSettled: false,    // true once /meta has succeeded or definitively failed
  health: null,          // /health payload or null
  ready: null,           // /ready payload or null
  api: 'unknown',        // 'ok' | 'degraded' | 'down' | 'unknown'
  date: null,            // YYYY-MM-DD, always inside meta range
  mode: prefs.mode === 'nowcast' ? 'nowcast' : 'delayed',
  perf: Boolean(prefs.perf),
  demo: Boolean(prefs.demo),
  reduced: reducedMotion.matches,
  lite: smallScreen.matches,   // phones / touch: 2D fallback
  point: { lat: 15.0, lon: 65.0 },
  lastPrediction: null,
};

export function set(patch) {
  const changed = {};
  for (const [k, v] of Object.entries(patch)) {
    if (state[k] !== v) {
      state[k] = v;
      changed[k] = v;
    }
  }
  if (!Object.keys(changed).length) return;
  if ('perf' in changed || 'mode' in changed || 'demo' in changed) savePrefs();
  listeners.forEach((fn) => fn(state, changed));
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** True when heavy 3D should run at all. */
export function allow3D() {
  return !state.perf && !state.lite;
}

reducedMotion.addEventListener('change', (e) => set({ reduced: e.matches }));
smallScreen.addEventListener('change', (e) => set({ lite: e.matches }));
