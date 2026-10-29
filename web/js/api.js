// API client: timeouts, bounded retries, explicit 503 handling and provenance.
//
// Every successful call resolves to the raw payload. Failures throw ApiError with a
// `kind` the UI can render honestly:
//   unavailable  503 — the backend had no observation (local store, cache and live all missed)
//   offline      network error / timeout — API not reachable
//   not_found    404
//   invalid      400 / 422 (bad lat/lon/date)
//   server       other 5xx
//
// When offline demo mode is on, data endpoints are answered by demo.js instead and
// every payload carries data_source = "demo_synthetic".

import { state } from './state.js';
import * as demo from './demo.js';

const BASE = (new URLSearchParams(location.search).get('api') || '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(kind, message, { status = 0, detail = '' } = {}) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function detailText(body) {
  if (!body) return '';
  if (typeof body.detail === 'string') return body.detail;
  if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg).join('; ');
  return '';
}

async function request(path, { method = 'GET', body, timeout = 10000, retries = 1, signal } = {}) {
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(new DOMException('timeout', 'TimeoutError')), timeout);
    const onAbort = () => ctrl.abort(signal.reason);
    signal?.addEventListener('abort', onAbort, { once: true });
    try {
      const res = await fetch(BASE + path, {
        method,
        signal: ctrl.signal,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const json = await res.json().catch(() => null);
      if (res.ok) return json;

      const detail = detailText(json);
      if (res.status === 503) throw new ApiError('unavailable', 'Data unavailable', { status: 503, detail });
      if (res.status === 404) throw new ApiError('not_found', 'Not found', { status: 404, detail });
      if (res.status === 400 || res.status === 422) throw new ApiError('invalid', 'Request rejected', { status: res.status, detail });
      lastErr = new ApiError('server', `Server error ${res.status}`, { status: res.status, detail });
    } catch (err) {
      if (signal?.aborted) throw err;                // caller navigated away
      if (err instanceof ApiError) throw err;        // 503/404/422 are final
      lastErr = new ApiError('offline', 'API unreachable', {
        detail: err?.name === 'AbortError' || err?.name === 'TimeoutError' ? `No response within ${timeout / 1000}s` : String(err?.message || err),
      });
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    }
    if (attempt < retries) await sleep(400 * 2 ** attempt);
  }
  throw lastErr;
}

const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v != null)).toString();

export const isDemo = () => state.demo;

// ── Status endpoints (never answered by the demo: they describe the real API) ──
export const health = (opts) => request('/health', { timeout: 4000, retries: 0, ...opts });
export const ready = (opts) => request('/ready', { timeout: 4000, retries: 0, ...opts });
export const meta = (opts) => request('/meta', { timeout: 6000, ...opts });

// ── Data endpoints ─────────────────────────────────────────────────────────────
export function predict({ lat, lon, date }, opts) {
  if (state.demo) return demo.predict({ lat, lon, date });
  return request(`/predict?${qs({ lat, lon, date })}`, opts);
}

const batchCache = new Map();
export async function predictBatch(items, opts) {
  if (state.demo) return demo.predictBatch(items);
  const key = JSON.stringify(items);
  if (batchCache.has(key)) return batchCache.get(key);
  const res = await request('/predict_batch', { method: 'POST', body: { items }, timeout: 60000, retries: 0, ...opts });
  if (batchCache.size > 12) batchCache.delete(batchCache.keys().next().value);
  batchCache.set(key, res);
  return res;
}

export function grid(params, opts) {
  if (state.demo) return demo.grid(params);
  return request(`/grid?${qs(params)}`, { timeout: 60000, retries: 0, ...opts });
}

export function validationProfile({ lat, lon, date, includeTraining = false }, opts) {
  if (state.demo) return demo.validationProfile({ lat, lon, date });
  const include_training = includeTraining ? 'true' : null;
  return request(`/validation/profile?${qs({ lat, lon, date, include_training })}`, opts);
}

export function explain({ lat, lon, date }, opts) {
  if (state.demo) return demo.explain({ lat, lon, date });
  return request(`/explain?${qs({ lat, lon, date })}`, opts);
}

// ── Static results files shipped in web/data (produced by the eval pipeline) ──
const staticCache = new Map();
let indexPromise;
/** web/data/index.json lists the results files that exist; null if the index itself is missing. */
function resultsIndex() {
  indexPromise ||= fetch('data/index.json').then((r) => (r.ok ? r.json() : null)).then((d) => (d ? new Set(d.files) : null)).catch(() => null);
  return indexPromise;
}

export async function results(name) {
  const index = await resultsIndex();
  if (index && !index.has(name)) throw new ApiError('not_found', `${name}.json not produced yet`, { status: 404 });
  if (!staticCache.has(name)) {
    staticCache.set(
      name,
      fetch(`data/${name}.json`).then((r) => {
        if (!r.ok) throw new ApiError(r.status === 404 ? 'not_found' : 'server', `${name}.json missing`, { status: r.status });
        return r.json();
      }).catch((err) => {
        staticCache.delete(name);
        throw err instanceof ApiError ? err : new ApiError('offline', `Could not load ${name}.json`);
      }),
    );
  }
  return staticCache.get(name);
}

const assetCache = new Map();
export function asset(name) {
  if (!assetCache.has(name)) {
    assetCache.set(name, fetch(`assets/${name}`).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  }
  return assetCache.get(name);
}
