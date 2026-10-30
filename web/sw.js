// AquaSphere service worker (roadmap Phase 6, B10): the app shell works with no server, and
// the last API answers stay readable offline, clearly marked as saved.
//
//   static files   cache first, refreshed in the background
//   API reads      network first; when the network fails, the last saved answer is returned with
//                  an X-AquaSphere-Saved-At header, and the page says it is showing saved results
//   /health, /ready  never served from cache: they must describe the live API
//
// The precache list and its version come from data/precache.json (scripts/build_web_data.py).

const SHELL = 'aquasphere-shell-';
const API = 'aquasphere-api-v1';
const API_PATHS = /^\/(meta|predict|predict_batch|grid|explain|validation|v2\/)/;
const LIVE_ONLY = /^\/(health|ready|metrics)$/;
const MAX_API_ENTRIES = 400;

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const res = await fetch('data/precache.json', { cache: 'no-store' });
    const manifest = await res.clone().json();
    const cache = await caches.open(SHELL + manifest.version);
    await cache.addAll(manifest.files);
    await cache.put('data/precache.json', res); // activate reads the version back from here
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    // The newest shell is the one whose stored manifest names it; older shells are dropped
    const shells = (await caches.keys()).filter((k) => k.startsWith(SHELL));
    let keep = null;
    for (const key of shells) {
      const m = await (await (await caches.open(key)).match('data/precache.json'))?.json().catch(() => null);
      if (m && key === SHELL + m.version) keep = key;
    }
    const fresh = await fetch('data/precache.json', { cache: 'no-store' }).then((r) => r.json()).catch(() => null);
    if (fresh && shells.includes(SHELL + fresh.version)) keep = SHELL + fresh.version;
    for (const key of shells) if (keep && key !== keep) await caches.delete(key);
    await self.clients.claim();
  })());
});

async function hashBody(text) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].slice(0, 12).map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** A GET request that stands for the response to a POST with this body. */
async function cacheKey(request) {
  if (request.method === 'GET') return request;
  const body = await request.clone().text();
  return new Request(`${request.url}${request.url.includes('?') ? '&' : '?'}__post=${await hashBody(body)}`);
}

async function stamp(response) {
  const headers = new Headers(response.headers);
  // The stored body is already decoded: drop transfer headers that described the wire format
  for (const h of ['content-encoding', 'content-length', 'etag']) headers.delete(h);
  headers.set('X-AquaSphere-Saved-At', new Date().toISOString());
  return new Response(await response.clone().blob(), { status: response.status, statusText: response.statusText, headers });
}

async function trim(cache) {
  const keys = await cache.keys();
  for (const k of keys.slice(0, Math.max(0, keys.length - MAX_API_ENTRIES))) await cache.delete(k);
}

async function apiNetworkFirst(request) {
  const key = await cacheKey(request);
  try {
    // Straight to the network: the browser's HTTP cache must not pass an old answer off as live
    const response = await fetch(new Request(request, { cache: 'no-store' }));
    if (response.ok) {
      const cache = await caches.open(API);
      await cache.put(key, await stamp(response));
      trim(cache);
    }
    return response;
  } catch (err) {
    const saved = await caches.match(key, { cacheName: API });
    if (saved) return saved;
    throw err;
  }
}

async function staticCacheFirst(request) {
  const hit = await caches.match(request, { ignoreSearch: true });
  const refresh = fetch(request).then(async (response) => {
    if (response.ok) {
      const name = (await caches.keys()).find((k) => k.startsWith(SHELL));
      if (name) (await caches.open(name)).put(request, response.clone());
    }
    return response;
  }).catch(() => null);
  return hit || (await refresh) || new Response('Offline and not cached', { status: 503 });
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== location.origin || LIVE_ONLY.test(url.pathname)) return;
  if (url.pathname.startsWith('/v2/export')) return; // downloads go straight to the network
  if (API_PATHS.test(url.pathname)) {
    if (event.request.method === 'GET' || /predict_batch$/.test(url.pathname)) {
      event.respondWith(apiNetworkFirst(event.request));
    }
    return;
  }
  if (event.request.method !== 'GET') return;
  // The hash route lives client-side: every navigation is the app shell
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('index.html', { ignoreSearch: true })));
    return;
  }
  event.respondWith(staticCacheFirst(event.request));
});
