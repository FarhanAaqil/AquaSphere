import { state } from '../state.js';
import * as api from '../api.js';
import { loadGrid } from '../gridData.js';
import { badge, tag, sourceSummary } from '../ui/badges.js';
import { ablationSyntheticChannels, describeChannels } from '../audit.js';
import { loading, errorState, pending } from '../ui/loaders.js';
import { plot, C } from '../charts/theme.js';
import { renderHeatmap } from '../charts/heatmap.js';
import { card, $, h, onDate, fmt, reveal } from './_util.js';

const WIDTH_DEPTHS = [0, 50, 100, 150, 300, 1000];

async function optional(name) {
  try { return await api.results(name); } catch { return null; }
}

const METHOD_LABEL = {
  heteroscedastic: 'Heteroscedastic (raw σ)',
  seed_ensemble: 'Seed ensemble',
  conformal_global: 'Conformal, global',
  conformal_mondrian: 'Conformal, Mondrian (served)',
};

async function e6Card(c, body, meta, p4, ctx) {
  c.querySelector('.card__sub').textContent = 'E6 · four ways to build the 90% interval for Tier A v2 · validation 2023 · bars show the 95% CI from a bootstrap over floats';
  meta.append(badge('results'));
  const keys = Object.keys(p4.e6.methods);
  const overall = keys.map((k) => p4.e6.methods[k].coverage[0]);
  await plot(body.firstChild, [{
    type: 'bar', x: keys.map((k) => METHOD_LABEL[k] || k), y: overall.map((o) => o.coverage * 100),
    error_y: { type: 'data', symmetric: false, array: overall.map((o) => (o.ci_high - o.coverage) * 100), arrayminus: overall.map((o) => (o.coverage - o.ci_low) * 100), color: C.glow },
    marker: { color: keys.map((k) => (k === 'conformal_mondrian' ? C.cyan : 'rgba(20,184,166,0.55)')) },
    customdata: keys.map((k) => [p4.e6.methods[k].mean_width, p4.e6.methods[k].crps_thermocline]),
    hovertemplate: '%{x}: %{y:.1f}%<br>mean width %{customdata[0]:.2f} °C · CRPS %{customdata[1]:.3f}<extra></extra>',
  }], {
    yaxis: { title: { text: 'Coverage (%)' }, range: [70, 100] },
    shapes: [
      { type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 87, y1: 93, fillcolor: 'rgba(251,191,36,0.07)', line: { width: 0 }, layer: 'below' },
      { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 90, y1: 90, line: { color: C.amber, dash: 'dash', width: 1.5 } },
    ],
    margin: { l: 52, r: 12, t: 8, b: 70 }, showlegend: false,
  }, ctx, 'aquasphere-e6');
  const n = body.querySelector('.note');
  n.hidden = false;
  n.textContent = 'Conformal coverage is measured out of fold: each float is scored by a calibrator fitted on the other floats. The shaded band is H3\'s 87–93% target, which is tested once on the 2024–25 test period.';
}

