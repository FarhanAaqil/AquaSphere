// Regular-grid predictions for a date via /predict_batch (all 15 depths per point).
// Land cells are masked client-side; the API itself would happily predict over land.

import * as api from './api.js';
import { DOMAIN, nioLand, onLand } from './geo.js';

export const GRID_STEP = 2.5;

const cache = new Map();

export async function loadGrid(date, { signal } = {}) {
  const key = `${date}|${api.isDemo?.() ? 'demo' : 'api'}`;
  if (cache.has(key)) return cache.get(key);
  await nioLand();

  const lats = [];
  const lons = [];
  for (let la = DOMAIN.lat_min; la <= DOMAIN.lat_max + 1e-6; la += GRID_STEP) lats.push(+la.toFixed(3));
  for (let lo = DOMAIN.lon_min; lo <= DOMAIN.lon_max + 1e-6; lo += GRID_STEP) lons.push(+lo.toFixed(3));

  const items = [];
  const index = [];
  lats.forEach((lat, j) => lons.forEach((lon, i) => {
    if (onLand(lat, lon)) return;
    items.push({ lat, lon, date });
    index.push([j, i]);
  }));

  const res = await api.predictBatch(items, { signal });
  const depths = res.predictions[0]?.depths || [];
  const blank = () => lats.map(() => lons.map(() => null));
  const values = depths.map(blank);
  const lower = depths.map(blank);
  const upper = depths.map(blank);
  const d20 = blank();
  const mld = blank();
  const sources = [];

  res.predictions.forEach((p, n) => {
    const [j, i] = index[n];
    p.temperatures.forEach((t, d) => {
      values[d][j][i] = t;
      lower[d][j][i] = p.interval_lower[d];
      upper[d][j][i] = p.interval_upper[d];
    });
    d20[j][i] = p.d20;
    mld[j][i] = p.mld;
    sources.push(p.data_source);
  });

  const grid = { date, lats, lons, depths, values, lower, upper, d20, mld, sources, nOcean: items.length };
  if (cache.size > 8) cache.delete(cache.keys().next().value);
  cache.set(key, grid);
  return grid;
}
