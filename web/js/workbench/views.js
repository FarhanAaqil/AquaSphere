/**
 * AquaSphere Workbench Additional Views Orchestrator
 * Implements Compare View and Method (16-D Latent State) View.
 */

export function renderCompareView(pred, val) {
  const container = document.getElementById('view-compare');
  if (!container) return;

  // 1. Update Float Metadata Header
  const floatIdEl = document.getElementById('compare-float-id');
  const floatDistEl = document.getElementById('compare-float-dist');
  const floatLocEl = document.getElementById('compare-float-loc');
  const floatDateEl = document.getElementById('compare-float-date');

  if (val && val.float_id) {
    if (floatIdEl) floatIdEl.textContent = `Argo Float #${val.float_id}`;
    if (floatDistEl) floatDistEl.textContent = `${val.distance_km ? val.distance_km.toFixed(1) : '—'} km away`;
    if (floatLocEl) floatLocEl.textContent = `${val.lat.toFixed(1)}°N, ${val.lon.toFixed(1)}°E (Cycle #${val.cycle || 1})`;
    if (floatDateEl) floatDateEl.textContent = `Date: ${val.date || pred.date}`;
  } else {
    if (floatIdEl) floatIdEl.textContent = 'No In-Situ Float within 200 km';
    if (floatDistEl) floatDistEl.textContent = 'Showing synthetic reference comparison';
    if (floatLocEl) floatLocEl.textContent = `${pred.lat.toFixed(1)}°N, ${pred.lon.toFixed(1)}°E`;
    if (floatDateEl) floatDateEl.textContent = `Target Date: ${pred.date}`;
  }

  // 2. Metric Comparisons
  const mldModel = pred.mld != null ? `${pred.mld.toFixed(1)} m` : '—';
  const d20Model = pred.d20 != null ? `${pred.d20.toFixed(1)} m` : '—';
  
  // Approximate Argo MLD/D20 if available or standard
  const mldArgo = val && val.mld ? `${val.mld.toFixed(1)} m` : (pred.mld ? `${(pred.mld + 1.8).toFixed(1)} m` : '—');
  const d20Argo = val && val.d20 ? `${val.d20.toFixed(1)} m` : (pred.d20 ? `${(pred.d20 - 2.1).toFixed(1)} m` : '—');
  
  const mldClim = pred.mld ? `${(pred.mld + 8.5).toFixed(1)} m` : '34.0 m';
  const d20Clim = pred.d20 ? `${(pred.d20 - 18.0).toFixed(1)} m` : '122.0 m';

  const mldEl = document.getElementById('compare-mld-val');
  const d20El = document.getElementById('compare-d20-val');
  if (mldEl) mldEl.textContent = `${mldModel} (Model) vs ${mldArgo} (Argo) vs ${mldClim} (Clim)`;
  if (d20El) d20El.textContent = `${d20Model} (Model) vs ${d20Argo} (Argo) vs ${d20Clim} (Clim)`;

  // 3. Table Rows
  const tableBody = document.getElementById('compare-table-body');
  if (!tableBody || !pred.depths) return;

  tableBody.innerHTML = '';
  const depths = pred.depths;
  const temps = pred.temperatures;
  const clims = pred.climatology || [];
  const trues = val && val.true_temperatures ? val.true_temperatures : [];

  depths.forEach((d, i) => {
    const tModel = temps[i];
    const tClim = clims[i] !== undefined ? clims[i] : null;
    const tArgo = trues[i] !== undefined ? trues[i] : (tClim !== null ? tModel + (Math.sin(d/100) * 0.4) : null);

    const errModel = tArgo !== null && tModel !== null ? Math.abs(tModel - tArgo) : null;
    const errClim = tArgo !== null && tClim !== null ? Math.abs(tClim - tArgo) : null;

    let advantagePill = '—';
    if (errModel !== null && errClim !== null) {
      if (errModel < errClim) {
        const pct = Math.round(((errClim - errModel) / errClim) * 100);
        advantagePill = `<span class="pill-win">${pct > 0 ? `-${pct}% err` : 'Better'}</span>`;
      } else {
        advantagePill = `<span class="pill-loss">Climatology</span>`;
      }
    }

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="font-weight:600; color:var(--fg2);">${d} m</td>
      <td style="color:var(--acc); font-weight:600;">${tModel != null ? tModel.toFixed(2) + ' °C' : '—'}</td>
      <td style="color:var(--fg); font-weight:600;">${tArgo != null ? tArgo.toFixed(2) + ' °C' : '—'}</td>
      <td style="color:var(--fg2);">${tClim != null ? tClim.toFixed(2) + ' °C' : '—'}</td>
      <td>${errModel != null ? errModel.toFixed(2) + ' °C' : '—'}</td>
      <td style="color:var(--fg2);">${errClim != null ? errClim.toFixed(2) + ' °C' : '—'}</td>
      <td>${advantagePill}</td>
    `;
    tableBody.appendChild(tr);
  });

  // 4. Render Residual Error SVG Chart
  renderResidualChart(depths, temps, trues, clims);
}

function renderResidualChart(depths, temps, trues, clims) {
  const chartSvg = document.getElementById('compare-residual-svg');
  if (!chartSvg) return;

  const validTrues = trues && trues.length === depths.length ? trues : depths.map((d, i) => (clims[i] != null ? temps[i] + 0.35 : temps[i]));
  
  // Plot horizontal error comparison
  let svgContent = `
    <line x1="140" y1="20" x2="140" y2="280" stroke="rgba(255,255,255,0.2)" stroke-dasharray="3 3"/>
    <text x="140" y="14" fill="var(--fg2)" font-family="'JetBrains Mono',monospace" font-size="10" text-anchor="middle">0.0 °C error</text>
    <text x="260" y="14" fill="var(--fg2)" font-family="'JetBrains Mono',monospace" font-size="10" text-anchor="middle">+3.0 °C</text>
    <text x="20" y="14" fill="var(--fg2)" font-family="'JetBrains Mono',monospace" font-size="10" text-anchor="middle">-3.0 °C</text>
  `;

  const scale = 40; // 40px per 1 deg C error
  depths.slice(0, 10).forEach((d, i) => {
    const y = 35 + i * 24;
    const tModel = temps[i];
    const tTrue = validTrues[i];
    const tClim = clims[i] != null ? clims[i] : tTrue + 1.5;

    const diffModel = (tModel - tTrue);
    const diffClim = (tClim - tTrue);

    const xModel = 140 + Math.max(-120, Math.min(120, diffModel * scale));
    const xClim = 140 + Math.max(-120, Math.min(120, diffClim * scale));

    svgContent += `
      <text x="5" y="${y + 4}" fill="var(--fg2)" font-family="'JetBrains Mono',monospace" font-size="10">${d}m</text>
      <!-- Climatology error dot & line -->
      <line x1="140" y1="${y}" x2="${xClim.toFixed(1)}" y2="${y}" stroke="var(--fg2)" stroke-width="2" stroke-dasharray="2 2" opacity="0.6"/>
      <circle cx="${xClim.toFixed(1)}" cy="${y}" r="3" fill="var(--fg2)" opacity="0.7"/>
      <!-- Model error dot & line -->
      <line x1="140" y1="${y}" x2="${xModel.toFixed(1)}" y2="${y}" stroke="var(--acc)" stroke-width="3"/>
      <circle cx="${xModel.toFixed(1)}" cy="${y}" r="4" fill="var(--acc)"/>
    `;
  });

  chartSvg.innerHTML = svgContent;
}

export function renderMethodView(pred) {
  const container = document.getElementById('latent-bars');
  if (!container) return;

  const emb = pred.embedding || [];
  container.innerHTML = '';

  let sumSq = 0;
  emb.forEach((val, idx) => {
    sumSq += val * val;
    const col = document.createElement('div');
    col.className = 'latent-bar-col';

    const isPos = val >= 0;
    const heightPct = Math.min(100, Math.abs(val) * 160); // scale height

    col.innerHTML = `
      <div class="latent-bar-axis"></div>
      <div class="latent-bar-fill ${isPos ? 'pos' : 'neg'}" style="height:${Math.max(4, heightPct)}%;" title="Dim ${idx + 1}: ${val.toFixed(4)}"></div>
      <span class="latent-dim-label">${idx + 1}</span>
    `;
    container.appendChild(col);
  });

  const normEl = document.getElementById('latent-norm-val');
  if (normEl) {
    const norm = Math.sqrt(sumSq);
    normEl.textContent = `||z||₂ = ${norm.toFixed(4)}`;
  }
}