async function coverageCard(host, ctx) {
  const { card: c, body, meta } = card({ title: 'Empirical coverage of the 90% interval', sub: 'Per ablation run, mean ± std over seeds. Dashed line = nominal 90%.' });
  host.append(c);
  body.innerHTML = '<div class="chart chart--short"></div><p class="note" hidden></p>';
  const p4 = await optional('phase4');
  if (p4?.e6) return e6Card(c, body, meta, p4, ctx);
  const ab = await optional('ablation');
  if (!ab) return pending(body, { title: 'Ablation results missing', needs: 'web/data/ablation.json' });
  const synthetic = await ablationSyntheticChannels();
  meta.append(badge('results'), ...(synthetic.length ? [tag('Synthetic inputs', 'warn')] : []));
  if (synthetic.length) {
    const n = h('<p class="note note--warn"></p>');
    n.textContent = `These runs were trained on a table whose ${describeChannels(synthetic)} values are synthetic; only A1 (SST only) uses real inputs throughout. Treat every bar except A1 as not evidence.`;
    body.append(n);
  }
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
  // Protocol v2: the B4 deep ensemble is the first model with real calibration on held-out data
  const p4 = await optional('phase4');
  if (p4?.e6?.reliability) {
    const r = p4.e6.reliability;
    c.querySelector('.card__sub').textContent = 'Tier A v2 · validation 2023 · conformal levels fitted out of fold over floats';
    meta.append(badge('results'));
    return plot(body.firstChild, [
      { x: [0, 1], y: [0, 1], mode: 'lines', line: { color: C.faint, dash: 'dash' }, name: 'Perfect calibration', hoverinfo: 'skip' },
      { x: r.nominal, y: r.heteroscedastic, mode: 'lines+markers', line: { color: C.teal, width: 2 }, name: 'Raw σ (Gaussian)', hovertemplate: 'nominal %{x:.2f} → %{y:.3f}<extra></extra>' },
      { x: r.nominal, y: r.conformal_mondrian, mode: 'lines+markers', line: { color: C.cyan, width: 3 }, name: 'Mondrian conformal', hovertemplate: 'nominal %{x:.2f} → %{y:.3f}<extra></extra>' },
    ], { xaxis: { title: { text: 'Nominal coverage' }, range: [0.45, 1] }, yaxis: { title: { text: 'Empirical coverage' }, range: [0.45, 1] }, legend: { orientation: 'h', y: 1.12 } }, ctx, 'aquasphere-reliability');
  }
  const v2 = await optional('metrics_v2');
  const fromB4 = v2?.e2?.B4?.probabilistic?.reliability;
  const rel = fromB4 || (await optional('reliability'));
  if (fromB4) c.querySelector('.card__sub').textContent = `B4 deep-ensemble baseline · validation 2023 · ${fromB4.n.toLocaleString()} observed depth cells (AquaSphere's own model is retrained in Phase 4)`;
  if (!rel) {
    meta.append(badge('pending'));
    return pending(body, { title: 'Pending', detail: 'Needs coverage measured at several nominal levels on held-out profiles.', needs: 'web/data/reliability.json → { "nominal": [0.5, …, 0.95], "empirical": [...], "n": int }' });
  }
  meta.append(badge('results'));
  await plot(body.firstChild, [
    { x: [0, 1], y: [0, 1], mode: 'lines', line: { color: C.faint, dash: 'dash' }, name: 'Perfect calibration', hoverinfo: 'skip' },
    { x: rel.nominal, y: rel.empirical, mode: 'lines+markers', line: { color: C.cyan, width: 3 }, name: fromB4 ? 'B4 deep ensemble' : 'AquaSphere', hovertemplate: 'nominal %{x:.2f} → empirical %{y:.2f}<extra></extra>' },
  ], { xaxis: { title: { text: 'Nominal coverage' }, range: [0, 1] }, yaxis: { title: { text: 'Empirical coverage' }, range: [0, 1] } }, ctx, 'aquasphere-reliability');
}

