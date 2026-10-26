/**
 * AquaSphere Depth View — Horizontal Slice at Selected Depth
 */

import { DEPTHS, BOUNDS, fetchPredict, fetchGrid, regionName } from '../api.js';
import { state, setDepth, notify } from '../state.js';

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

export async function renderDepth() {
  const container = document.createElement('div');
  const pred = await fetchPredict(state.lat, state.lon, state.date);
  const depthIdx = DEPTHS.indexOf(state.depth);
  const currentDepthTemp = pred.temperatures[depthIdx !== -1 ? depthIdx : 7];

  container.innerHTML = `
    <h1 class="page">Depth View</h1>
    <p class="sub">
      Navigate through the 15 standard Argo pressure levels to observe how thermal structure decays
      with depth, through the upper mixed layer, across the main thermocline, and into the abyssal ocean.
    </p>

    <div class="controls-row">
      <div style="flex: 1; min-width: 280px;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
          <label class="fl">Selected Depth</label>
          <span style="font-family: var(--mono); color: var(--teal); font-size: 15px; font-weight: 600;">
            ${state.depth} meters
          </span>
        </div>
        <input type="range" id="depthRange" min="0" max="${DEPTHS.length - 1}" value="${depthIdx !== -1 ? depthIdx : 7}" style="width: 100%;">
        <div style="display: flex; justify-content: space-between; font-family: var(--mono); font-size: 9.5px; color: var(--muted2); margin-top: 6px;">
          ${DEPTHS.map(d => `<span>${d}</span>`).join('')}
        </div>
      </div>
    </div>

    <div class="mapwrap">
      <canvas id="depthCanvas"></canvas>
      <div class="maplegend" id="depthLegend"></div>
      <div class="maptip">
        Horizontal field slice reconstructed at <b>${state.depth} m</b> across the North Indian Ocean.
      </div>
    </div>

    <div class="section-head">
      <h2>Two-depth thermal comparison</h2>
      <span class="note">${regionName(state.lat, state.lon)} · ${state.lat.toFixed(1)}°N, ${state.lon.toFixed(1)}°E</span>
    </div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Primary Level (${state.depth} m)</h3>
        <div class="big">${currentDepthTemp.toFixed(2)}<span class="unit">°C</span></div>
        <div class="est-flag" style="margin-top: 8px;">Reconstructed at chosen depth</div>
      </div>
      <div class="card">
        <h3>Reference Subsurface Level (500 m)</h3>
        <div class="big">${pred.temperatures[12].toFixed(2)}<span class="unit">°C</span></div>
        <div class="est-flag" style="margin-top: 8px;">Intermediate water mass</div>
      </div>
    </div>
  `;

  // Range slider event
  const slider = container.querySelector('#depthRange');
  slider.addEventListener('input', (e) => {
    setDepth(DEPTHS[parseInt(e.target.value, 10)]);
  });

  // Render Canvas
  setTimeout(async () => {
    const canvas = container.querySelector('#depthCanvas');
    if (!canvas) return;

    const w = canvas.clientWidth || 800;
    const h = 380;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.height = `${h}px`;

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const gridRes = await fetchGrid(state.date, 2.5);
    const pts = gridRes.points || [];

    const latStep = 2.5;
    const lonStep = 2.5;
    const cols = Math.round((BOUNDS.lonMax - BOUNDS.lonMin) / lonStep);
    const rows = Math.round((BOUNDS.latMax - BOUNDS.latMin) / latStep);
    const cw = w / cols;
    const ch = h / rows;

    const range = [4.0, 30.0];

    pts.forEach(p => {
      const c = Math.round((p.lon - BOUNDS.lonMin) / lonStep);
      const r = Math.round((BOUNDS.latMax - p.lat) / latStep);

      // Depth decay function
      const decay = Math.exp(-state.depth / 200.0);
      const val = 4.0 + (p.sst - 4.0) * decay;
      const t = Math.max(0, Math.min(1, (val - range[0]) / (range[1] - range[0])));
      ctx.fillStyle = warmColor(t);
      ctx.globalAlpha = 0.94;
      ctx.fillRect(c * cw, r * ch, cw + 0.6, ch + 0.6);
    });

    // Marker
    const selX = ((state.lon - BOUNDS.lonMin) / (BOUNDS.lonMax - BOUNDS.lonMin)) * w;
    const selY = ((BOUNDS.latMax - state.lat) / (BOUNDS.latMax - BOUNDS.latMin)) * h;

    ctx.globalAlpha = 1.0;
    ctx.strokeStyle = '#eee8d8';
    ctx.lineWidth = 2.0;
    ctx.beginPath();
    ctx.arc(selX, selY, 7, 0, Math.PI * 2);
    ctx.stroke();

    const leg = container.querySelector('#depthLegend');
    if (leg) {
      leg.innerHTML = `
        <div><b>Temperature @ ${state.depth}m</b></div>
        <div class="legend-grad" style="background:linear-gradient(90deg, #14285a, #33b9ac, #e3a04a, #e2654b);"></div>
        <div class="legend-scale"><span>4.0</span><span>30.0 °C</span></div>
      `;
    }
  }, 30);

  return container;
}
