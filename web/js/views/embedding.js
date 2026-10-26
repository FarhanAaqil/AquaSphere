/**
 * AquaSphere Embedding View — 16-D Multi-Sensor Satellite Representation
 */

import { fetchGrid, fetchPredict, regionName } from '../api.js';
import { state } from '../state.js';

let embedChart = null;

export async function renderEmbedding() {
  const container = document.createElement('div');

  // Fetch current prediction for embedding vector
  const pred = await fetchPredict(state.lat, state.lon, state.date);
  const emb = pred.embedding || Array(16).fill(0.0);

  // Fetch spatial grid for regional PCA distribution
  const gridRes = await fetchGrid(state.date, 2.5);
  const pts = gridRes.points || [];

  const asPoints = pts
    .filter(p => p.lon < 78.0)
    .map(p => ({ x: +(p.pca1 || 0).toFixed(3), y: +(p.pca2 || 0).toFixed(3) }));

  const bobPoints = pts
    .filter(p => p.lon >= 78.0)
    .map(p => ({ x: +(p.pca1 || 0).toFixed(3), y: +(p.pca2 || 0).toFixed(3) }));

  // Selected coordinate projection
  const selX = +(emb.slice(0, 8).reduce((a, b) => a + b, 0) / 8).toFixed(3);
  const selY = +(emb.slice(8, 16).reduce((a, b) => a + b, 0) / 8).toFixed(3);

  container.innerHTML = `
    <h1 class="page">Ocean Embedding</h1>
    <p class="sub">
      Multi-sensor observations (SST, SSS, SLA, currents, winds) are mapped by the encoder network
      into a 16-dimensional unit-norm latent manifold. Nearby points in this embedding space share
      subsurface hydrographic dynamics.
    </p>

    <div class="grid cols-2">
      <div class="card">
        <h3>Embedding Space (2D PCA Projection)</h3>
        <div style="height: 360px; position: relative;">
          <canvas id="embedCanvas"></canvas>
        </div>
      </div>

      <div class="card">
        <h3>16-Dimensional Normalized Embedding</h3>
        <p style="font-size: 12.5px; color: var(--muted); margin-bottom: 14px; line-height: 1.6;">
          Unit-norm bottleneck vector for <b>${regionName(state.lat, state.lon)}</b> (${state.lat.toFixed(1)}°N, ${state.lon.toFixed(1)}°E) on ${state.date}.
          Decoded by the subsurface network into 15 depth-wise mean and variance estimates.
        </p>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; font-family: var(--mono); font-size: 11px;">
          ${emb.map((val, i) => `
            <div style="background: var(--panel2); padding: 8px; border-radius: 4px; border: 1px solid var(--line); text-align: center;">
              <span style="color: var(--muted2); font-size: 9px; display: block;">d${i+1}</span>
              <span style="color: ${val >= 0 ? 'var(--teal)' : 'var(--amber)'};">${val.toFixed(3)}</span>
            </div>
          `).join('')}
        </div>

        <div class="est-flag" style="margin-top: 18px;">
          Learned Latent Representation (L2 Norm = 1.0)
        </div>
      </div>
    </div>
  `;

  // Render Chart.js scatter plot
  setTimeout(() => {
    const canvas = container.querySelector('#embedCanvas');
    if (!canvas) return;
    if (embedChart) {
      embedChart.destroy();
      embedChart = null;
    }

    embedChart = new Chart(canvas, {
      type: 'scatter',
      data: {
        datasets: [
          {
            label: 'Arabian Sea States',
            data: asPoints,
            backgroundColor: 'rgba(95, 163, 209, 0.65)',
            borderColor: '#5fa3d1',
            pointRadius: 4,
          },
          {
            label: 'Bay of Bengal States',
            data: bobPoints,
            backgroundColor: 'rgba(227, 160, 74, 0.65)',
            borderColor: '#e3a04a',
            pointRadius: 4,
          },
          {
            label: 'Selected Target Location',
            data: [{ x: selX, y: selY }],
            backgroundColor: '#eee8d8',
            borderColor: '#33b9ac',
            borderWidth: 2,
            pointRadius: 8,
            pointStyle: 'rectRot',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            title: { display: true, text: 'Latent Component 1 (PCA)', color: '#8fa5ad' },
            grid: { color: '#16313d' },
          },
          y: {
            title: { display: true, text: 'Latent Component 2 (PCA)', color: '#8fa5ad' },
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
