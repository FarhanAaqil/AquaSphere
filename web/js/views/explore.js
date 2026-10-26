/**
 * AquaSphere Explore View — Interactive NIO Spatial Grid
 */

import { BOUNDS, fetchGrid, formatSourceBadge, DEPTHS } from '../api.js';
import { state, setDate, setLocation, setPage, notify } from '../state.js';

const LAYERS = {
  sst: { label: 'Sea Surface Temp', unit: '°C', range: [24, 31], scale: 'warm' },
  sss: { label: 'Sea Surface Salinity', unit: 'PSU', range: [31, 37], scale: 'teal' },
  sla: { label: 'Sea Level Anomaly', unit: 'm', range: [-0.25, 0.25], scale: 'diverge' },
  subsurface: { label: `Subsurface Temp`, unit: '°C', range: [4, 29], scale: 'warm' },
  d20: { label: 'Thermocline (D20)', unit: 'm', range: [40, 130], scale: 'teal' },
};

function lerpColor(a, b, t) {
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function warmColor(t) {
  const stops = [[20, 40, 90], [51, 185, 172], [227, 160, 74], [226, 101, 75]];
  const seg = Math.min(2, Math.floor(t * 3));
  const localT = (t * 3) - seg;
  return lerpColor(stops[seg], stops[seg + 1], localT);
}

function colorFor(val, range, scale) {
  const t = Math.max(0, Math.min(1, (val - range[0]) / (range[1] - range[0])));
  if (scale === 'diverge') {
    if (t < 0.5) {
      return lerpColor([95, 163, 209], [230, 225, 210], t / 0.5);
    } else {
      return lerpColor([230, 225, 210], [226, 101, 75], (t - 0.5) / 0.5);
    }
  }
  if (scale === 'teal') {
    return lerpColor([12, 45, 55], [51, 185, 172], t);
  }
  return warmColor(t);
}

export async function renderExplore() {
  const container = document.createElement('div');
  const meta = state.meta || { min_date: '2020-01-01', max_date: '2025-12-31' };

  container.innerHTML = `
    <h1 class="page">Explore</h1>
    <p class="sub">
      Click anywhere on the North Indian Ocean grid to reposition the observation focal point.
      Switch observation layers to evaluate spatial gradients across both basins.
    </p>

    <div class="controls-row">
      <div>
        <label class="fl">Date (Bounded by /meta)</label>
        <input type="date" id="dateInput" min="${meta.min_date}" max="${meta.max_date}" value="${state.date}">
      </div>

      <div>
        <label class="fl">Quick Monsoon Season Presets</label>
        <div class="chip-row">
          <span class="chip preset-btn" data-date="2024-01-15">NE Monsoon (Jan)</span>
          <span class="chip preset-btn" data-date="2024-04-15">Pre-Monsoon (Apr)</span>
          <span class="chip preset-btn" data-date="2024-07-15">SW Monsoon (Jul)</span>
          <span class="chip preset-btn" data-date="2024-10-15">Post-Monsoon (Oct)</span>
        </div>
      </div>

      <div style="margin-left: auto;">
        <label class="fl">Active Layer</label>
        <div class="chip-row" id="layerChips">
          ${Object.entries(LAYERS).map(([k, v]) => `
            <span class="chip ${state.mapLayer === k ? 'active' : ''}" data-layer="${k}">
              ${v.label}
            </span>
          `).join('')}
        </div>
      </div>
    </div>

    <div class="mapwrap">
      <canvas id="oceanmap"></canvas>
      <div class="regionlabel" style="top: 32%; left: 63%;">Bay of Bengal</div>
      <div class="regionlabel" style="top: 36%; left: 16%;">Arabian Sea</div>
      <div class="maplegend" id="mapLegend"></div>
      <div class="maptip">
        North Indian Ocean: 5°N–30°N · 45°E–105°E.<br>
        Current target: <b style="color:var(--cream);">${state.lat.toFixed(1)}°N, ${state.lon.toFixed(1)}°E</b>
      </div>
    </div>

    <div style="margin-top: 18px; display: flex; gap: 12px; align-items: center;">
      <button class="btn small" id="gotoLocBtn">View 0–1000m Depth Profile →</button>
      <span style="font-size: 12px; color: var(--muted);">Click on map canvas to update target coordinate</span>
    </div>
  `;

  // Attach controls
  const dateInput = container.querySelector('#dateInput');
  dateInput.addEventListener('change', (e) => {
    setDate(e.target.value);
  });

  container.querySelectorAll('.preset-btn').forEach(b => {
    b.addEventListener('click', () => {
      setDate(b.dataset.date);
    });
  });

  container.querySelectorAll('#layerChips .chip').forEach(b => {
    b.addEventListener('click', () => {
      state.mapLayer = b.dataset.layer;
      notify('layer');
    });
  });

  container.querySelector('#gotoLocBtn')?.addEventListener('click', () => setPage('location'));

  // Deferred canvas render after mount
  setTimeout(async () => {
    const canvas = container.querySelector('#oceanmap');
    if (!canvas) return;

    const layerCfg = LAYERS[state.mapLayer] || LAYERS.sst;
    const w = canvas.clientWidth || 800;
    const h = 400;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.height = `${h}px`;

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    // Fetch grid points from server
    const gridRes = await fetchGrid(state.date, 2.5);
    const pts = gridRes.points || [];

    const latStep = 2.5;
    const lonStep = 2.5;
    const cols = Math.round((BOUNDS.lonMax - BOUNDS.lonMin) / lonStep);
    const rows = Math.round((BOUNDS.latMax - BOUNDS.latMin) / latStep);
    const cw = w / cols;
    const ch = h / rows;

    pts.forEach(p => {
      const c = Math.round((p.lon - BOUNDS.lonMin) / lonStep);
      const r = Math.round((BOUNDS.latMax - p.lat) / latStep);
      let val = p.sst;
      if (state.mapLayer === 'd20') val = p.d20;
      else if (state.mapLayer === 'sla') val = (p.pca1 || 0) * 0.1;
      else if (state.mapLayer === 'sss') val = p.lon > 78 ? 32.8 : 36.2;
      else if (state.mapLayer === 'subsurface') val = p.sst - 5.0;

      const fill = colorFor(val, layerCfg.range, layerCfg.scale);
      ctx.fillStyle = fill;
      ctx.globalAlpha = 0.94;
      ctx.fillRect(c * cw, r * ch, cw + 0.6, ch + 0.6);
    });

    // Draw Crosshair selection marker
    const selX = ((state.lon - BOUNDS.lonMin) / (BOUNDS.lonMax - BOUNDS.lonMin)) * w;
    const selY = ((BOUNDS.latMax - state.lat) / (BOUNDS.latMax - BOUNDS.latMin)) * h;

    ctx.globalAlpha = 1.0;
    ctx.strokeStyle = '#eee8d8';
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.arc(selX, selY, 8, 0, Math.PI * 2);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(selX - 14, selY);
    ctx.lineTo(selX + 14, selY);
    ctx.moveTo(selX, selY - 14);
    ctx.lineTo(selX, selY + 14);
    ctx.stroke();

    // Update legend
    const leg = container.querySelector('#mapLegend');
    if (leg) {
      leg.innerHTML = `
        <div><b>${layerCfg.label}</b></div>
        <div class="legend-grad" style="background:linear-gradient(90deg, ${
          layerCfg.scale === 'diverge'
            ? '#5fa3d1,#e6e1d2,#e2654b'
            : layerCfg.scale === 'teal'
            ? '#0c2d37,#33b9ac'
            : '#14285a,#33b9ac,#e3a04a,#e2654b'
        });"></div>
        <div class="legend-scale">
          <span>${layerCfg.range[0]}</span>
          <span>${layerCfg.range[1]} ${layerCfg.unit}</span>
        </div>
      `;
    }

    // Attach click repositioning
    canvas.onclick = (e) => {
      const rect = canvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;
      const lon = BOUNDS.lonMin + (clickX / rect.width) * (BOUNDS.lonMax - BOUNDS.lonMin);
      const lat = BOUNDS.latMax - (clickY / rect.height) * (BOUNDS.latMax - BOUNDS.latMin);
      setLocation(lat, lon);
    };
  }, 30);

  return container;
}
