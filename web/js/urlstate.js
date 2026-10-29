// Shareable links: the view's point, date, mode and depth live in the hash query, e.g.
//   #/predict?lat=15.00&lon=88.00&date=2025-06-15&mode=nowcast
// Reading happens once at start-up; afterwards state changes are mirrored into the URL with
// history.replaceState (no hashchange, no new history entries).

import { state, set, subscribe } from './state.js';
import { inDomain } from './geo.js';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function parts() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [route, query = ''] = raw.split('?');
  return { route: route || 'overview', params: new URLSearchParams(query) };
}

/** True if the date can be shown: before /meta loads, the picker validates it later. */
function dateOffered(date) {
  if (!state.metaSettled) return true;
  const picker = document.getElementById('date-picker');
  if (picker?.tagName === 'SELECT') return [...picker.options].some((o) => o.value === date);
  return Boolean(state.meta) && date >= state.meta.min_date && date <= state.meta.max_date;
}

/** Apply URL parameters to state; anything invalid or unavailable is ignored. */
export function readUrlState() {
  const { params } = parts();
  const patch = {};
  const lat = Number(params.get('lat'));
  const lon = Number(params.get('lon'));
  if (params.has('lat') && params.has('lon') && inDomain(lat, lon)) patch.point = { lat, lon };
  const date = params.get('date');
  if (date && DATE_RE.test(date) && dateOffered(date)) patch.date = date;
  if (params.get('mode') === 'nowcast' || params.get('mode') === 'delayed') patch.mode = params.get('mode');
  const depth = Number(params.get('depth'));
  if (params.has('depth') && Number.isFinite(depth) && depth >= 0 && depth <= 1000) patch.depth = depth;
  set(patch);
}

export function currentLink() {
  const { route } = parts();
  const q = new URLSearchParams();
  if (state.point) {
    q.set('lat', state.point.lat.toFixed(2));
    q.set('lon', state.point.lon.toFixed(2));
  }
  if (state.date) q.set('date', state.date);
  if (state.mode === 'nowcast') q.set('mode', 'nowcast');
  if (state.depth != null) q.set('depth', String(state.depth));
  return `#/${route}?${q.toString()}`;
}

export function writeUrlState() {
  const next = currentLink();
  if (location.hash !== next) history.replaceState(null, '', next);
}

export function initUrlState() {
  readUrlState();
  subscribe((s, changed) => {
    if (['point', 'date', 'mode', 'depth'].some((k) => k in changed)) writeUrlState();
  });
  // A link pasted into the same tab only fires hashchange; honour its parameters too.
  window.addEventListener('hashchange', () => {
    if (location.hash.includes('?')) readUrlState();
    writeUrlState();
  });
}
