// Vertical temperature profile: prediction, 90% band, climatology, optional observations,
// D20 / MLD markers. Depth runs on a square-root axis so the upper 200 m is readable.

import { C, plot, loadPlotly } from './theme.js';
import { state } from '../state.js';

const TICKS = [0, 20, 50, 100, 150, 200, 300, 500, 700, 1000];
const s = (d) => Math.sqrt(d);

function depthAxis() {
  return {
    title: { text: 'Depth (m)' },
    autorange: 'reversed',
    tickvals: TICKS.map(s),
    ticktext: TICKS.map((d) => `${d}`),
    zeroline: false,
  };
}

function hline(depth, color, label, dash) {
  return {
    shape: { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: s(depth), y1: s(depth), line: { color, width: 1.2, dash } },
    annotation: { xref: 'paper', x: 1, y: s(depth), xanchor: 'right', yanchor: 'bottom', text: label, showarrow: false, font: { family: 'JetBrains Mono', size: 11, color } },
  };
}

/**
 * @param {HTMLElement} el
 * @param {{depths:number[], mean:number[], lower?:number[], upper?:number[], bandLabel?:string,
 *          climatology?:number[]|null, observed?:(number|null)[], d20?:number|null, mld?:number|null}} p
 */
export async function renderProfile(el, p, ctx, { name = 'aquasphere-profile', meanLabel = 'Prediction' } = {}) {
  const y = p.depths.map(s);
  const custom = p.depths;
  const traces = [];

  if (p.lower && p.upper) {
    traces.push({
      x: [...p.upper, ...[...p.lower].reverse()],
      y: [...y, ...[...y].reverse()],
      fill: 'toself', fillcolor: C.band, line: { width: 0 }, mode: 'lines',
      name: p.bandLabel || '90% conformal interval', hoverinfo: 'skip',
    });
  }
  if (p.climatology) {
    traces.push({
      x: p.climatology, y, customdata: custom, mode: 'lines', name: 'Monthly climatology',
      line: { color: C.muted, width: 1.5, dash: 'dash' },
      hovertemplate: 'Climatology %{x:.2f} °C at %{customdata} m<extra></extra>',
    });
  }
  if (p.observed) {
    traces.push({
      x: p.observed, y, customdata: custom, mode: 'lines+markers', name: 'Argo observed (held out)', connectgaps: false,
      line: { color: C.coral, width: 2 }, marker: { size: 7, color: C.coral, line: { color: '#020617', width: 1 } },
      hovertemplate: 'Observed %{x:.2f} °C at %{customdata} m<extra></extra>',
    });
  }
  const lower = p.lower;
  const upper = p.upper;
  traces.push({
    x: p.mean, y, customdata: p.depths.map((d, i) => [d, lower?.[i], upper?.[i]]), mode: 'lines+markers', name: meanLabel,
    line: { color: C.cyan, width: 3, shape: 'spline', smoothing: 0.4 },
    marker: { size: 6, color: C.glow, line: { color: '#020617', width: 1 } },
    hovertemplate: lower
      ? `${meanLabel} %{x:.2f} °C at %{customdata[0]} m<br>90%% [%{customdata[1]:.2f}, %{customdata[2]:.2f}]<extra></extra>`.replace('%%', '%')
      : `${meanLabel} %{x:.2f} °C at %{customdata[0]} m<extra></extra>`,
  });

  const marks = [];
  if (p.d20 != null) marks.push(hline(p.d20, C.teal, `D20 ${p.d20.toFixed(0)} m`, 'dot'));
  if (p.mld != null) marks.push(hline(p.mld, C.amber, `MLD ${p.mld.toFixed(0)} m`, 'dashdot'));

  const lay = {
    xaxis: { title: { text: 'Temperature (°C)' }, side: 'top', ticksuffix: '°' },
    yaxis: depthAxis(),
    margin: { l: 56, r: 16, t: 44, b: 20 },
    legend: { orientation: 'h', x: 0, y: -0.04, yanchor: 'top' },
    shapes: marks.map((m) => m.shape),
    annotations: marks.map((m) => m.annotation),
    hovermode: 'closest',
  };

  // Animate: the band opens out from the mean line.
  const animate = !state.reduced && !state.perf && p.lower && !el.dataset.drawn;
  if (animate) {
    const collapsed = traces.map((t, i) => (i === 0 ? { ...t, x: [...p.mean, ...[...p.mean].reverse()] } : t));
    await plot(el, collapsed, lay, ctx, name);
    const Plotly = await loadPlotly();
    if (ctx?.signal.aborted) return;
    el.dataset.drawn = '1';
    await Plotly.animate(el, { data: [{ x: traces[0].x }], traces: [0] }, { transition: { duration: 650, easing: 'cubic-out' }, frame: { duration: 650, redraw: false } });
  } else {
    await plot(el, traces, lay, ctx, name);
    el.dataset.drawn = '1';
  }
}
