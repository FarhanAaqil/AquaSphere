// Lat/lon heatmap with the coastline drawn on top. Thermal colormap for temperature layers.

import { C, THERMAL, plot } from './theme.js';
import { nioLand } from '../geo.js';

let landTrace = null;
async function coastline() {
  if (landTrace) return landTrace;
  const rings = await nioLand();
  const x = [];
  const y = [];
  for (const r of rings) {
    for (const [lo, la] of r) { x.push(lo); y.push(la); }
    x.push(null); y.push(null);
  }
  landTrace = { x, y, mode: 'lines', fill: 'toself', fillcolor: '#0d2238', line: { color: 'rgba(159,179,200,0.6)', width: 0.8 }, hoverinfo: 'skip', showlegend: false };
  return landTrace;
}

/**
 * @param {{lats:number[], lons:number[], z:(number|null)[][], unit:string, label:string, scale?:'thermal'|'width'|'depth'}} d
 */
export async function renderHeatmap(el, d, ctx, name) {
  const colorscale = d.scale === 'width'
    ? [[0, '#0b1f3a'], [0.5, '#0e7490'], [1, '#67e8f9']]
    : d.scale === 'depth'
      ? [[0, '#fbbf24'], [0.5, '#14b8a6'], [1, '#4f46e5']] // shallow (warm) → deep (indigo)
      : THERMAL;
  const heat = {
    type: 'heatmap', x: d.lons, y: d.lats, z: d.z, colorscale, zsmooth: 'best', hoverongaps: false,
    colorbar: { title: { text: d.unit, side: 'right', font: { color: C.muted } }, thickness: 10, outlinewidth: 0, tickfont: { family: 'JetBrains Mono', color: C.muted, size: 10 } },
    hovertemplate: `%{y:.1f}°N %{x:.1f}°E<br>${d.label}: %{z:.2f} ${d.unit}<extra></extra>`,
  };
  await plot(el, [heat, await coastline()], {
    xaxis: { range: [44, 106], ticksuffix: '°E', showgrid: false, constrain: 'domain' },
    yaxis: { range: [4, 31], ticksuffix: '°N', showgrid: false },
    margin: { l: 48, r: 8, t: 8, b: 32 },
    showlegend: false,
  }, ctx, name);
}
