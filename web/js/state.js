/**
 * AquaSphere Central Application State and Event Dispatcher
 */

export const state = {
  lat: 15.0,
  lon: 88.0,
  date: '2025-05-15',
  depth: 100,
  mapLayer: 'sst',
  compareA: { lat: 15.0, lon: 88.0, date: '2025-05-15' },
  compareB: { lat: 13.0, lon: 65.0, date: '2025-05-15' },
  page: 'studio',
  meta: null,
  isOfflineDemo: false,
  demo: { active: false, step: 0 },
};

const listeners = new Set();

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function notify(changeKey = null) {
  listeners.forEach(fn => fn(state, changeKey));
}

export function setState(updates) {
  Object.assign(state, updates);
  notify();
}

export function setLocation(lat, lon) {
  state.lat = Math.round(lat * 10) / 10;
  state.lon = Math.round(lon * 10) / 10;
  notify('location');
}

export function setDate(dateStr) {
  state.date = dateStr;
  notify('date');
}

export function setDepth(depthMeters) {
  state.depth = Number(depthMeters);
  notify('depth');
}

export function setPage(pageId) {
  state.page = pageId;
  notify('page');
}
