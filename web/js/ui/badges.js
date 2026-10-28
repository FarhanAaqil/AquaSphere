// Provenance badges. Every chart/card that shows data carries one.

const SOURCES = {
  local_store: { label: 'Local store', cls: 'local', title: 'Surface observations read from the local Zarr store.' },
  disk_cache: { label: 'Disk cache', cls: 'cache', title: 'Surface observations from the on-disk cache of an earlier live fetch.' },
  live: { label: 'Live', cls: 'live', title: 'Surface observations fetched live from NOAA ERDDAP.' },
  offline_synthetic: {
    label: 'Offline demo (synthetic)',
    cls: 'demo',
    title: 'The API answered from its offline synthetic fixture store — inputs are not real observations.',
  },
  demo_synthetic: {
    label: 'Offline demo (synthetic)',
    cls: 'demo',
    title: 'Generated in your browser by offline demo mode. Not model output.',
  },
  held_out_validation: { label: 'Held-out store', cls: 'heldout', title: 'Profile from the validation lookup store.' },
  user_override: { label: 'User override', cls: 'override', title: 'Surface features supplied manually in the request.' },
  results: { label: 'Results file', cls: 'results', title: 'Read from an evaluation results file produced by the pipeline (web/data).' },
  unavailable: { label: 'Data unavailable', cls: 'unavailable', title: 'The API returned 503: no observation from store, cache or live.' },
  pending: { label: 'Pending', cls: 'pending', title: 'No results exist for this yet.' },
  offline: { label: 'API offline', cls: 'unavailable', title: 'The serving API did not respond.' },
  unreported: { label: 'Source not reported', cls: 'muted', title: 'This endpoint returns no provenance field, so the input source cannot be shown.' },
};

export function sourceInfo(key) {
  return SOURCES[key] || { label: key ? String(key) : 'Unknown source', cls: 'muted', title: 'Unrecognised provenance value from the API.' };
}

export function badge(key, extraTitle = '') {
  const s = sourceInfo(key);
  const el = document.createElement('span');
  el.className = `badge badge--${s.cls}`;
  el.dataset.source = key || 'unknown';
  el.textContent = s.label;
  el.title = extraTitle ? `${s.title} ${extraTitle}` : s.title;
  return el;
}

/** Simple coloured tag that is not a provenance claim (e.g. "In training", "Outside domain"). */
export function tag(text, cls = 'muted', title = '') {
  const el = document.createElement('span');
  el.className = `badge badge--${cls}`;
  el.textContent = text;
  if (title) el.title = title;
  return el;
}

/** Collapse a list of per-point sources into one badge set (e.g. grid/batch calls). */
export function sourceSummary(sources) {
  const counts = new Map();
  for (const s of sources) counts.set(s, (counts.get(s) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([key, n]) =>
    badge(key, counts.size > 1 ? `(${n} of ${sources.length} points)` : ''));
}
