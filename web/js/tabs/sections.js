// Sections: a depth x distance transect between two map clicks, and a depth x time
// (Hovmoller) view at one point over the dates in the local store. Points or dates without a
// surface observation are left out and listed, never interpolated.

import { state, set } from '../state.js';
import * as api from '../api.js';
import { fmtLat, fmtLon, nioLand, onLand } from '../geo.js';
import { createMap } from '../ui/map.js';
import { sourceSummary, tag } from '../ui/badges.js';
import { loading, errorState, empty } from '../ui/loaders.js';
import { toast } from '../ui/toasts.js';
import { plot, C, THERMAL, T_RANGE } from '../charts/theme.js';
import { card, $, onDate, onState, reveal } from './_util.js';

const SPANS = { 90: '3 months', 182: '6 months', 365: '1 year', 730: '2 years' };

async function section(el, { x, depths, z, d20, xTitle, name }, ctx) {
  await plot(el, [
    {
      type: 'heatmap', x, y: depths, z: depths.map((_, k) => z.map((row) => row[k])),
      colorscale: THERMAL, zmin: T_RANGE[0], zmax: T_RANGE[1], zsmooth: 'best',
      colorbar: { title: { text: '°C', side: 'right' }, thickness: 10, outlinewidth: 0 },
      hovertemplate: `%{x}<br>%{y} m: %{z:.2f} °C<extra></extra>`,
    },
    { x, y: d20, mode: 'lines', name: 'D20', line: { color: C.glow, width: 2, dash: 'dot' }, connectgaps: false, hovertemplate: 'D20 %{y:.0f} m<extra></extra>' },
  ], {
    xaxis: { title: { text: xTitle } },
    yaxis: { title: { text: 'Depth (m)' }, autorange: 'reversed', range: [500, 0] },
    margin: { l: 56, r: 12, t: 8, b: 48 },
    legend: { orientation: 'h', y: 1.08 },
  }, ctx, name);
}