async function regionSeasonCard(host, ctx) {
  const { card: c, body, meta } = card({ title: 'Coverage by region and monsoon season', sub: 'Arabian Sea vs Bay of Bengal · SW monsoon, NE monsoon, inter-monsoon' });
  host.append(c);
  body.innerHTML = '<div class="chart chart--short"></div>';
  const p4 = await optional('phase4');
  const mond = p4?.e6?.methods?.conformal_mondrian?.coverage?.filter((r) => r.region !== 'All');
  if (mond?.length) {
    c.querySelector('.card__sub').textContent = 'Served Mondrian intervals · 95% CI over floats · shaded 85–95% = Phase 4 gate · hatched = too few floats for claims';
    meta.append(badge('results'));
    const regions = [...new Set(mond.map((r) => r.region))];
    return plot(body.firstChild, regions.map((rg, i) => {
      const rows = mond.filter((r) => r.region === rg);
      return {
        type: 'bar', name: rg, x: rows.map((r) => r.season), y: rows.map((r) => r.coverage * 100),
        error_y: { type: 'data', symmetric: false, array: rows.map((r) => (r.ci_high - r.coverage) * 100), arrayminus: rows.map((r) => (r.coverage - r.ci_low) * 100), color: C.glow },
        marker: { color: [C.coral, C.indigo][i % 2], pattern: { shape: rows.map((r) => (r.status === 'descriptive only' ? '/' : '')) } },
        customdata: rows.map((r) => [r.profiles, r.floats, r.status]),
        hovertemplate: `${rg} · %{x}: %{y:.1f}%<br>%{customdata[0]} profiles, %{customdata[1]} floats · %{customdata[2]}<extra></extra>`,
      };
    }), {
      barmode: 'group', yaxis: { title: { text: 'Coverage (%)' }, range: [70, 100] },
      shapes: [
        { type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 85, y1: 95, fillcolor: 'rgba(251,191,36,0.07)', line: { width: 0 }, layer: 'below' },
        { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 90, y1: 90, line: { color: C.amber, dash: 'dash' } },
      ],
    }, ctx, 'aquasphere-coverage-regions');
  }
  const v2 = await optional('metrics_v2');
  const v2rows = (v2?.strata || []).filter((r) => r.b4_coverage_90 != null).map((r) => ({ region: r.region, season: r.season, coverage: r.b4_coverage_90, n: r.profiles, status: r.status }));
  const data = v2rows.length ? { rows: v2rows } : await optional('coverage_regions');
  if (v2rows.length) c.querySelector('.card__sub').textContent = 'B4 deep-ensemble 90% coverage per stratum · validation 2023 · hatched = too few floats for claims';
  if (!data) {
    meta.append(badge('pending'));
    return pending(body, { title: 'Pending', detail: 'The evaluation has not been broken down by basin and season yet.', needs: 'web/data/coverage_regions.json → { "rows": [{ "region", "season", "coverage", "n" }] }' });
  }
  meta.append(badge('results'));
  const regions = [...new Set(data.rows.map((r) => r.region))];
  await plot(body.firstChild, regions.map((rg, i) => {
    const rows = data.rows.filter((r) => r.region === rg);
    return {
      type: 'bar', name: rg, x: rows.map((r) => r.season), y: rows.map((r) => r.coverage * 100),
      marker: { color: [C.coral, C.indigo, C.teal][i % 3], pattern: { shape: rows.map((r) => (r.status === 'descriptive only' ? '/' : '')) } },
      customdata: rows.map((r) => [r.n, r.status || '']),
      hovertemplate: `${rg} · %{x}: %{y:.1f}% (n=%{customdata[0]}) %{customdata[1]}<extra></extra>`,
    };
  }), {
    barmode: 'group', yaxis: { title: { text: 'Coverage (%)' } },
    shapes: [
      // H3 acceptance band: within ±5 points of nominal in every stratum
      { type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 85, y1: 95, fillcolor: 'rgba(251,191,36,0.07)', line: { width: 0 }, layer: 'below' },
      { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 90, y1: 90, line: { color: C.amber, dash: 'dash' } },
    ],
  }, ctx, 'aquasphere-coverage-regions');
}

async function dissimilarityCard(host, ctx) {
  const { card: c, body, meta } = card({ title: 'Applicability domain · dissimilarity index', sub: 'Distance of each cell\'s embedding from the training embeddings, divided by their mean nearest-neighbour distance' });
  host.append(c);
  body.innerHTML = '<div class="chart" style="min-height:300px"></div><p class="note"></p>';
  const chart = body.firstChild;
  const note = body.querySelector('.note');
  const p4 = await optional('phase4');
  const draw = async (date) => {
    if (!date) return errorState(chart, { kind: 'offline' });
    loading(chart, `Computing the dissimilarity index for ${date}…`);
    try {
      const g = await api.gridV2({ date, depth: 100, step: 2 }, { signal: ctx.signal });
      if (!g.cells.some((x) => x.di != null)) {
        meta.replaceChildren(badge('pending'));
        return pending(chart, { title: 'Not reported', detail: 'The served model is the v1 checkpoint, which has no dissimilarity index. Train the protocol v2 model (make eval-phase4).' });
      }
      const lats = [...new Set(g.cells.map((x) => x.lat))].sort((a, b) => a - b);
      const lons = [...new Set(g.cells.map((x) => x.lon))].sort((a, b) => a - b);
      const at = new Map(g.cells.map((x) => [`${x.lat}|${x.lon}`, x.di]));
      const z = lats.map((la) => lons.map((lo) => at.get(`${la}|${lo}`) ?? null));
      meta.replaceChildren(...sourceSummary(g.cells.map((x) => x.data_source)));
      chart.replaceChildren();
      await renderHeatmap(chart, { lats, lons, z, unit: 'DI', label: 'Dissimilarity', scale: 'width' }, ctx, `aquasphere-di-${date}`);
      const out = g.cells.filter((x) => x.in_domain === false).length;
      const ap = p4?.e6?.applicability;
      note.textContent = `${out} of ${g.count} cells on ${date} are outside the applicability domain.` + (ap
        ? ` On the 2023 validation set, ${(ap.share_inside * 100).toFixed(0)}% of profiles were inside; thermocline RMSE was ${fmt(ap.inside.thermocline_rmse, 2)} °C inside and ${fmt(ap.outside.thermocline_rmse, 2)} °C outside (${ap.outside.profiles} profiles).`
        : '');
    } catch (err) {
      if (ctx.signal.aborted) return;
      meta.replaceChildren();
      errorState(chart, err, { retry: () => draw(state.date) });
    }
  };
  onDate(ctx, draw);
}

