import { state } from '../state.js';
import * as api from '../api.js';
import { loadGrid } from '../gridData.js';
import { badge, sourceSummary } from '../ui/badges.js';
import { loading, errorState, pending } from '../ui/loaders.js';
import { plot, C } from '../charts/theme.js';
import { renderHeatmap } from '../charts/heatmap.js';
import { card, $, h, onDate, reveal } from './_util.js';

const WIDTH_DEPTHS = [0, 50, 100, 150, 300, 1000];

async function optional(name) {
  try { return await api.results(name); } catch { return null; }
}

async function coverageCard(host, ctx) {
  const { card: c, body, meta } = card({ title: 'Empirical coverage of the 90% interval', sub: 'Per ablation run, mean ± std over seeds. Dashed line = nominal 90%.' });
  host.append(c);
  body.innerHTML = '<div class="chart chart--short"></div><p class="note" hidden></p>';
  const ab = await optional('ablation');
  if (!ab) return pending(body, { title: 'Ablation results missing', needs: 'web/data/ablation.json' });
  meta.append(badge('results'));
  await plot(body.firstChild, [{
    type: 'bar', x: ab.results.map((r) => r.run), y: ab.results.map((r) => r.coverage_mean * 100),
    error_y: { type: 'data', array: ab.results.map((r) => r.coverage_std * 100), color: C.glow },
    marker: { color: C.teal }, hovertemplate: '%{x}: %{y:.1f}%<extra></extra>',
  }], {
    yaxis: { title: { text: 'Coverage (%)' }, range: [80, 100] },
    xaxis: { tickangle: -20 },
    shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 90, y1: 90, line: { color: C.amber, dash: 'dash', width: 1.5 } }],
    margin: { l: 52, r: 12, t: 8, b: 70 }, showlegend: false,
  }, ctx, 'aquasphere-coverage');
  const spread = Math.max(...ab.results.map((r) => r.coverage_mean)) - Math.min(...ab.results.map((r) => r.coverage_mean));
  if (spread < 1e-6) {
    const n = body.querySelector('.note');
    n.hidden = false;
    n.className = 'note note--warn';
    n.textContent = `Coverage is identical across every run (${(ab.results[0].coverage_mean * 100).toFixed(1)}%, std ≈ 0) on a validation set of ${ab.n_val} profiles. That pattern suggests a fixed calibration scale rather than per-run calibration; read it as indicative only.`;
  }
}

async function reliabilityCard(host, ctx) {
  const { card: c, body, meta } = card({ title: 'Reliability diagram', sub: 'Nominal vs empirical coverage across interval levels, held-out profiles only' });
  host.append(c);
  body.innerHTML = '<div class="chart chart--short"></div>';
  const rel = await optional('reliability');
  if (!rel) {
    meta.append(badge('pending'));
    return pending(body, { title: 'Pending', detail: 'Needs coverage measured at several nominal levels on held-out profiles.', needs: 'web/data/reliability.json → { "nominal": [0.5, …, 0.95], "empirical": [...], "n": int }' });
  }
  meta.append(badge('results'));
  await plot(body.firstChild, [
    { x: [0, 1], y: [0, 1], mode: 'lines', line: { color: C.faint, dash: 'dash' }, name: 'Perfect calibration', hoverinfo: 'skip' },
    { x: rel.nominal, y: rel.empirical, mode: 'lines+markers', line: { color: C.cyan, width: 3 }, name: 'AquaSphere', hovertemplate: 'nominal %{x:.2f} → empirical %{y:.2f}<extra></extra>' },
  ], { xaxis: { title: { text: 'Nominal coverage' }, range: [0, 1] }, yaxis: { title: { text: 'Empirical coverage' }, range: [0, 1] } }, ctx, 'aquasphere-reliability');
}

async function regionSeasonCard(host, ctx) {
  const { card: c, body, meta } = card({ title: 'Coverage by region and monsoon season', sub: 'Arabian Sea vs Bay of Bengal · SW monsoon, NE monsoon, inter-monsoon' });
  host.append(c);
  body.innerHTML = '<div class="chart chart--short"></div>';
  const data = await optional('coverage_regions');
  if (!data) {
    meta.append(badge('pending'));
    return pending(body, { title: 'Pending', detail: 'The evaluation has not been broken down by basin and season yet.', needs: 'web/data/coverage_regions.json → { "rows": [{ "region", "season", "coverage", "n" }] }' });
  }
  meta.append(badge('results'));
  const regions = [...new Set(data.rows.map((r) => r.region))];
  await plot(body.firstChild, regions.map((rg, i) => {
    const rows = data.rows.filter((r) => r.region === rg);
    return { type: 'bar', name: rg, x: rows.map((r) => r.season), y: rows.map((r) => r.coverage * 100), marker: { color: [C.coral, C.indigo, C.teal][i % 3] }, customdata: rows.map((r) => r.n), hovertemplate: `${rg} · %{x}: %{y:.1f}% (n=%{customdata})<extra></extra>` };
  }), { barmode: 'group', yaxis: { title: { text: 'Coverage (%)' } }, shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 90, y1: 90, line: { color: C.amber, dash: 'dash' } }] }, ctx, 'aquasphere-coverage-regions');
}

