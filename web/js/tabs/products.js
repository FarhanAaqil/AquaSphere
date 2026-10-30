// Ocean products from /v2/grid: cyclone heat potential, isotherm depths, temperature and
// anomaly at a depth, interval width and the applicability domain. Compare mode subtracts a
// second date cell by cell; cells missing on either date stay empty.

import { state } from '../state.js';
import * as api from '../api.js';
import { sourceSummary, tag } from '../ui/badges.js';
import { loading, errorState } from '../ui/loaders.js';
import { renderHeatmap } from '../charts/heatmap.js';
import { card, h, $, onDate, onState, fmt, reveal } from './_util.js';

const LAYERS = {
  tchp: { label: 'Cyclone heat potential (TCHP)', unit: 'kJ/cm²', scale: 'thermal', depthless: true, note: 'Heat above the 26 °C isotherm; values above ~50 kJ/cm² favour cyclone intensification.' },
  d26: { label: 'Depth of the 26 °C isotherm (D26)', unit: 'm', scale: 'depth', depthless: true, note: '0 where the surface is cooler than 26 °C.' },
  temperature: { label: 'Temperature', unit: '°C', scale: 'thermal' },
  anomaly: { label: 'Anomaly vs training-years climatology', unit: '°C', scale: 'diverging', note: 'Prediction minus the 2015–2022 monthly climatology at this depth.' },
  interval_width: { label: '90% interval width', unit: '°C', scale: 'width', note: 'Wider = less certain. Mondrian conformal by region and season when the v2 model is served.' },
  d20: { label: 'Depth of the 20 °C isotherm (D20)', unit: 'm', scale: 'depth', depthless: true },
  mld: { label: 'Mixed layer depth', unit: 'm', scale: 'depth', depthless: true },
  di: { label: 'Dissimilarity index (applicability)', unit: 'DI', scale: 'width', depthless: true, note: 'Distance of the embedding from the training data; above the threshold the cell is outside the applicability domain.' },
};
const DEPTHS = [0, 50, 100, 150, 200, 300, 500];
const STEPS = [1.5, 2, 2.5];

function toMatrix(cells, key) {
  const lats = [...new Set(cells.map((c) => c.lat))].sort((a, b) => a - b);
  const lons = [...new Set(cells.map((c) => c.lon))].sort((a, b) => a - b);
  const z = lats.map(() => lons.map(() => null));
  const at = new Map(cells.map((c) => [`${c.lat}|${c.lon}`, c]));
  lats.forEach((la, j) => lons.forEach((lo, i) => {
    const c = at.get(`${la}|${lo}`);
    if (c && c[key] != null) z[j][i] = c[key];
  }));
  return { lats, lons, z, at };
}

