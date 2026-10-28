// Offline demo generator. ONLY used when the user explicitly turns on "Offline demo".
// Everything here is synthetic: a smooth idealised profile shape, not model output.
// Payloads mirror the API schemas so views render identically, and every one is
// stamped data_source = "demo_synthetic" so badges and watermarks say so.

const DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000];
const SOURCE = 'demo_synthetic';

function hash(...xs) {
  let h = 2166136261;
  for (const x of xs) {
    h ^= Math.round(x * 1000);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 10000) / 10000;
}

function doy(date) {
  const d = new Date(`${date}T00:00:00Z`);
  return (d - Date.UTC(d.getUTCFullYear(), 0, 0)) / 864e5;
}

function profile(lat, lon, date) {
  const season = Math.sin(((doy(date) - 80) / 365) * 2 * Math.PI);
  const bob = lon >= 78 ? 1 : 0;
  const sst = 28.6 - 0.12 * (lat - 15) + 0.8 * season * (lat / 30) + 0.3 * bob + (hash(lat, lon) - 0.5) * 0.4;
  const mld = 25 + 30 * (1 - season) * 0.5 + 10 * hash(lon, lat);
  const width = 55 + 20 * hash(lat * 2, lon);
  const deep = (z) => 5.5 + 9 * Math.exp(-z / 380);
  const temps = DEPTHS.map((z) => {
    const mix = 0.5 * (1 - Math.tanh((z - mld - width) / width));
    return +(deep(z) + (sst - deep(z)) * mix).toFixed(3);
  });
  const sigma = DEPTHS.map((z) => +(0.25 + 0.9 * Math.exp(-(((z - mld - width) / 60) ** 2)) + 0.1 * (z / 1000)).toFixed(3));
  return { sst, mld, temps, sigma };
}

function d20(temps) {
  for (let i = 1; i < temps.length; i++) {
    if (temps[i - 1] >= 20 && temps[i] < 20) {
      const f = (temps[i - 1] - 20) / (temps[i - 1] - temps[i]);
      return DEPTHS[i - 1] + f * (DEPTHS[i] - DEPTHS[i - 1]);
    }
  }
  return null;
}

const delay = (v) => new Promise((r) => setTimeout(() => r(v), 120));

function predictSync({ lat, lon, date }) {
  const p = profile(lat, lon, date);
  const clim = p.temps.map((t, i) => +(t - 0.4 * Math.exp(-(((DEPTHS[i] - 90) / 70) ** 2))).toFixed(3));
  return {
    lat, lon, date,
    depths: DEPTHS,
    temperatures: p.temps,
    uncertainties: p.sigma,
    interval_lower: p.temps.map((t, i) => +(t - 1.645 * p.sigma[i]).toFixed(3)),
    interval_upper: p.temps.map((t, i) => +(t + 1.645 * p.sigma[i]).toFixed(3)),
    embedding: Array.from({ length: 16 }, (_, i) => +(hash(lat, lon, i) - 0.5).toFixed(3)),
    mld: +p.mld.toFixed(1),
    d20: d20(p.temps),
    climatology: clim,
    ohc300: +(p.temps.slice(0, 12).reduce((a, b) => a + b, 0) / 12).toFixed(2),
    data_source: SOURCE,
    model_version: 'demo',
    data_version: 'demo',
    in_training_set: false,
  };
}

export const predict = (q) => delay(predictSync(q));

export const predictBatch = (items) => delay({ count: items.length, predictions: items.map(predictSync) });

export function grid({ date, step = 2.5 }) {
  const points = [];
  for (let lat = 5; lat <= 30 + 1e-6; lat += step) {
    for (let lon = 45; lon <= 105 + 1e-6; lon += step) {
      const p = predictSync({ lat, lon, date });
      points.push({ lat, lon, sst: p.temperatures[0], mld: p.mld, d20: p.d20, pca1: p.embedding[0], pca2: p.embedding[1] });
    }
  }
  return delay({ date, count: points.length, points });
}

export function validationProfile({ lat, lon, date }) {
  const p = predictSync({ lat, lon, date: date || '2024-06-15' });
  const truth = p.temperatures.map((t, i) => +(t + (hash(lat, lon, i, 7) - 0.5) * 2 * p.uncertainties[i]).toFixed(3));
  const rmse = Math.sqrt(truth.reduce((a, t, i) => a + (t - p.temperatures[i]) ** 2, 0) / truth.length);
  return delay({
    profile_id: 'demo', float_id: 'demo', cycle: 0, date: p.date, lat, lon, distance_km: 0,
    depths: DEPTHS, true_temperatures: truth, pred_temperatures: p.temperatures,
    uncertainties: p.uncertainties, rmse, data_source: SOURCE,
  });
}

export function explain({ lat, lon, date }) {
  const names = ['lat', 'lon', 'sin_doy', 'cos_doy', 'sst', 'sss', 'sla', 'ug', 'vg', 'u10', 'v10'];
  const raw = names.map((n, i) => (n === 'sst' ? 3 : n === 'sla' ? 2 : 1) * (0.2 + hash(lat, lon, i)));
  const total = raw.reduce((a, b) => a + b, 0);
  return delay({
    lat, lon, date, method: 'demo_synthetic',
    feature_attributions: Object.fromEntries(names.map((n, i) => [n, raw[i] / total])),
    data_source: SOURCE,
  });
}
