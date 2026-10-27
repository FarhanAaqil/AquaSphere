/**
 * AquaSphere Workbench Depth Profile Renderer
 * Depth axis stretched above 300 m matching reference coordinate system.
 */

const X_MIN = 60;
const X_MAX = 350;
const T_MIN = 4.0;
const T_MAX = 32.0;

export function depthToY(d) {
  if (d <= 300) {
    return 20 + d * 0.6;
  }
  return 200 + (d - 300) * 0.1714;
}

export function tempToX(t) {
  const clamped = Math.max(T_MIN, Math.min(T_MAX, t));
  return X_MIN + ((clamped - T_MIN) / (T_MAX - T_MIN)) * (X_MAX - X_MIN);
}

export function renderProfile(predData, valData = null, options = {}) {
  const showPred = options.showPred !== false;
  const showUnc = options.showUnc !== false;
  const showArgo = options.showArgo !== false;

  const uncEl = document.getElementById('prof-unc-band');
  const predEl = document.getElementById('prof-pred-line');
  const climEl = document.getElementById('prof-clim-line');
  const argoEl = document.getElementById('prof-argo-points');

  if (!predData || !predData.depths) {
    return;
  }

  const depths = predData.depths;
  const temps = predData.temperatures;
  const lower = predData.interval_lower || [];
  const upper = predData.interval_upper || [];

  // 1. Predicted line
  if (predEl) {
    if (showPred && temps && temps.length) {
      const pts = depths.map((d, i) => `${tempToX(temps[i]).toFixed(1)},${depthToY(d).toFixed(1)}`).join(' ');
      predEl.setAttribute('points', pts);
      predEl.style.display = '';
    } else {
      predEl.style.display = 'none';
    }
  }

  // 2. Conformal uncertainty band
  if (uncEl) {
    if (showUnc && upper.length && lower.length) {
      const topPts = depths.map((d, i) => `${tempToX(upper[i]).toFixed(1)},${depthToY(d).toFixed(1)}`);
      const btmPts = depths.slice().reverse().map((d, idx) => {
        const i = depths.length - 1 - idx;
        return `${tempToX(lower[i]).toFixed(1)},${depthToY(d).toFixed(1)}`;
      });
      uncEl.setAttribute('points', `${topPts.join(' ')} ${btmPts.join(' ')}`);
      uncEl.style.display = '';
    } else {
      uncEl.style.display = 'none';
    }
  }

  // 3. Climatology line (if available from API)
  if (climEl) {
    if (predData.climatology && predData.climatology.length) {
      const pts = depths.map((d, i) => `${tempToX(predData.climatology[i]).toFixed(1)},${depthToY(d).toFixed(1)}`).join(' ');
      climEl.setAttribute('points', pts);
      climEl.style.display = '';
    } else {
      climEl.style.display = 'none';
    }
  }

  // 4. Held-out Argo validation profile points
  if (argoEl) {
    argoEl.innerHTML = '';
    if (showArgo && valData && valData.depths && valData.true_temperatures) {
      valData.depths.forEach((d, i) => {
        const t = valData.true_temperatures[i];
        if (t !== undefined && t !== null && d <= 1000) {
          const cx = tempToX(t).toFixed(1);
          const cy = depthToY(d).toFixed(1);
          const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          c.setAttribute('cx', cx);
          c.setAttribute('cy', cy);
          c.setAttribute('r', '3.5');
          c.innerHTML = `<title>Argo Obs: ${t.toFixed(2)}°C at ${d}m</title>`;
          argoEl.appendChild(c);
        }
      });
      argoEl.style.display = '';
    }
  }

  // 5. Update stat tiles
  updateStatTiles(predData);
}

export function updateStatTiles(pred) {
  const d20El = document.getElementById('tile-d20');
  const mldEl = document.getElementById('tile-mld');
  const ohcEl = document.getElementById('tile-ohc');
  const appEl = document.getElementById('tile-app');

  if (d20El) {
    d20El.innerHTML = pred.d20 != null ? `${pred.d20.toFixed(1)} <span style="font-size:12px;color:var(--fg2);">m</span>` : '—';
  }
  if (mldEl) {
    mldEl.innerHTML = pred.mld != null ? `${pred.mld.toFixed(1)} <span style="font-size:12px;color:var(--fg2);">m</span>` : '—';
  }
  if (ohcEl) {
    ohcEl.textContent = pred.heat_content != null ? `${pred.heat_content.toFixed(2)} GJ/m²` : '—';
  }
  if (appEl) {
    const isApp = pred.in_training_set !== false;
    appEl.textContent = isApp ? 'IN DOMAIN' : 'OUTSIDE DOMAIN';
    appEl.style.color = isApp ? 'var(--acc)' : 'var(--warm)';
  }
}