async function driftCard(host, ctx) {
  const { card: c, body, meta } = card({ title: 'Drift monitor', sub: 'Monthly mean dissimilarity of the whole domain (3° grid) against the training data' });
  host.append(c);
  body.innerHTML = '<div class="chart chart--short"></div><p class="note"></p>';
  const chart = body.firstChild;
  const dates = state.meta?.available_dates || [];
  if (!dates.length) return pending(chart, { title: 'No stored dates', detail: 'The drift monitor runs over dates in the local surface store.' });
  // Scoring one grid per month over the whole store takes a while: run it when asked
  const box = pending(chart, { title: 'Not run yet', detail: `Scores a 3° grid on one date per month from ${dates[0]} to ${dates.at(-1)} (about 20 s the first time, then cached by the API).` });
  const go = document.createElement('button');
  go.className = 'btn btn--sm';
  go.textContent = 'Run drift monitor';
  box.append(go);
  await new Promise((resolve) => go.addEventListener('click', resolve, { once: true }));
  loading(chart, 'Scoring one grid per month…');
  try {
    const d = await api.drift({ start: dates[0], end: dates.at(-1), step_days: 30, step: 3 }, { signal: ctx.signal });
    meta.replaceChildren(tag(`model ${d.model_version}`, 'muted'));
    chart.replaceChildren();
    const x = d.points.map((p) => p.date);
    await plot(chart, [
      { x, y: d.points.map((p) => p.mean_di), mode: 'lines+markers', name: 'Mean DI', line: { color: C.cyan, width: 2.5 } },
      { x, y: d.points.map((p) => p.p90_di), mode: 'lines', name: '90th percentile', line: { color: C.teal, width: 1.5, dash: 'dot' } },
      { x, y: d.points.map((p) => p.share_outside * 100), mode: 'lines', name: '% cells outside', yaxis: 'y2', line: { color: C.coral, width: 1.5 } },
    ], {
      yaxis: { title: { text: 'DI' } },
      yaxis2: { title: { text: '% outside' }, overlaying: 'y', side: 'right', showgrid: false, rangemode: 'tozero' },
      shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: d.threshold, y1: d.threshold, line: { color: C.amber, dash: 'dash' } }],
      legend: { orientation: 'h', y: 1.15 }, margin: { l: 52, r: 52, t: 8, b: 40 },
    }, ctx, 'aquasphere-drift');
    body.querySelector('.note').textContent = `Dashed line: the applicability threshold (DI ${fmt(d.threshold, 2)}). A rising curve after 2022 means the inputs are moving away from what the model was trained on.`;
  } catch (err) {
    if (ctx.signal.aborted) return;
    if (err.status === 503 || err.kind === 'not_found') {
      return pending(chart, { title: 'Not available', detail: err.detail || 'The drift monitor needs the protocol v2 model and API v2.' });
    }
    errorState(chart, err);
  }
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
    await Promise.all([regionSeasonCard(cRow, ctx), dissimilarityCard(cRow, ctx)]);
    const dRow = h('<div class="grid"></div>');
    root.append(dRow);
    driftCard(dRow, ctx);

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