export default {
  async mount(root, ctx) {
    root.innerHTML = `
      <div class="page__intro"><h2>Ocean products</h2>
        <p>Maps derived from predicted profiles for the selected date and mode: tropical cyclone heat potential, isotherm depths,
        temperature and anomaly at a depth, uncertainty and the applicability domain. Cells without a surface observation are left blank.</p></div>
      <div class="grid grid--main-side" data-ref="row"></div>`;
    const map = card({ title: 'Map', sub: '—' });
    const side = card({ title: 'Layer', sub: 'What to map', bodyCls: 'tool-stack' });
    map.body.innerHTML = '<div class="chart" style="min-height:420px" data-ref="chart"></div><p class="note" data-ref="note"></p>';
    side.body.innerHTML = `
      <label class="field"><span class="field__label">Layer</span>
        <select class="input" data-ref="layer">${Object.entries(LAYERS).map(([k, l]) => `<option value="${k}">${l.label}</option>`).join('')}</select></label>
      <label class="field"><span class="field__label">Depth</span>
        <select class="input input--mono" data-ref="depth">${DEPTHS.map((d) => `<option value="${d}" ${d === 100 ? 'selected' : ''}>${d} m</option>`).join('')}</select></label>
      <label class="field"><span class="field__label">Grid step</span>
        <select class="input input--mono" data-ref="step">${STEPS.map((s) => `<option value="${s}" ${s === 2 ? 'selected' : ''}>${s}°</option>`).join('')}</select></label>
      <label class="field field--inline"><input type="checkbox" data-ref="compare"> <span>Compare with another date</span></label>
      <label class="field" data-ref="date2-wrap" hidden><span class="field__label">Second date (subtracted)</span>
        <select class="input input--mono" data-ref="date2"></select></label>
      <div class="stat stat--sm" data-ref="summary"></div>
      <div class="btn-row">
        <a class="btn btn--ghost btn--sm" data-ref="csv" download>Export grid · CSV</a>
        <a class="btn btn--ghost btn--sm" data-ref="nc" download>NetCDF</a>
      </div>
      <p class="card__foot">Exports carry the full 15-depth profiles with intervals, the model version, git commit and per-cell data source.</p>`;
    $(root, '[data-ref="row"]').append(map.card, side.card);

    const chart = $(map.body, '[data-ref="chart"]');
    const note = $(map.body, '[data-ref="note"]');
    const ui = (k) => $(side.body, `[data-ref="${k}"]`);
    const dates = (state.meta?.available_dates || []).slice();
    ui('date2').innerHTML = dates.map((d) => `<option value="${d}">${d}</option>`).join('');

    let req = 0;
    async function draw() {
      const date = state.date;
      if (!date) return errorState(chart, { kind: 'offline' });
      const layer = ui('layer').value;
      const L = LAYERS[layer];
      const depth = +ui('depth').value;
      const step = +ui('step').value;
      const compare = ui('compare').checked;
      const date2 = ui('date2').value;
      ui('depth').disabled = Boolean(L.depthless);
      ui('date2-wrap').hidden = !compare;
      ui('csv').href = api.exportUrl('grid', { date, step, format: 'csv' });
      ui('nc').href = api.exportUrl('grid', { date, step, format: 'netcdf' });

      const my = ++req;
      loading(chart, `Predicting ${compare ? 'two grids' : 'the grid'} at ${step}° for ${date}…`);
      try {
        const [a, b] = await Promise.all([
          api.gridV2({ date, depth, step }, { signal: ctx.signal }),
          compare && date2 ? api.gridV2({ date: date2, depth, step }, { signal: ctx.signal }) : null,
        ]);
        if (my !== req) return;
        const A = toMatrix(a.cells, layer);
        let z = A.z;
        let scale = L.scale;
        let label = L.label;
        if (b) {
          const B = toMatrix(b.cells, layer);
          z = A.lats.map((la, j) => A.lons.map((lo, i) => {
            const vb = B.at.get(`${la}|${lo}`)?.[layer];
            return A.z[j][i] == null || vb == null ? null : A.z[j][i] - vb;
          }));
          scale = 'diverging';
          label = `${L.label}: ${date} − ${date2}`;
        }
        const where = L.depthless ? '' : ` at ${depth} m`;
        map.card.querySelector('.card__sub').textContent = `${label}${where} · ${a.mode} mode · ${a.count} cells${a.missing ? ` · ${a.missing} without data` : ''}`;
        map.meta.replaceChildren(
          ...sourceSummary(a.cells.map((c) => c.data_source)),
          tag(`model ${a.model_version}`, 'muted'),
          ...(b ? [tag('Difference', 'muted')] : []),
        );
        chart.replaceChildren();
        await renderHeatmap(chart, { lats: A.lats, lons: A.lons, z, unit: L.unit, label, scale }, ctx, `aquasphere-${layer}-${date}`);
        const vals = z.flat().filter((v) => v != null);
        const outside = a.cells.filter((c) => c.in_domain === false).length;
        ui('summary').replaceChildren(h(`<span class="stat__label">Across mapped cells</span>`), Object.assign(document.createElement('span'), {
          className: 'stat__note',
          textContent: vals.length
            ? `min ${fmt(Math.min(...vals), 1)} · median ${fmt(vals.sort((x, y) => x - y)[Math.floor(vals.length / 2)], 1)} · max ${fmt(Math.max(...vals), 1)} ${L.unit}`
            : 'No values',
        }));
        note.textContent = [
          L.note,
          a.cells.some((c) => c.di != null) ? `${outside} of ${a.count} cells are outside the applicability domain.` : 'This model does not report a dissimilarity index.',
        ].filter(Boolean).join(' ');
      } catch (err) {
        if (ctx.signal.aborted || my !== req) return;
        map.meta.replaceChildren();
        errorState(chart, err, { retry: draw });
        note.textContent = '';
      }
    }

    for (const k of ['layer', 'depth', 'step', 'compare', 'date2']) ui(k).addEventListener('change', draw);
    onDate(ctx, () => draw());
    onState(ctx, ['mode', 'demo'], () => draw());
    reveal(root, ctx, '.grid > .card');
  },
};
