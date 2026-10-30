import * as api from '../api.js';
import { badge, tag } from '../ui/badges.js';
import { pending } from '../ui/loaders.js';
import { plot, C } from '../charts/theme.js';
import { card, h, $, fmt, reveal } from './_util.js';

const LADDER = [
  ['B0', 'Climatology'],
  ['B1', 'Climatology + Ridge'],
  ['B2', 'Gradient Boosted Trees (HistGBDT)'],
  ['B3', 'v1 OceanEmbedNet (Re-evaluated)'],
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
  c.body.innerHTML = '<div class="chart"></div><div class="table-wrap" tabindex="0" role="region" aria-label="E1 leakage gap by model"><table class="table"><thead><tr><th>Model</th><th class="num">Random</th><th class="num">Float-blocked</th><th class="num">Time-blocked</th><th class="num">Float gap</th><th class="num">Time gap</th></tr></thead><tbody></tbody></table></div>';
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

const V2_SERIES = { B0: C.faint, B1: C.indigo, B2: C.teal, B3: C.violet, B4: C.cyan };

/** E2 under protocol v2: time-blocked + float-grouped, 2023 validation, test locked. */
async function e2v2(host, ctx, m) {
  const c = card({ title: 'E2 · baseline ladder (protocol v2)', sub: `Validation 2023 · ${m.split.profiles.val} profiles from ${m.split.floats.val} floats never seen in training · 95% CI from a bootstrap over floats` });
  host.append(c.card);
  c.meta.append(badge('results'), tag('Validation 2023', 'heldout', 'The test-period ladder is in the Final evaluation card.'));
  c.body.innerHTML = `<div class="grid grid--2"><div class="chart"></div><div class="chart"></div></div>
    <div class="table-wrap" tabindex="0" role="region" aria-label="E2 baseline ladder"><table class="table"><thead><tr><th>Rung</th><th>Model</th><th class="num">Thermocline RMSE</th><th class="num">95% CI</th><th class="num">Skill vs B0</th><th class="num">≥ 20 m RMSE</th><th class="num">D20 RMSE (m)</th><th class="num">vs B0, p (Holm)</th></tr></thead><tbody></tbody></table></div>
    <p class="note"></p>`;
  const keys = Object.keys(m.e2);
  const [left, right] = c.body.querySelectorAll('.chart');
  await plot(left, [{
    type: 'bar', x: keys, y: keys.map((k) => m.e2[k].thermocline_rmse),
    error_y: { type: 'data', symmetric: false, array: keys.map((k) => m.e2[k].thermocline_ci_95[1] - m.e2[k].thermocline_rmse), arrayminus: keys.map((k) => m.e2[k].thermocline_rmse - m.e2[k].thermocline_ci_95[0]), color: C.glow },
    marker: { color: keys.map((k) => V2_SERIES[k] || C.cyan) }, customdata: keys.map((k) => m.e2[k].name), hovertemplate: '%{customdata}: %{y:.3f} °C<extra></extra>',
  }], { yaxis: { title: { text: 'Thermocline RMSE (°C)' } }, showlegend: false }, ctx, 'aquasphere-e2-ladder');
  const bands = m.e2.B0.bands.map((b) => b.band);
  await plot(right, keys.map((k) => ({
    x: m.e2[k].bands.map((b) => b.rmse), y: bands, name: k, mode: 'lines+markers', line: { color: V2_SERIES[k] || C.cyan, width: 2.5 },
    hovertemplate: `${k} %{y}: %{x:.2f} °C<extra></extra>`,
  })), { xaxis: { title: { text: 'RMSE (°C)' } }, yaxis: { autorange: 'reversed', type: 'category' }, margin: { l: 150, r: 12, t: 8, b: 60 } }, ctx, 'aquasphere-e2-depth');
  const tb = c.body.querySelector('tbody');
  for (const k of keys) {
    const r = m.e2[k];
    const tr = h('<tr><td class="mono"></td><td></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td></tr>');
    const cmp = r.vs_B0_thermocline;
    [k, r.name, `${fmt(r.thermocline_rmse, 3)} ± ${fmt(r.thermocline_rmse_seed_std, 3)}`, `${fmt(r.thermocline_ci_95[0])}–${fmt(r.thermocline_ci_95[1])}`,
      r.skill_thermocline == null ? '—' : `${r.skill_thermocline >= 0 ? '+' : ''}${fmt(r.skill_thermocline, 3)}`, fmt(r.headline_rmse_20m_plus, 3), fmt(r.d20_rmse_m, 1),
      cmp ? `${cmp.diff >= 0 ? '+' : ''}${fmt(cmp.diff, 3)} °C, ${cmp.p_holm < 0.001 ? '<0.001' : fmt(cmp.p_holm, 3)}` : '—']
      .forEach((x, i) => { tr.cells[i].textContent = x; });
    tb.append(tr);
  }
  const b5 = h('<tr><td class="mono">B5</td><td colspan="7"><span class="badge badge--muted" title="ARMOR3D is distributed by Copernicus Marine, which needs an account; everything else here uses open data">Not run</span> <span>ARMOR3D upper reference: needs a Copernicus Marine account, and it assimilates Argo, so it could only be a labelled reference</span></td></tr>');
  tb.append(b5);
  c.body.querySelector('.note').textContent = `Every rung is fitted on ${m.split.profiles.train.toLocaleString()} training profiles (2015–2022) with fixed, untuned settings. ± is the spread over ${m.seeds.length} seeds; deterministic rungs run once. Headline depths are 20 m and below because satellite SST already contains Argo near-surface data. ${m.split.dropped_profiles.val.toLocaleString()} 2023 profiles from floats already seen in training are excluded. Generated ${m.generated_at.slice(0, 10)}.`;

  // Strata with power analysis
  const s = card({ title: 'Basin × monsoon season', sub: 'Thermocline RMSE per stratum with sample counts. MDE = the smallest B2-vs-B0 difference this stratum could detect (80% power, α = 0.05).' });
  host.append(s.card);
  s.meta.append(badge('results'));
  s.body.innerHTML = '<div class="table-wrap" tabindex="0" role="region" aria-label="Results by basin and monsoon season"><table class="table"><thead><tr><th>Basin</th><th>Season</th><th class="num">Profiles</th><th class="num">Floats</th><th class="num">B0</th><th class="num">B2</th><th class="num">B4 90% coverage</th><th class="num">MDE (°C)</th><th>Status</th></tr></thead><tbody></tbody></table></div>';
  for (const r of m.strata) {
    const t = r.thermocline_rmse || {};
    const tr = h('<tr><td></td><td></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td><td></td></tr>');
    [r.region, r.season, r.profiles, r.floats, fmt(t.B0, 3), fmt(t.B2, 3), r.b4_coverage_90 == null ? '—' : `${(r.b4_coverage_90 * 100).toFixed(1)}%`, fmt(r.mde_thermocline_c, 2)]
      .forEach((x, i) => { tr.cells[i].textContent = x; });
    tr.cells[8].append(tag(r.status, r.status === 'confirmatory' ? 'ok' : r.status === 'empty' ? 'muted' : 'warn'));
    s.body.querySelector('tbody').append(tr);
  }
}

/** E1 under protocol v2: same models, three splits of 2015–2023. */
async function e1v2(host, ctx, d) {
  const c = card({ title: 'E1 · leakage gap (protocol v2)', sub: 'Thermocline RMSE of the same models under three ways of splitting 2015–2023 (test period untouched)' });
  host.append(c.card);
  c.meta.append(badge('results'));
  c.body.innerHTML = '<div class="chart"></div><div class="table-wrap" tabindex="0" role="region" aria-label="E1 leakage gap by model"><table class="table"><thead><tr><th>Model</th><th class="num">Random</th><th class="num">Float-grouped</th><th class="num">Time-blocked + float-grouped</th><th class="num">Random looks better by</th></tr></thead><tbody></tbody></table></div><p class="note"></p>';
  const models = Object.keys(d.models);
  const proto = [['Random (naive)', 'random', C.coral], ['Float-grouped', 'float_grouped', C.teal], ['Time-blocked + float-grouped', 'time_blocked_float_grouped', C.indigo]];
  await plot(c.body.firstChild, proto.map(([name, key, color]) => ({
    type: 'bar', name, x: models, y: models.map((m) => d.models[m][key]), marker: { color }, hovertemplate: `${name}: %{y:.3f} °C<extra></extra>`,
  })), { barmode: 'group', yaxis: { title: { text: 'Thermocline RMSE (°C)' } }, margin: { l: 56, r: 12, t: 8, b: 40 } }, ctx, 'aquasphere-e1');
  for (const k of models) {
    const r = d.models[k];
    const tr = h('<tr><td class="mono"></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td></tr>');
    [k, fmt(r.random, 3), fmt(r.float_grouped, 3), fmt(r.time_blocked_float_grouped, 3), r.random_vs_blocked_pct == null ? '—' : `${fmt(r.random_vs_blocked_pct, 1)}%`]
      .forEach((x, i) => { tr.cells[i].textContent = x; });
    c.body.querySelector('tbody').append(tr);
  }
  c.body.querySelector('.note').textContent = `How much a random profile split flatters each model compared with the protocol split. Hypothesis H4 is tested on B3, the v1 network. Split sizes: random ${d.splits.random.eval}, float-grouped ${d.splits.float_grouped.eval}, protocol ${d.splits.time_blocked_float_grouped.eval} evaluation profiles.`;
}

async function e2(host, ctx) {
  const c = card({ title: 'E2 · baseline ladder', sub: 'Float-grouped held-out set · thermocline RMSE with 95% bootstrap CI, and RMSE by depth band' });
  host.append(c.card);
  const m = await optional('metrics');
  if (!m) { c.meta.append(badge('pending')); return pending(c.body, { needs: 'web/data/metrics.json (make eval && make ui-data)' }); }
  c.meta.append(badge('results'));
  c.body.innerHTML = '<div class="grid grid--2"><div class="chart"></div><div class="chart"></div></div><div class="table-wrap" tabindex="0" role="region" aria-label="E2 baseline ladder"><table class="table"><thead><tr><th>Rung</th><th>Model</th><th class="num">Thermo RMSE</th><th class="num">95% CI</th><th class="num">Overall RMSE</th><th class="num">Skill</th></tr></thead><tbody></tbody></table></div>';
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
  for (const [id, what] of [
    ['B4', 'Deep ensemble of Tier A models (uncertainty baseline for conformal)'],
    ['B5', 'ARMOR3D upper reference (mooring comparison only; it assimilates Argo)'],
  ]) {
    const tr = h('<tr><td class="mono"></td><td colspan="5"><span class="badge badge--pending">Pending</span> <span></span></td></tr>');
    tr.cells[0].textContent = id;
    tr.cells[1].lastChild.textContent = what;
    tb.append(tr);
  }
  const n = document.createElement('p');
  n.className = 'note';
  n.textContent = `${m.n_eval_profiles} held-out profiles from ${m.n_eval_floats} floats (${m.split}), ${m.n_train_profiles} training profiles. Generated ${m._generated_at?.slice(0, 10) || '—'}. The blueprint specifies LightGBM for B2; this run used scikit-learn's HistGradientBoosting, an equivalent histogram GBDT.`;
  c.body.append(n);
}


const HYP_LABEL = {
  H1a: ['H1a', 'SLA adds to SST', (h) => `${(h.reduction * 100).toFixed(1)}% lower RMSE`, (h) => `${(h.ci[0] * 100).toFixed(1)} to ${(h.ci[1] * 100).toFixed(1)}%`, '≥ 15%'],
  H1b: ['H1b', 'Nowcast keeps skill', (h) => `ratio ${fmt(h.ratio, 3)}`, (h) => `${fmt(h.ci[0], 3)} to ${fmt(h.ci[1], 3)}`, '≥ 0.85'],
  H2: ['H2', 'Pre-training helps', (h) => `${(h.labels_100pct.reduction * 100).toFixed(1)}% · ${(h.labels_10pct.reduction * 100).toFixed(1)}% at 10%`, (h) => `${(h.labels_100pct.ci[0] * 100).toFixed(1)} to ${(h.labels_100pct.ci[1] * 100).toFixed(1)}%`, '≥ 5% and ≥ 10%'],
  H3: ['H3', 'Calibrated 90% intervals', (h) => `${(h.coverage * 100).toFixed(1)}% coverage`, (h) => `${(h.ci[0] * 100).toFixed(1)} to ${(h.ci[1] * 100).toFixed(1)}%`, '87–93%, strata 85–95%'],
  H4: ['H4', 'Random split flatters', (h) => `${(h.gap * 100).toFixed(1)}% gap`, (h) => `${(h.ci[0] * 100).toFixed(1)} to ${(h.ci[1] * 100).toFixed(1)}%`, '≥ 20%'],
};

/** The one run on 2024-25: frozen hypotheses with Holm, and the test-period ladder. */
async function finalCard(host, ctx, f) {
  const n = Object.values(f.hypotheses).filter((x) => x.supported).length;
  const c = card({ title: 'Final evaluation · test period 2024–25', sub: `Read once · ${f.split.test_profiles.toLocaleString()} profiles from ${f.split.test_floats} floats never used for training or calibration · hypotheses frozen ${f.hypotheses_file.frozen_at}` });
  host.append(c.card);
  c.card.classList.add('card--final');
  c.meta.append(badge('results'), tag(`${n} of 5 hypotheses supported`, n ? 'ok' : 'warn', 'After Holm correction, at alpha 0.05, and only when the estimate also meets its frozen threshold.'));
  c.body.innerHTML = `<div class="table-wrap" tabindex="0" role="region" aria-label="Confirmatory hypotheses"><table class="table"><thead><tr><th>Hypothesis</th><th>Estimate</th><th class="num">95% CI</th><th>Threshold</th><th class="num">p (Holm)</th><th>Result</th></tr></thead><tbody></tbody></table></div>
    <div class="chart"></div><p class="note"></p>`;
  const tb = c.body.querySelector('tbody');
  for (const [key, [id, claim, est, ci, thr]] of Object.entries(HYP_LABEL)) {
    const hyp = f.hypotheses[key];
    if (!hyp) continue;
    const tr = h('<tr><td></td><td></td><td class="num"></td><td></td><td class="num"></td><td></td></tr>');
    tr.cells[0].innerHTML = `<strong>${id}</strong> `;
    tr.cells[0].append(claim);
    [est(hyp), ci(hyp), thr, hyp.p_holm < 0.001 ? '< 0.001' : fmt(hyp.p_holm, 3)].forEach((v, i) => { tr.cells[i + 1].textContent = v; });
    tr.cells[5].append(tag(hyp.supported ? 'Supported' : 'Not supported', hyp.supported ? 'ok' : 'warn'));
    if (hyp.supported) tr.classList.add('is-best');
    tb.append(tr);
  }
  const keys = Object.keys(f.ladder);
  const colors = keys.map((k) => (k.startsWith('Tier A') ? (k.includes('nowcast') ? C.teal : C.cyan) : V2_SERIES[k] || C.faint));
  await plot(c.body.querySelector('.chart'), [{
    type: 'bar', x: keys, y: keys.map((k) => f.ladder[k].thermocline_rmse),
    error_y: { type: 'data', symmetric: false, array: keys.map((k) => f.ladder[k].ci[1] - f.ladder[k].thermocline_rmse), arrayminus: keys.map((k) => f.ladder[k].thermocline_rmse - f.ladder[k].ci[0]), color: C.glow },
    marker: { color: colors }, customdata: keys.map((k) => [f.ladder[k].name, f.ladder[k].skill_thermocline]),
    hovertemplate: '%{customdata[0]}<br>%{y:.3f} °C · skill %{customdata[1]:.3f}<extra></extra>',
  }], { yaxis: { title: { text: 'Test thermocline RMSE (°C)' } }, margin: { l: 56, r: 12, t: 8, b: 60 }, showlegend: false }, ctx, 'aquasphere-final');
  const a = f.ladder['Tier A v2'];
  const best = keys.filter((k) => !k.startsWith('Tier A')).sort((x, y) => f.ladder[x].thermocline_rmse - f.ladder[y].thermocline_rmse)[0];
  c.body.querySelector('.note').textContent = `On the test period the served model scores ${fmt(a.thermocline_rmse, 3)} °C (95% CI ${fmt(a.ci[0], 3)}–${fmt(a.ci[1], 3)}) against ${fmt(f.ladder[best].thermocline_rmse, 3)} °C for the best baseline (${best}). A hypothesis counts as supported only if its Holm-adjusted p is below 0.05 and its estimate meets the threshold frozen before this run; the rest are reported as they came out.`;
}

const pct = (x) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`);
const ciText = (ci) => (ci?.[0] == null ? '—' : `${fmt(ci[0], 3)} to ${fmt(ci[1], 3)}`);

async function e5v2(host, ctx, p4) {
  const c = card({ title: 'E5 · pre-training learning curves', sub: 'Tier C (pre-trained patch encoder) vs the same network from scratch · thermocline RMSE on validation 2023, seed-averaged' });
  host.append(c.card);
  const h2 = p4.e5.h2_validation;
  c.meta.append(badge('results'), tag(`H2 at validation: ${h2.decision}`, h2.decision === 'go' ? 'ok' : 'warn', 'Go/no-go before the test period; the confirmatory test runs once in Phase 6.'));
  c.body.innerHTML = '<div class="chart"></div><p class="note"></p>';
  const arms = [['scratch', 'From scratch', C.faint, 2.5], ['masked', 'Masked reconstruction', C.teal, 2.5], ['masked+temporal', 'Masked + temporal pretext', C.cyan, 3]];
  await plot(c.body.firstChild, arms.map(([k, name, color, width]) => {
    const pts = p4.e5.curves[k];
    return {
      x: pts.map((p) => p.fraction * 100), y: pts.map((p) => p.thermocline_rmse), name, mode: 'lines+markers', line: { color, width },
      error_y: { type: 'data', array: pts.map((p) => p.seeds.std), color, thickness: 1 },
      hovertemplate: `${name} · %{x}% labels: %{y:.3f} °C<extra></extra>`,
    };
  }), { xaxis: { title: { text: 'Labelled floats used (%)' }, type: 'log', tickvals: [10, 25, 50, 100] }, yaxis: { title: { text: 'Thermocline RMSE (°C)' } }, legend: { orientation: 'h', y: 1.12 } }, ctx, 'aquasphere-e5');
  c.body.querySelector('.note').textContent = `Best pretext (${h2.best_pretext}): ${pct(h2.reduction_full_labels)} RMSE reduction at full labels (H2 needs ≥ ${pct(h2.thresholds.full)}) and ${pct(h2.reduction_10pct_labels)} at 10% (needs ≥ ${pct(h2.thresholds['10%'])}). `
    + (h2.decision === 'go' ? 'Both thresholds are met on validation.' : 'Not met, so the pre-trained model is not shipped and the negative result is reported. Pre-training used 2015–2022 patches only.');
}

async function e4v2(host, ctx, p4) {
  const e = p4.e4;
  const c = card({ title: 'E4 · point features vs 9×9 patch encoder', sub: 'Tier A (scalars at the profile) vs Tier B (4 lags × 7 channels × 9×9 patch) · validation 2023' });
  host.append(c.card);
  c.meta.append(badge('results'));
  c.body.innerHTML = '<div class="chart chart--short"></div><p class="note"></p>';
  const rows = [['Tier A · point', e.tier_a, C.teal], ['Tier B · patch', e.tier_b, C.cyan]];
  await plot(c.body.firstChild, [{
    type: 'bar', x: rows.map((r) => r[0]), y: rows.map((r) => r[1].thermocline_rmse),
    error_y: { type: 'data', symmetric: false, array: rows.map((r) => r[1].ci[1] - r[1].thermocline_rmse), arrayminus: rows.map((r) => r[1].thermocline_rmse - r[1].ci[0]), color: C.glow },
    marker: { color: rows.map((r) => r[2]) }, hovertemplate: '%{x}: %{y:.3f} °C<extra></extra>',
  }], { yaxis: { title: { text: 'Thermocline RMSE (°C)' } }, margin: { l: 56, r: 12, t: 8, b: 40 }, showlegend: false }, ctx, 'aquasphere-e4');
  const d = e.b_minus_a;
  c.body.querySelector('.note').textContent = `Tier B − Tier A = ${fmt(d.diff_c, 3)} °C (95% CI ${ciText(d.ci)}, ${pct(d.relative)}). `
    + (d.ci[0] > 0 ? 'Spatial context made the thermocline worse here, so the point model is served.' : d.ci[1] < 0 ? 'Spatial context helped beyond the bootstrap noise.' : 'The difference is within bootstrap noise.');
}

async function physicsCard(host, p4) {
  const ph = p4.physics;
  const c = card({ title: 'Loss · physics terms', sub: 'Tier A with and without the vertical-gradient and anti-inversion terms (blueprint §9.3)' });
  host.append(c.card);
  c.meta.append(badge('results'));
  c.body.innerHTML = '<div class="table-wrap" tabindex="0" role="region" aria-label="Physics-term ablation"><table class="table"><thead><tr><th>Arm</th><th class="num">Thermocline RMSE</th><th class="num">95% CI</th><th class="num">Skill vs B0</th></tr></thead><tbody></tbody></table></div><p class="note"></p>';
  for (const k of ['with', 'without']) {
    const tr = h('<tr><td></td><td class="num"></td><td class="num"></td><td class="num"></td></tr>');
    [k === 'with' ? 'With physics terms' : 'Without', fmt(ph[k].thermocline_rmse, 3), ciText(ph[k].ci), fmt(ph[k].skill_thermocline, 3)].forEach((v, i) => { tr.cells[i].textContent = v; });
    if (k === ph.chosen) tr.classList.add('is-best');
    c.body.querySelector('tbody').append(tr);
  }
  const d = ph.with_minus_without;
  c.body.querySelector('.note').textContent = `Difference ${fmt(d.diff_c, 3)} °C (95% CI ${ciText(d.ci)}). The served model uses the arm with lower validation RMSE: ${ph.chosen}.`;
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
  if (d?.pooled_headline) {
    c.card.querySelector('.card__sub').textContent = `${d.period[0]} to ${d.period[1]} · daily sensor temperatures at 20 m and deeper · 95% CI from 30-day blocks · never used for training`;
    c.meta.append(badge('results'));
    c.body.innerHTML = '<div class="chart"></div><p class="note"></p>';
    const ms = d.moorings.filter((x) => x.n);
    await plot(c.body.firstChild, [
      { type: 'bar', name: 'Tier A v2', x: ms.map((x) => x.id), y: ms.map((x) => x.headline.rmse), marker: { color: C.cyan },
        error_y: { type: 'data', symmetric: false, array: ms.map((x) => x.headline.ci[1] - x.headline.rmse), arrayminus: ms.map((x) => x.headline.rmse - x.headline.ci[0]), color: C.glow },
        customdata: ms.map((x) => [x.n, x.region]), hovertemplate: '%{x} (%{customdata[1]}): %{y:.3f} °C, n=%{customdata[0]}<extra>Tier A v2</extra>' },
      { type: 'bar', name: 'B0 climatology', x: ms.map((x) => x.id), y: ms.map((x) => x.headline_b0.rmse), marker: { color: C.faint }, hovertemplate: '%{x}: %{y:.3f} °C<extra>Climatology</extra>' },
    ], { barmode: 'group', yaxis: { title: { text: 'RMSE at ≥ 20 m (°C)' } }, legend: { orientation: 'h', y: 1.12 } }, ctx, 'aquasphere-e8');
    const p = d.pooled_headline;
    const b = d.pooled_headline_b0;
    const skipped = d.moorings.filter((x) => !x.n).map((x) => `${x.id} (${x.note})`);
    c.body.querySelector('.note').textContent = `Pooled over ${p.n.toLocaleString()} observations: ${fmt(p.rmse, 3)} °C (95% CI ${fmt(p.ci[0], 3)}–${fmt(p.ci[1], 3)}) against ${fmt(b.rmse, 3)} °C for climatology, so at the moorings the model is not better than climatology. ${skipped.length ? `Not scored: ${skipped.join('; ')}. ` : ''}${d.armor3d}`;
    return;
  }
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
    // Protocol v2 results replace the old 6-month-snapshot results once they exist
    const [v2, e1v2Data] = await Promise.all([optional('metrics_v2'), optional('e1_leakage_v2')]);
    if (v2) await e2v2(a, ctx, v2);
    else await e2(a, ctx);
    if (e1v2Data) await e1v2(a, ctx, e1v2Data);
    else await e1(a, ctx);
    const final = await optional('final_eval');
    if (final && !final.dry_run) {
      const fRow = h('<div class="grid"></div>');
      a.before(fRow);
      await finalCard(fRow, ctx, final);
    }
    const p4 = await optional('phase4');
    if (p4) {
      const p = h('<div class="grid grid--2"></div>');
      a.after(p);
      await e4v2(p, ctx, p4);
      await physicsCard(p, p4);
      await e5v2(b, ctx, p4);
    } else {
      await e5(b, ctx);
    }
    await e8(b, ctx);
    reveal(root, ctx, '.card');
  },
};
