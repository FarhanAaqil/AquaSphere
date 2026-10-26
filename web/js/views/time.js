/**
 * AquaSphere Time View — Temporal Evolution across Monsoon Phases
 */

import { fetchPredictBatch, regionName } from '../api.js';
import { state } from '../state.js';

let timeChart = null;

const TIME_POINTS = [
  '2025-03-31',
  '2025-04-30',
  '2025-05-31',
  '2025-06-30',
  '2025-07-31',
  '2025-08-31',
];

export async function renderTime() {
  const container = document.createElement('div');

  // Request batch predictions across all time points
  const points = TIME_POINTS.map(d => ({ lat: state.lat, lon: state.lon, date: d }));
  const batchRes = await fetchPredictBatch(points);
  const preds = batchRes.predictions;

  const sstSeries = preds.map(p => p.temperatures[0]);
  const t100Series = preds.map(p => p.temperatures[7]); // 100m depth
  const d20Series = preds.map(p => p.d20 || 80.0);

  container.innerHTML = `
    <h1 class="page">Time View</h1>
    <p class="sub">
      Multi-sensor reconstruction across seasonal monsoon transitions at <b>${regionName(state.lat, state.lon)}</b> (${state.lat.toFixed(1)}°N, ${state.lon.toFixed(1)}°E).
    </p>

    <div class="card" style="height: 340px; position: relative;">
      <canvas id="timeSeriesCanvas"></canvas>
    </div>

    <div class="banner info" style="margin-top: 20px;">
      <span>ⓘ</span>
      <div>
        <b>Monsoon Cycle Dynamics:</b> In the Arabian Sea, intense southwest monsoon winds drive coastal upwelling and thermocline shoaling during July–September.
        In the Bay of Bengal, heavy freshwater river runoff sustains strong barrier layers and warmer surface temperatures.
      </div>
    </div>

    <div class="section-head">
      <h2>Temporal evolution metrics</h2>
      <span class="note">surface vs. subsurface thermal coupling</span>
    </div>
    <div class="card">
      <table class="dtab">
        <thead>
          <tr>
            <th>Date</th>
            <th>Surface SST (°C)</th>
            <th>100m Subsurface (°C)</th>
            <th>Thermocline D20 (m)</th>
            <th>Data Source</th>
          </tr>
        </thead>
        <tbody>
          ${preds.map((p, i) => `
            <tr>
              <td><b>${p.date}</b></td>
              <td>${sstSeries[i].toFixed(2)}</td>
              <td>${t100Series[i].toFixed(2)}</td>
              <td>${d20Series[i].toFixed(1)}</td>
              <td><span style="font-size: 10px; color: var(--teal);">${p.data_source}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;

  // Render Chart.js
  setTimeout(() => {
    const canvas = container.querySelector('#timeSeriesCanvas');
    if (!canvas) return;
    if (timeChart) {
      timeChart.destroy();
      timeChart = null;
    }

    timeChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: TIME_POINTS,
        datasets: [
          {
            label: 'Surface SST (0m)',
            data: sstSeries,
            borderColor: '#e3a04a',
            backgroundColor: 'rgba(227, 160, 74, 0.12)',
            fill: true,
            tension: 0.35,
            pointRadius: 4,
          },
          {
            label: 'Subsurface (100m)',
            data: t100Series,
            borderColor: '#33b9ac',
            borderWidth: 2,
            tension: 0.35,
            pointRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            title: { display: true, text: 'Temperature (°C)', color: '#8fa5ad' },
            grid: { color: '#16313d' },
          },
          x: {
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
