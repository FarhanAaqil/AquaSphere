import * as api from '../api.js';
import { badge } from '../ui/badges.js';
import { pending } from '../ui/loaders.js';
import { plot, C } from '../charts/theme.js';
import { card, h, $, fmt, reveal } from './_util.js';

const LADDER = [
  ['B0', 'Climatology'],
  ['B1', 'Climatology + Ridge'],
  ['B2', 'Gradient Boosted Trees (HistGBDT)'],
  ['Net', 'v1 OceanEmbedNet (Re-evaluated)'],
];
const SERIES = [C.faint, C.indigo, C.teal, C.cyan];

async function optional(name) {
  try { return await api.results(name); } catch { return null; }
}

async function e1(host, ctx) {
  const c = card({ title: 'E1 · leakage gap', sub: 'Thermocline RMSE under a random split vs float-blocked and time-blocked splits' });
  host.append(c.card);
  const d = await optional('e1_leakage');
  if (!d) { c.meta.append(badge('pending')); return pending(c.body, { needs: 'web/data/e1_leakage.json (make leakage)' }); }
  c.meta.append(badge('results'));
  c.body.innerHTML = '<div class="chart"></div><div class="table-wrap"><table class="table"><thead><tr><th>Model</th><th class="num">Random</th><th class="num">Float-blocked</th><th class="num">Time-blocked</th><th class="num">Float gap</th><th class="num">Time gap</th></tr></thead><tbody></tbody></table></div>';
  const models = Object.keys(d.leakage_gaps);
  const g = d.leakage_gaps;
  const proto = [['Random (naive)', 'rand_thermo_rmse', C.coral], ['Float-blocked', 'flt_thermo_rmse', C.teal], ['Time-blocked', 'time_thermo_rmse', C.indigo]];
  await plot(c.body.firstChild, proto.map(([name, key, color]) => ({
    type: 'bar', name, x: models, y: models.map((m) => g[m][key]), marker: { color }, hovertemplate: `${name}: %{y:.3f} °C<extra></extra>`,
  })), { barmode: 'group', yaxis: { title: { text: 'Thermocline RMSE (°C)' } }, margin: { l: 56, r: 12, t: 8, b: 80 } }, ctx, 'aquasphere-e1');
  const tb = c.body.querySelector('tbody');
  for (const m of models) {
    const tr = h('<tr><td></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td></tr>');
    [m, fmt(g[m].rand_thermo_rmse, 3), fmt(g[m].flt_thermo_rmse, 3), fmt(g[m].time_thermo_rmse, 3), `+${fmt(g[m].delta_float_leakage, 3)}`, `+${fmt(g[m].delta_time_leakage, 3)}`]
      .forEach((v, i) => { tr.cells[i].textContent = v; });
    tb.append(tr);
  }
  const n = document.createElement('p');
  n.className = 'note';
  n.textContent = 'A positive gap means the random split flatters the model: profiles from the same float leak between train and test. All headline numbers on this site use the float-grouped split.';
  c.body.append(n);
}

async function e2(host, ctx) {
  const c = card({ title: 'E2 · baseline ladder', sub: 'Float-grouped held-out set · thermocline RMSE with 95% bootstrap CI, and RMSE by depth band' });
  host.append(c.card);
  const m = await optional('metrics');
  if (!m) { c.meta.append(badge('pending')); return pending(c.body, { needs: 'web/data/metrics.json (make eval && make ui-data)' }); }
  c.meta.append(badge('results'));
  c.body.innerHTML = '<div class="grid grid--2"><div class="chart"></div><div class="chart"></div></div><div class="table-wrap"><table class="table"><thead><tr><th>Rung</th><th>Model</th><th class="num">Thermo RMSE</th><th class="num">95% CI</th><th class="num">Overall RMSE</th><th class="num">Skill</th></tr></thead><tbody></tbody></table></div>';
  const rows = LADDER.map(([id, key]) => [id, key, m.baselines[key]]).filter((r) => r[2]);
  const [left, right] = c.body.querySelectorAll('.chart');
  await plot(left, [{
    type: 'bar', x: rows.map((r) => r[0]), y: rows.map((r) => r[2].thermocline_rmse),
    error_y: { type: 'data', symmetric: false, array: rows.map((r) => r[2].thermocline_ci_95[1] - r[2].thermocline_rmse), arrayminus: rows.map((r) => r[2].thermocline_rmse - r[2].thermocline_ci_95[0]), color: C.glow },
    marker: { color: rows.map((_, i) => SERIES[i]) }, customdata: rows.map((r) => r[1]), hovertemplate: '%{customdata}: %{y:.3f} °C<extra></extra>',
  }], { yaxis: { title: { text: 'Thermocline RMSE (°C)' } }, showlegend: false }, ctx, 'aquasphere-e2-ladder');
  const groups = rows[0][2].grouped.map((gp) => gp.depth_group);
  await plot(right, rows.map((r, i) => ({
    x: r[2].grouped.map((gp) => gp.rmse), y: groups, name: r[0], mode: 'lines+markers', line: { color: SERIES[i], width: 2.5 }, hovertemplate: `${r[0]} %{y}: %{x:.2f} °C<extra></extra>`,
  })), { xaxis: { title: { text: 'RMSE (°C)' } }, yaxis: { autorange: 'reversed', type: 'category' }, margin: { l: 90, r: 12, t: 8, b: 60 } }, ctx, 'aquasphere-e2-depth');
  const tb = c.body.querySelector('tbody');
  for (const [id, key, v] of rows) {
    const tr = h('<tr><td class="mono"></td><td></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td></tr>');
    [id, key, fmt(v.thermocline_rmse, 3), `${fmt(v.thermocline_ci_95[0])}–${fmt(v.thermocline_ci_95[1])}`, fmt(v.overall_rmse, 3), fmt(v.skill_score_overall, 3)].forEach((x, i) => { tr.cells[i].textContent = x; });
    tb.append(tr);
  }
  const tr = h('<tr><td class="mono">B3–B5</td><td colspan="5"><span class="badge badge--pending">Pending</span> Not in metrics.json yet</td></tr>');
  tb.append(tr);
  const n = document.createElement('p');
  n.className = 'note';
  n.textContent = `${m.n_eval_profiles} held-out profiles from ${m.n_eval_floats} floats (${m.split}), ${m.n_train_profiles} training profiles. Generated ${m._generated_at?.slice(0, 10) || '—'}.`;
  c.body.append(n);
}