async function dissimilarityCard(host) {
  const { card: c, body, meta } = card({ title: 'Applicability domain · dissimilarity index', sub: 'Distance of each cell\'s embedding from the training distribution' });
  host.append(c);
  meta.append(badge('pending'));
  pending(body, {
    title: 'Pending',
    detail: 'The API does not expose a dissimilarity index yet, so outside-domain areas cannot be mapped honestly. The interval-width map on this page is the closest real signal available today.',
    needs: 'Needs a per-point DI (e.g. kNN distance in embedding space vs training set) from /predict or /grid',
  });
}

export default {
  async mount(root, ctx) {
    root.innerHTML = `
      <div class="page__intro"><h2>Uncertainty &amp; applicability</h2>
        <p>How trustworthy are the intervals, and where is the model working outside what it has seen? Calibration results come
        from the evaluation files; interval widths are computed from live predictions for the selected date.</p></div>
      <div class="grid grid--2" data-ref="a"></div>
      <div class="grid grid--main-side" data-ref="b"></div>
      <div class="grid grid--2" data-ref="c"></div>`;
    const a = $(root, '[data-ref="a"]');
    const b = $(root, '[data-ref="b"]');
    const cRow = $(root, '[data-ref="c"]');

    // Live: interval width across the grid
    const widthMap = card({ title: 'Mean 90% interval width', sub: '—' });
    const widthProfile = card({ title: 'Interval width by depth, whole domain', sub: 'Median and 10–90th percentile across ocean cells' });
    widthMap.body.innerHTML = `<div class="depth-pick" role="radiogroup" aria-label="Depth">${WIDTH_DEPTHS.map((d) => `<button class="chip" role="radio" aria-checked="${d === 100}" data-depth="${d}">${d} m</button>`).join('')}</div><div class="chart" style="min-height:300px"></div>`;
    widthProfile.body.innerHTML = '<div class="chart"></div>';
    b.append(widthMap.card, widthProfile.card);

    await Promise.all([coverageCard(a, ctx), reliabilityCard(a, ctx)]);
    await Promise.all([regionSeasonCard(cRow, ctx), dissimilarityCard(cRow)]);

    let depth = 100;
    let grid = null;
    const mapChart = widthMap.body.querySelector('.chart');
    const profChart = widthProfile.body.firstChild;
    const drawMap = async () => {
      if (!grid) return;
      const di = grid.depths.indexOf(depth);
      const z = grid.upper[di].map((row, j) => row.map((u, i) => (u == null ? null : u - grid.lower[di][j][i])));
      widthMap.card.querySelector('.card__sub').textContent = `${depth} m · ${grid.date} · wider = less certain`;
      await renderHeatmap(mapChart, { lats: grid.lats, lons: grid.lons, z, unit: '°C', label: '90% width', scale: 'width' }, ctx, `aquasphere-width-${depth}`);
    };
    widthMap.body.querySelector('.depth-pick').addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if (!btn) return;
      depth = +btn.dataset.depth;
      for (const x of btn.parentElement.children) x.setAttribute('aria-checked', String(x === btn));
      drawMap();
    });

    onDate(ctx, async (date) => {
      grid = null;
      if (!date) { errorState(mapChart, { kind: 'offline' }); errorState(profChart, { kind: 'offline' }); return; }
      loading(mapChart, `Loading grid predictions for ${date}…`);
      loading(profChart, 'Waiting for grid…');
      try {
        const g = await loadGrid(date, { signal: ctx.signal });
        if (state.date !== date) return;
        grid = g;
        const badges = sourceSummary(g.sources);
        widthMap.meta.replaceChildren(...badges);
        widthProfile.meta.replaceChildren(...badges.map((n) => n.cloneNode(true)));
        mapChart.replaceChildren();
        profChart.replaceChildren();
        await drawMap();
        const q = (arr, p) => { const s = [...arr].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
        const stats = g.depths.map((d, di) => {
          const w = [];
          g.upper[di].forEach((row, j) => row.forEach((u, i) => { if (u != null) w.push(u - g.lower[di][j][i]); }));
          return [q(w, 0.1), q(w, 0.5), q(w, 0.9)];
        });
        const ys = g.depths.map((d) => `${d} m`);
        await plot(profChart, [
          { x: stats.map((s) => s[2]), y: ys, mode: 'lines', line: { width: 0 }, hoverinfo: 'skip', showlegend: false },
          { x: stats.map((s) => s[0]), y: ys, mode: 'lines', fill: 'tonextx', fillcolor: C.band, line: { width: 0 }, name: '10–90th pct', hoverinfo: 'skip' },
          { x: stats.map((s) => s[1]), y: ys, mode: 'lines+markers', line: { color: C.cyan, width: 2.5 }, name: 'Median width', hovertemplate: '%{y}: %{x:.2f} °C<extra></extra>' },
        ], { xaxis: { title: { text: '90% interval width (°C)' } }, yaxis: { autorange: 'reversed', type: 'category' }, margin: { l: 64, r: 12, t: 8, b: 60 } }, ctx, 'aquasphere-width-profile');
      } catch (err) {
        if (ctx.signal.aborted) return;
        errorState(mapChart, err);
        errorState(profChart, err);
      }
    });
    reveal(root, ctx, '.grid > .card');
  },
};