export default {
  async mount(root, ctx) {
    root.innerHTML = `
      <div class="page__intro"><h2>Sections</h2>
        <p>Cut through the reconstructed ocean. A <strong>transect</strong> joins two points along the great circle and shows
        temperature against depth and distance. The <strong>depth–time</strong> view follows one point through the dates held in
        the local store. Both use the mode chosen in the top bar.</p></div>
      <div class="grid grid--side" data-ref="t"></div>
      <div class="grid grid--side" data-ref="h"></div>`;
    await nioLand();

    // ── Transect ──
    const tPick = card({ title: 'Transect', sub: 'Click a start point, then an end point', bodyCls: 'tool-stack' });
    const tPlot = card({ title: 'Depth × distance', sub: '—' });
    tPick.body.innerHTML = `<div data-ref="map"></div>
      <label class="field"><span class="field__label">Points along the line</span>
        <select class="input input--mono" data-ref="n">${[20, 40, 60].map((n) => `<option ${n === 40 ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
      <p class="card__foot" data-ref="ends">No line yet.</p>`;
    tPlot.body.innerHTML = '<div class="chart chart--tall" data-ref="chart"></div><p class="note" data-ref="note"></p>';
    tPlot.card.dataset.ref = 'transect';
    $(root, '[data-ref="t"]').append(tPick.card, tPlot.card);
    const tChart = $(tPlot.body, '[data-ref="chart"]');
    empty(tChart, 'Pick two points on the map', 'The section is computed for the date in the top bar.');

    let ends = [];
    const tMap = await createMap($(tPick.body, '[data-ref="map"]'), {
      label: 'Click two points to draw a transect',
      onPick: ({ lat, lon, inside }) => {
        if (!inside) return toast('Pick points inside the 5–30°N, 45–105°E domain.', { kind: 'warn' });
        ends = ends.length >= 2 ? [{ lat, lon }] : [...ends, { lat, lon }];
        tMap.setPoints(ends.map((p, i) => ({ id: i, ...p, color: i ? C.coral : C.cyan, r: 0.6, label: i ? 'End' : 'Start' })));
        tMap.setLine(ends[0], ends[1]);
        $(tPick.body, '[data-ref="ends"]').textContent = ends.map((p, i) => `${i ? 'End' : 'Start'} ${fmtLat(p.lat)} ${fmtLon(p.lon)}`).join(' → ');
        if (ends.length === 2) drawTransect();
      },
    });

    let tReq = 0;
    async function drawTransect() {
      if (ends.length < 2) return;
      if (!state.date) return errorState(tChart, { kind: 'offline' });
      const [a, b] = ends;
      const my = ++tReq;
      loading(tChart, 'Predicting profiles along the line…');
      try {
        const s = await api.transect({ lat1: a.lat, lon1: a.lon, lat2: b.lat, lon2: b.lon, date: state.date, n: $(tPick.body, '[data-ref="n"]').value }, { signal: ctx.signal });
        if (my !== tReq) return;
        tPlot.card.querySelector('.card__sub').textContent = `${state.date} · ${s.mode} mode · ${s.axis.length} profiles over ${Math.round(s.axis.at(-1) - s.axis[0])} km`;
        tPlot.meta.replaceChildren(...sourceSummary(s.data_source), tag(`model ${s.model_version}`, 'muted'));
        tChart.replaceChildren();
        await section(tChart, { x: s.axis, depths: s.depths, z: s.temperature, d20: s.d20, xTitle: 'Distance from start (km)', name: `aquasphere-transect-${state.date}` }, ctx);
        $(tPlot.body, '[data-ref="note"]').textContent = s.skipped.length
          ? `${s.skipped.length} point(s) had no surface observation (land or a data gap) and are left out: ${s.skipped.slice(0, 6).join(', ')}${s.skipped.length > 6 ? '…' : ''}.`
          : 'Every point along the line had a surface observation.';
      } catch (err) {
        if (ctx.signal.aborted || my !== tReq) return;
        tPlot.meta.replaceChildren();
        errorState(tChart, err, { retry: drawTransect });
      }
    }
    $(tPick.body, '[data-ref="n"]').addEventListener('change', drawTransect);

    // ── Depth-time ──
    const hPick = card({ title: 'Depth–time at a point', sub: 'Click the map to choose the point', bodyCls: 'tool-stack' });
    const hPlot = card({ title: 'Depth × time', sub: '—' });
    hPick.body.innerHTML = `<div data-ref="map"></div>
      <label class="field"><span class="field__label">Window ending at the selected date</span>
        <select class="input" data-ref="span">${Object.entries(SPANS).map(([d, l]) => `<option value="${d}" ${d === '365' ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      <label class="field"><span class="field__label">Every</span>
        <select class="input input--mono" data-ref="every">${[3, 7, 14, 30].map((d) => `<option value="${d}" ${d === 7 ? 'selected' : ''}>${d} days</option>`).join('')}</select></label>
      <div class="btn-row"><a class="btn btn--ghost btn--sm" data-ref="csv" download>Profile · CSV</a><a class="btn btn--ghost btn--sm" data-ref="nc" download>NetCDF</a></div>
      <p class="card__foot">Exports the profile at this point for the selected date, with its interval and provenance.</p>`;
    hPlot.body.innerHTML = '<div class="chart chart--tall" data-ref="chart"></div><p class="note" data-ref="note"></p>';
    $(root, '[data-ref="h"]').append(hPick.card, hPlot.card);
    const hChart = $(hPlot.body, '[data-ref="chart"]');
    const hMap = await createMap($(hPick.body, '[data-ref="map"]'), {
      label: 'Click to choose the point for the depth-time view',
      onPick: ({ lat, lon, inside }) => {
        if (!inside) return toast('Pick a point inside the study domain.', { kind: 'warn' });
        if (onLand(lat, lon)) return toast('That point is on land.', { kind: 'warn' });
        set({ point: { lat, lon } });
        drawSeries();
      },
    });

    let hReq = 0;
    async function drawSeries() {
      const { lat, lon } = state.point;
      hMap.setTarget(lat, lon);
      const date = state.date;
      if (!date) return errorState(hChart, { kind: 'offline' });
      $(hPick.body, '[data-ref="csv"]').href = api.exportUrl('profile', { lat, lon, date, format: 'csv' });
      $(hPick.body, '[data-ref="nc"]').href = api.exportUrl('profile', { lat, lon, date, format: 'netcdf' });
      const span = +$(hPick.body, '[data-ref="span"]').value;
      const start = new Date(Date.parse(`${date}T00:00:00Z`) - span * 864e5).toISOString().slice(0, 10);
      const my = ++hReq;
      loading(hChart, `Predicting ${fmtLat(lat)} ${fmtLon(lon)} from ${start} to ${date}…`);
      try {
        const s = await api.timeseries({ lat, lon, start, end: date, step_days: $(hPick.body, '[data-ref="every"]').value }, { signal: ctx.signal });
        if (my !== hReq) return;
        hPlot.card.querySelector('.card__sub').textContent = `${fmtLat(lat)} ${fmtLon(lon)} · ${s.axis.length} dates · ${s.mode} mode`;
        hPlot.meta.replaceChildren(...sourceSummary(s.data_source), tag(`model ${s.model_version}`, 'muted'));
        hChart.replaceChildren();
        await section(hChart, { x: s.axis, depths: s.depths, z: s.temperature, d20: s.d20, xTitle: 'Date', name: `aquasphere-hovmoller-${lat}-${lon}` }, ctx);
        $(hPlot.body, '[data-ref="note"]').textContent = s.skipped.length
          ? `${s.skipped.length} stored date(s) had no observation at this point and are left out.`
          : 'Dates come from the local surface store only; no live fetches are made for a series.';
      } catch (err) {
        if (ctx.signal.aborted || my !== hReq) return;
        hPlot.meta.replaceChildren();
        errorState(hChart, err, { retry: drawSeries });
      }
    }
    for (const k of ['span', 'every']) $(hPick.body, `[data-ref="${k}"]`).addEventListener('change', drawSeries);

    onDate(ctx, () => { drawTransect(); drawSeries(); });
    onState(ctx, ['mode', 'demo'], () => { drawTransect(); drawSeries(); });
    reveal(root, ctx, '.grid > .card');
  },
};
