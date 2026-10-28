// Geography helpers shared by maps, the cube and the globe.

import { asset } from './api.js';

export const DOMAIN = { lat_min: 5, lat_max: 30, lon_min: 45, lon_max: 105 };
export const BOB_LON = 78; // same basin split as scripts/build_web_data.py

export function region(lat, lon) {
  if (lat < 5) return 'Equatorial';
  return lon >= BOB_LON ? 'Bay of Bengal' : 'Arabian Sea';
}

export function inDomain(lat, lon, d = DOMAIN) {
  return lat >= d.lat_min && lat <= d.lat_max && lon >= d.lon_min && lon <= d.lon_max;
}

let landRings = null;
export async function nioLand() {
  if (!landRings) landRings = (await asset('land_nio.json'))?.rings || [];
  return landRings;
}

function inRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Point-in-land test against the clipped Natural Earth 1:50m outline. Call nioLand() first. */
export function onLand(lat, lon) {
  return (landRings || []).some((r) => inRing(lon, lat, r));
}

export const fmtLat = (v) => `${Math.abs(v).toFixed(2)}°${v >= 0 ? 'N' : 'S'}`;
export const fmtLon = (v) => `${Math.abs(v).toFixed(2)}°${v >= 0 ? 'E' : 'W'}`;
