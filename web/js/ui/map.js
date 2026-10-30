// Lightweight SVG map of the North Indian Ocean (equirectangular, degrees as SVG units).
// Click to pick a point, plot markers, or lay a canvas heatmap underneath the coastline.

import { DOMAIN, inDomain, nioLand, fmtLat, fmtLon } from '../geo.js';

const NS = 'http://www.w3.org/2000/svg';
export const VIEW = { lon0: 43, lon1: 107, lat0: 3, lat1: 32 };
const W = VIEW.lon1 - VIEW.lon0;
const H = VIEW.lat1 - VIEW.lat0;

const x = (lon) => lon - VIEW.lon0;
const y = (lat) => VIEW.lat1 - lat;

function el(name, attrs = {}, parent) {
  const n = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  parent?.append(n);
  return n;
}

export async function createMap(container, { onPick, label = 'Map of the North Indian Ocean', regions = true } = {}) {
  container.classList.add('map');
  container.style.aspectRatio = `${W} / ${H}`;
  const canvas = document.createElement('canvas');
  canvas.hidden = true;
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', role: 'img', 'aria-label': label });
  container.replaceChildren(canvas, svg);

  // Graticule + labels
  const grat = el('g', {}, svg);
  for (let lon = 50; lon <= 100; lon += 10) {
    el('line', { class: 'map__grat', x1: x(lon), x2: x(lon), y1: 0, y2: H }, grat);
  }
  for (let lat = 10; lat <= 30; lat += 10) {
    el('line', { class: 'map__grat', x1: 0, x2: W, y1: y(lat), y2: y(lat) }, grat);
  }

  const land = el('path', { class: 'map__land', d: '' }, svg);
  const rings = await nioLand();
  land.setAttribute('d', rings.map((r) => `M${r.map(([lo, la]) => `${x(lo).toFixed(2)},${y(la).toFixed(2)}`).join('L')}Z`).join(''));

  el('rect', {
    x: x(DOMAIN.lon_min), y: y(DOMAIN.lat_max),
    width: DOMAIN.lon_max - DOMAIN.lon_min, height: DOMAIN.lat_max - DOMAIN.lat_min,
    fill: 'none', stroke: 'rgba(34,211,238,0.55)', 'stroke-dasharray': '0.6 0.5', 'stroke-width': 1,
    'vector-effect': 'non-scaling-stroke',
  }, svg);

  // Text in a degree-unit viewBox with preserveAspectRatio=none would stretch, so labels live in
  // an HTML overlay positioned by percentage instead.
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:absolute;inset:0;pointer-events:none';
  const pct = (lat, lon) => `left:${(x(lon) / W) * 100}%;top:${(y(lat) / H) * 100}%`;
  const text = (cls, s, lat, lon, extra = '') => {
    const t = document.createElement('span');
    t.className = cls;
    t.textContent = s;
    t.style.cssText = `position:absolute;${pct(lat, lon)};transform:translate(-50%,-50%);${extra}`;
    overlay.append(t);
  };
  for (let lon = 50; lon <= 100; lon += 10) text('map-tick', `${lon}°E`, VIEW.lat0 + 0.9, lon);
  for (let lat = 10; lat <= 30; lat += 10) text('map-tick', `${lat}°N`, lat, VIEW.lon0 + 0.3, 'transform:translate(0,-50%)');
  if (regions) {
    text('map-region', 'Arabian Sea', 14.5, 63);
    text('map-region', 'Bay of Bengal', 14.5, 88.5);
  }
  container.append(overlay);

  const lineLayer = el('g', {}, svg);
  const layer = el('g', {}, svg);
  const target = el('g', { class: 'map__target', hidden: '' }, svg);
  el('circle', { r: 1.1 }, target);
  el('circle', { r: 0.28, class: 'core' }, target);

  let readout;
  if (onPick) {
    const hit = el('rect', { class: 'map__hit', x: 0, y: 0, width: W, height: H }, svg);
    svg.insertBefore(hit, layer);
    readout = document.createElement('div');
    readout.className = 'map__readout';
    readout.textContent = 'Click inside the dashed box to choose a point';
    container.append(readout);

    const toGeo = (evt) => {
      const r = svg.getBoundingClientRect();
      return {
        lon: VIEW.lon0 + ((evt.clientX - r.left) / r.width) * W,
        lat: VIEW.lat1 - ((evt.clientY - r.top) / r.height) * H,
      };
    };
    hit.addEventListener('pointermove', (e) => {
      const g = toGeo(e);
      readout.textContent = `${fmtLat(g.lat)}  ${fmtLon(g.lon)}${inDomain(g.lat, g.lon) ? '' : '  · outside domain'}`;
    });
    hit.addEventListener('click', (e) => {
      const g = toGeo(e);
      onPick({ lat: +g.lat.toFixed(2), lon: +g.lon.toFixed(2), inside: inDomain(g.lat, g.lon) });
    });
  }

  return {
    svg,
    setTarget(lat, lon) {
      if (lat == null) return target.setAttribute('hidden', '');
      target.removeAttribute('hidden');
      target.setAttribute('transform', `translate(${x(lon)} ${y(lat)})`);
    },
    /** A line between two points, drawn in and then flowing (transects). null clears it. */
    setLine(a, b) {
      lineLayer.replaceChildren();
      if (!a || !b) return;
      const ln = el('line', { class: 'map__line is-drawing', x1: x(a.lon), y1: y(a.lat), x2: x(b.lon), y2: y(b.lat) }, lineLayer);
      ln.addEventListener('animationend', () => ln.classList.remove('is-drawing'), { once: true });
    },
    /** points: [{id, lat, lon, color, r, label, muted}] */
    setPoints(points, { onClick, selected } = {}) {
      // An image can't contain buttons; with clickable points the map is a labelled group.
      svg.setAttribute('role', onClick && points.length ? 'group' : 'img');
      layer.replaceChildren();
      for (const p of points) {
        // Container aspect ratio matches the viewBox, so degree units scale uniformly
        const c = el('circle', {
          class: `map__pt${p.id === selected ? ' is-selected' : ''}`,
          cx: x(p.lon), cy: y(p.lat), r: p.r || 0.42,
          fill: p.color || '#22d3ee', 'fill-opacity': p.muted ? 0.35 : 0.95,
        }, layer);
        if (p.label) el('title', {}, c).textContent = p.label;
        if (onClick) {
          c.setAttribute('tabindex', '0');
          c.setAttribute('role', 'button');
          c.setAttribute('aria-label', p.label || `${fmtLat(p.lat)} ${fmtLon(p.lon)}`);
          c.addEventListener('click', (e) => { e.stopPropagation(); onClick(p); });
          c.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(p); }
          });
        }
      }
    },
    /** Paint a lat/lon grid of values under the land layer. cells: [{lat, lon, v}] with uniform step. */
    setHeat(cells, step, colorFor) {
      if (!cells?.length) { canvas.hidden = true; return; }
      const scale = 8;
      canvas.width = W * scale;
      canvas.height = H * scale;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const c of cells) {
        if (c.v == null || Number.isNaN(c.v)) continue;
        ctx.fillStyle = colorFor(c.v);
        ctx.fillRect((x(c.lon) - step / 2) * scale, (y(c.lat) - step / 2) * scale, step * scale + 0.5, step * scale + 0.5);
      }
      canvas.hidden = false;
    },
  };
}
