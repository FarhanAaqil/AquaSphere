/**
 * AquaSphere Compare View — Dual-Location Simultaneous Reconstruction
 */

import { DEPTHS, fetchPredictBatch, regionName } from '../api.js';
import { state, notify } from '../state.js';

let compareChart = null;

export async function renderCompare() {
  const container = document.createElement('div');
  const A = state.compareA;
  const B = state.compareB;

  // Single batch call for both locations
  const batchRes = await fetchPredictBatch([
    { lat: A.lat, lon: A.lon, date: A.date },
    { lat: B.lat, lon: B.lon, date: B.date },
  ]);

  const predA = batchRes.predictions[0];
  const predB = batchRes.predictions[1];

  container.innerHTML = `
    <h1 class="page">Compare</h1>
    <p class="sub">
      Contrast vertical stratification across distinct regimes (e.g., Arabian Sea high-salinity upwelling vs.
      Bay of Bengal low-salinity riverine barrier layers) simultaneously.
    </p>

    <div class="grid cols-2">
      <div class="card">
        <h3>Location A</h3>
        <div class="controls-row" style="margin-bottom: 8px;">
          <div style="flex: 1;">
            <label class="fl">Latitude (°N)</label>
            <input type="range" id="latA" min="5" max="30" step="0.5" value="${A.lat}" style="width: 100%;">
            <div style="font-family: var(--mono); font-size: 12px; margin-top: 4px;">${A.lat.toFixed(1)}°N</div>
          </div>
          <div style="flex: 1;">
            <label class="fl">Longitude (°E)</label>
            <input type="range" id="lonA" min="45" max="105" step="0.5" value="${A.lon}" style="width: 100%;">
            <div style="font-family: var(--mono); font-size: 12px; margin-top: 4px;">${A.lon.toFixed(1)}°E</div>
          </div>
        </div>
        <div style="font-size: 12px; color: var(--muted);">${regionName(A.lat, A.lon)} · ${A.date}</div>
      </div>

      <div class="card">
        <h3>Location B</h3>
        <div class="controls-row" style="margin-bottom: 8px;">
          <div style="flex: 1;">
            <label class="fl">Latitude (°N)</label>
            <input type="range" id="latB" min="5" max="30" step="0.5" value="${B.lat}" style="width: 100%;">
            <div style="font-family: var(--mono); font-size: 12px; margin-top: 4px;">${B.lat.toFixed(1)}°N</div>
          </div>
          <div style="flex: 1;">
            <label class="fl">Longitude (°E)</label>
            <input type="range" id="lonB" min="45" max="105" step="0.5" value="${B.lon}" style="width: 100%;">
            <div style="font-family: var(--mono); font-size: 12px; margin-top: 4px;">${B.lon.toFixed(1)}°E</div>
          </div>
        </div>
        <div style="font-size: 12px; color: var(--muted);">${regionName(B.lat, B.lon)} · ${B.date}</div>
      </div>
    </div>

    <div class="section-head">
      <h2>Vertical thermal comparison (0–1000m)</h2>
      <span class="note">unified axis for direct thermal differential reading</span>
    </div>
    <div class="card" style="height: 380px; position: relative;">
      <canvas id="compareCanvas"></canvas>
    </div>

    <div class="grid cols-2" style="margin-top: 16px;">
      <div class="card">
        <h3>A — Thermocline (D20) &amp; MLD</h3>
        <div class="big">${(predA.d20 || 82.0).toFixed(1)}<span class="unit">m D20</span></div>
        <div style="font-size: 13px; color: var(--muted); margin-top: 6px;">
          MLD: ${(predA.mld || 35.0).toFixed(1)} m · Surface SST: ${predA.temperatures[0].toFixed(2)} °C
        </div>
      </div>
      <div class="card">
        <h3>B — Thermocline (D20) &amp; MLD</h3>
        <div class="big">${(predB.d20 || 82.0).toFixed(1)}<span class="unit">m D20</span></div>
        <div style="font-size: 13px; color: var(--muted); margin-top: 6px;">
          MLD: ${(predB.mld || 35.0).toFixed(1)} m · Surface SST: ${predB.temperatures[0].toFixed(2)} °C
        </div>
      </div>
    </div>
  `;

  // Attach slider input listeners
  container.querySelector('#latA').addEventListener('input', (e) => {
    state.compareA.lat = parseFloat(e.target.value);
    notify('compare');
  });
  container.querySelector('#lonA').addEventListener('input', (e) => {
    state.compareA.lon = parseFloat(e.target.value);
    notify('compare');
  });
  container.querySelector('#latB').addEventListener('input', (e) => {
    state.compareB.lat = parseFloat(e.target.value);
    notify('compare');
  });
  container.querySelector('#lonB').addEventListener('input', (e) => {
    state.compareB.lon = parseFloat(e.target.value);
    notify('compare');
  });

  // Render Chart.js
  setTimeout(() => {
    const canvas = container.querySelector('#compareCanvas');
    if (!canvas) return;
    if (compareChart) {
      compareChart.destroy();
      compareChart = null;
    }

    compareChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: DEPTHS,
        datasets: [
          {
            label: `A: ${regionName(A.lat, A.lon)} (${A.lat.toFixed(1)}°N, ${A.lon.toFixed(1)}°E)`,
            data: predA.temperatures,
            borderColor: '#33b9ac',
            borderWidth: 2.5,
            pointRadius: 3,
            tension: 0.3,
          },
          {
            label: `B: ${regionName(B.lat, B.lon)} (${B.lat.toFixed(1)}°N, ${B.lon.toFixed(1)}°E)`,
            data: predB.temperatures,
            borderColor: '#e3a04a',
            borderWidth: 2.5,
            pointRadius: 3,
            tension: 0.3,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            reverse: true,
            title: { display: true, text: 'Depth (m)', color: '#8fa5ad' },
            grid: { color: '#16313d' },
          },
          x: {
            title: { display: true, text: 'Temperature (°C)', color: '#8fa5ad' },
            grid: { color: '#16313d' },
          },
        },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { boxWidth: 12 },
          },
        },
      },
    });
  }, 40);

  return container;
}