async function e5(host, ctx) {
  const c = card({ title: 'E5 · pre-training learning curves', sub: 'Thermocline RMSE with 10 / 25 / 50 / 100% of labels, with and without self-supervised pre-training' });
  host.append(c.card);
  const d = await optional('e5_learning_curve');
  if (!d) {
    c.meta.append(badge('pending'));
    return pending(c.body, { title: 'Pending', detail: 'The label-fraction sweep has not been run.', needs: 'web/data/e5_learning_curve.json → { "fractions": [0.1,0.25,0.5,1], "scratch": [...], "pretrained": [...] }' });
  }
  c.meta.append(badge('results'));
  c.body.innerHTML = '<div class="chart"></div>';
  await plot(c.body.firstChild, [
    { x: d.fractions.map((f) => f * 100), y: d.scratch, name: 'From scratch', mode: 'lines+markers', line: { color: C.faint, width: 2.5 } },
    { x: d.fractions.map((f) => f * 100), y: d.pretrained, name: 'SSL pre-trained', mode: 'lines+markers', line: { color: C.cyan, width: 3 } },
  ], { xaxis: { title: { text: 'Labelled profiles used (%)' }, type: 'log', tickvals: [10, 25, 50, 100] }, yaxis: { title: { text: 'Thermocline RMSE (°C)' } } }, ctx, 'aquasphere-e5');
}

async function e8(host, ctx) {
  const c = card({ title: 'E8 · RAMA mooring comparison', sub: 'Independent check against moored buoy temperature time series' });
  host.append(c.card);
  const d = await optional('e8_rama');
  if (!d) {
    c.meta.append(badge('pending'));
    return pending(c.body, { title: 'Pending', detail: 'No RAMA comparison has been produced. Moorings are fully independent of Argo, so this is the strongest external test.', needs: 'web/data/e8_rama.json → { "moorings": [{ "id", "lat", "lon", "rmse", "n" }] }' });
  }
  c.meta.append(badge('results'));
  c.body.innerHTML = '<div class="chart"></div>';
  await plot(c.body.firstChild, [{ type: 'bar', x: d.moorings.map((x) => x.id), y: d.moorings.map((x) => x.rmse), marker: { color: C.teal }, customdata: d.moorings.map((x) => x.n), hovertemplate: '%{x}: %{y:.2f} °C (n=%{customdata})<extra></extra>' }], { yaxis: { title: { text: 'RMSE (°C)' } } }, ctx, 'aquasphere-e8');
}

export default {
  async mount(root, ctx) {
    root.innerHTML = `<div class="page__intro"><h2>Experiments</h2>
      <p>Each card reads its own results file. If a file is missing the experiment is shown as <strong>Pending</strong> with the
      schema it needs. No placeholder numbers.</p></div>
      <div class="grid" data-ref="a"></div><div class="grid grid--2" data-ref="b"></div>`;
    const a = $(root, '[data-ref="a"]');
    const b = $(root, '[data-ref="b"]');
    await e2(a, ctx);
    await e1(a, ctx);
    await Promise.all([e5(b, ctx), e8(b, ctx)]);
    reveal(root, ctx, '.card');
  },
};
