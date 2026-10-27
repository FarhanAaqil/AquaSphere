/**
 * AquaSphere Workbench API Client
 * Wraps all serving endpoints strictly respecting schemas.py.
 */

export async function fetchMeta() {
  const res = await fetch('/meta');
  if (!res.ok) {
    throw new Error(`Failed to load /meta: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function fetchPredict(lat, lon, date, features = null) {
  const payload = {
    lat: parseFloat(lat),
    lon: parseFloat(lon),
    date: date,
    features: features
  };

  const res = await fetch('/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (res.status === 503) {
    throw new Error('Data source unavailable (503)');
  }
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Prediction error (${res.status}): ${errText}`);
  }
  return await res.json();
}

export async function fetchGrid(date, step = 2.5) {
  const url = `/grid?date=${encodeURIComponent(date)}&step=${step}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load grid (${res.status})`);
  }
  return await res.json();
}

export async function fetchValidationProfile(lat, lon, date = null) {
  let url = `/validation/profile?lat=${lat}&lon=${lon}`;
  if (date) url += `&date=${encodeURIComponent(date)}`;
  const res = await fetch(url);
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw new Error(`Validation profile error (${res.status})`);
  }
  return await res.json();
}

export async function fetchMetrics() {
  try {
    const res = await fetch('/data/metrics.json');
    if (res.ok) return await res.json();
  } catch (e) {
    // fallback to endpoint
  }
  const fallback = await fetch('/validation');
  if (!fallback.ok) {
    throw new Error('Failed to load metrics data');
  }
  return await fallback.json();
}
