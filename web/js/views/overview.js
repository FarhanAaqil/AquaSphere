/**
 * AquaSphere Overview View
 */

import { fetchPredict, fetchPredictBatch, formatSourceBadge, regionName } from '../api.js';
import { state, setPage } from '../state.js';

export async function renderOverview() {
  const container = document.createElement('div');

  // Fetch current point prediction
  const pred = await fetchPredict(state.lat, state.lon, state.date);
  const sst = pred.temperatures[0];
  const mld = pred.mld || 35.0;
  const d20 = pred.d20 || 80.0;
  const sourceBadge = formatSourceBadge(pred.data_source);

  // Monitor 5 strategic NIO regime points via single batch call
  const monitorPoints = [
    { lat: 14.5, lon: 89.5, date: state.date }, // Central Bay of Bengal
    { lat: 9.0, lon: 83.0, date: state.date },  // Sri Lanka Dome
    { lat: 18.0, lon: 67.0, date: state.date }, // Northern Arabian Sea
    { lat: 11.0, lon: 62.0, date: state.date }, // Western Arabian Sea Upwelling
    { lat: 21.0, lon: 90.0, date: state.date }, // Northern BoB River Plume
  ];
  const batchRes = await fetchPredictBatch(monitorPoints);

  const alerts = batchRes.predictions.map(p => {
    const pSST = p.temperatures[0];
    const anom = +(pSST - 28.0).toFixed(2);
    let sev = 'low';
    let head = `Normal seasonal regime — ${regionName(p.lat, p.lon)}`;
    if (anom > 0.8) {
      sev = 'high';
      head = `Elevated upper-ocean heat anomaly (+${anom}°C) — ${regionName(p.lat, p.lon)}`;
    } else if (anom < -0.6) {
      sev = 'med';
      head = `Strong upwelling signature (${anom}°C) — ${regionName(p.lat, p.lon)}`;
    }
    return {
      sev,
      head,
      loc: `${p.lat.toFixed(1)}°N, ${p.lon.toFixed(1)}°E`,
      date: p.date,
      source: p.data_source,
    };
  }).sort((a, b) => ({ high: 0, med: 1, low: 2 }[a.sev] - { high: 0, med: 1, low: 2 }[b.sev]));

  container.innerHTML = `
    <div class="hero">
      <div class="lede">
        <div class="kicker">SIH 26066 · MoES / INCOIS North Indian Ocean</div>
        <h1 class="page">Subsurface ocean state, reconstructed from the surface</h1>
        <p>
          AquaSphere combines multi-sensor satellite observations (SST, SSS, SLA, winds) into a calibrated
          deep representation to reconstruct temperature profiles from 0 to 1000 m. Every output is an estimate
          accompanied by conformal uncertainty bounds and verifiable data provenance.
        </p>
        <div class="flowline">
          <span class="step">Surface Obs</span><span class="arrow">→</span>
          <span class="step">Multi-Sensor Encoder</span><span class="arrow">→</span>
          <span class="step">Subsurface Profile</span><span class="arrow">→</span>
          <span class="step">Conformal Uncertainty</span><span class="arrow">→</span>
          <span class="step">Held-Out Validation</span>
        </div>
        <div style="margin-top: 24px; display: flex; gap: 12px; flex-wrap: wrap;">
          <button class="btn" id="runDemoBtn">Run guided demonstration</button>
          <button class="btn ghost" id="openExploreBtn">Open the interactive map</button>
        </div>
      </div>

      <div class="card" style="align-self: center;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;">
          <h3>Selected location snapshot</h3>
          <div>${sourceBadge}</div>
        </div>
        <div style="font-family: var(--serif); font-size: 19px; margin-bottom: 2px;">
          ${regionName(state.lat, state.lon)}
        </div>
        <div style="color: var(--muted); font-size: 12px; margin-bottom: 16px;">
          ${state.lat.toFixed(1)}°N, ${state.lon.toFixed(1)}°E · ${state.date}
        </div>
        <div class="grid cols-2" style="gap: 12px;">
          <div>
            <div style="color: var(--muted2); font-size: 10.5px;">Surface Temp (0m)</div>
            <div class="big" style="font-size: 20px;">${sst.toFixed(2)}<span class="unit">°C</span></div>
          </div>
          <div>
            <div style="color: var(--muted2); font-size: 10.5px;">Thermocline (D20)</div>
            <div class="big" style="font-size: 20px;">${d20.toFixed(1)}<span class="unit">m</span></div>
          </div>
          <div>
            <div style="color: var(--muted2); font-size: 10.5px;">Mixed Layer Depth</div>
            <div class="big" style="font-size: 20px;">${mld.toFixed(1)}<span class="unit">m</span></div>
          </div>
          <div>
            <div style="color: var(--muted2); font-size: 10.5px;">Deep Temp (1000m)</div>
            <div class="big" style="font-size: 20px;">${pred.temperatures[14].toFixed(2)}<span class="unit">°C</span></div>
          </div>
        </div>
        ${pred.in_training_set ? '<div class="training-warn-flag">⚠ In Training Set</div>' : '<div class="holdout-flag">✓ Held-Out Point</div>'}
      </div>
    </div>

    <div class="section-head">
      <h2>Regime decision summary</h2>
      <span class="note">evidence-backed analytical inference</span>
    </div>
    <div class="card">
      <p style="margin: 0 0 12px; font-size: 13.5px; line-height: 1.65;">
        ${regionName(state.lat, state.lon)} at <b>${state.lat.toFixed(1)}°N, ${state.lon.toFixed(1)}°E</b> is currently estimated with an upper-surface temperature of <b>${sst.toFixed(2)}°C</b> and an isothermal thermocline depth (D20) near <b>${d20.toFixed(1)} m</b>.
        The 90% conformal uncertainty interval spans an average width of <b>±${(pred.conformal_q * pred.stds[0]).toFixed(2)}°C</b> at the surface.
      </p>
      <div class="chip-row">
        <span class="chip" id="chipLoc">Inspect 0–1000m profile</span>
        <span class="chip" id="chipVal">Held-out Argo validation</span>
        <span class="chip" id="chipRep">Export provenance report</span>
      </div>
    </div>

    <div class="section-head">
      <h2>Regional regime monitoring</h2>
      <span class="note">evaluated live across NIO key coordinates</span>
    </div>
    <div class="card">
      ${alerts.map(a => `
        <div class="alertitem">
          <div class="sev ${a.sev}"></div>
          <div class="body">
            <div class="head">${a.head}</div>
            <div class="meta">${a.loc} · ${a.date} · source: ${a.source}</div>
          </div>
        </div>
      `).join('')}
    </div>
  `;

  // Attach button events
  container.querySelector('#runDemoBtn')?.addEventListener('click', () => {
    state.demo = { active: true, step: 0 };
    setPage('overview');
  });
  container.querySelector('#openExploreBtn')?.addEventListener('click', () => setPage('explore'));
  container.querySelector('#chipLoc')?.addEventListener('click', () => setPage('location'));
  container.querySelector('#chipVal')?.addEventListener('click', () => setPage('validation'));
  container.querySelector('#chipRep')?.addEventListener('click', () => setPage('reports'));

  return container;
}
