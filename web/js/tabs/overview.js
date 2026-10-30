import { state, allow3D } from '../state.js';
import * as api from '../api.js';
import { DOMAIN, fmtLat, fmtLon } from '../geo.js';
import { badge, tag } from '../ui/badges.js';
import { setDepth } from '../depth.js';
import { DEPTHS, initDescent, depthToProgress } from '../three/descent.js';
import { h, $, onDate, onState, countUp, reveal, fmt } from './_util.js';
import { ablationSyntheticChannels } from '../audit.js';

const MODEL_KEY = 'v1 OceanEmbedNet (Re-evaluated)';

const STAGES = [
  {
    depth: 'Surface · 0 m',
    title: 'Satellites see the skin of the ocean',
    body: 'Four sensor families are collocated onto each point from open NOAA ERDDAP products: sea-surface temperature (OISST v2.1), sea-level anomaly and geostrophic currents (NOAA/NESDIS altimetry), surface salinity (SMAP via CoastWatch) and 10 m winds (NOAA Blended Winds). With position, season and an availability flag per sensor that makes 18 inputs.',
    chips: ['SST', 'SLA', 'SSS', 'u/v geostrophic', 'u/v 10 m wind'],
  },
  {
    depth: 'Mixed layer · 10–30 m',
    title: 'An encoder turns them into an ocean embedding',
    body: 'The encoder compresses each multi-sensor snapshot into a 16-dimensional, L2-normalised embedding. One model serves two modes: nowcast (SST + SLA, available within hours) and delayed (every sensor). Patch encoders and self-supervised pre-training were tested too and are reported, not shipped.',
    chips: ['16-d embedding', 'nowcast + delayed', 'Tier A v2'],
  },
  {
    depth: 'Thermocline · 50–150 m',
    title: 'A decoder predicts the whole column',
    body: 'A heteroscedastic decoder outputs a mean temperature and a standard deviation at all 15 standard depths at once. The thermocline is where temperature falls fastest and where errors are largest, so it is the headline metric.',
    chips: ['15 depths', 'mean + σ', 'thermocline RMSE'],
  },
  {
    depth: 'Intermediate · 200–500 m',
    title: 'Profiles come with calibrated uncertainty',
    body: 'Conformal calibration on 2023, separately for each region and monsoon season, turns σ into 90% prediction intervals, and a dissimilarity index flags inputs unlike anything in training. From each profile come the 20 °C and 26 °C isotherm depths, mixed-layer depth and cyclone heat potential.',
    chips: ['Mondrian 90% band', 'dissimilarity index', 'D20 · D26', 'TCHP'],
  },
  {
    depth: 'Deep · 700–1000 m',
    title: 'And every claim is checked honestly',
    body: 'Training uses 2015–2022, calibration 2023, and 2024–2025 was read once to test hypotheses frozen in advance. No Argo float appears in two periods, independent RAMA moorings give an outside check, and negative results are reported rather than hidden.',
    chips: ['time-blocked + float-grouped', 'frozen hypotheses', 'RAMA moorings'],
    cta: true,
  },
];

function template() {
  return `
  <section class="hero" aria-labelledby="hero-title">
    <div class="hero__copy">
      <p class="eyebrow">SIH 26066 · OceanEmbed · North Indian Ocean</p>
      <h2 class="hero__title" id="hero-title">Reading the ocean's first 1,000 metres <span>from space.</span></h2>
      <p class="hero__lede">AquaSphere reconstructs subsurface temperature profiles across the Arabian Sea and Bay of Bengal
        (5–30°N, 45–105°E, 15 depths to 1000 m) from multi-sensor satellite embeddings,
        and attaches a calibrated 90% interval to every depth.</p>
      <div class="hero__cta">
        <a class="btn" href="#/predict"><svg aria-hidden="true"><use href="assets/icons.svg#i-predict"></use></svg>Predict a profile</a>
        <a class="btn btn--ghost" href="#/explorer"><svg aria-hidden="true"><use href="assets/icons.svg#i-explorer"></use></svg>Check against held-out Argo</a>
      </div>
      <div class="hero__mode" data-ref="mode"></div>
    </div>
    <div class="hero__visual">
      <canvas class="globe-canvas" data-ref="globe" aria-hidden="true"></canvas>
      <div class="globe-labels" data-ref="labels" aria-hidden="true"></div>
      <div class="hero__fallback" data-ref="fallback" hidden></div>
      <p class="hero__legend" data-ref="legend"></p>
    </div>
  </section>

  <section class="grid grid--4" aria-label="Headline results" data-ref="metrics"></section>

  <section class="grid grid--main-side">
    <div class="card" id="system-status">
      <div class="card__head"><div><h3 class="card__title">System status</h3><p class="card__sub">Live from /health and /ready, refreshed every 30 s</p></div><div class="card__meta" data-ref="status-badges"></div></div>
      <dl class="kv" data-ref="status"></dl>
    </div>
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Read this first</h3><p class="card__sub">What the numbers on this site are, and are not</p></div></div>
      <ul class="plain-list">
        <li>Every chart carries a source badge: <span class="badge badge--local">Local store</span> <span class="badge badge--cache">Disk cache</span> <span class="badge badge--live">Live</span> <span class="badge badge--demo">Offline demo (synthetic)</span> <span class="badge badge--results">Results file</span></li>
        <li>The API's local surface store is a synthetic fixture, so it reports <em>offline_synthetic</em>; those badges say so rather than "Local store".</li>
        <li>If the API returns 503 the view says <strong>Data unavailable</strong>. Nothing is filled in.</li>
        <li>Experiments without results are marked <strong>Pending</strong>.</li>
      </ul>
    </div>
  </section>

  <section class="descent" data-ref="descent" aria-label="How AquaSphere works, from surface to 1000 m">
    <div class="descent__stages" data-ref="stages"></div>
    <aside class="gauge glass" aria-label="Depth gauge" data-ref="gauge">
      <div class="gauge__track" data-ref="track"><div class="gauge__fill" data-ref="fill"></div><div class="gauge__marker" data-ref="marker"></div></div>
      <div class="gauge__readout">
        <div class="gauge__depth mono" data-ref="depth" aria-live="off">0 m</div>
        <div class="gauge__temp mono" data-ref="temp">—</div>
        <div class="gauge__where" data-ref="where"></div>
      </div>
    </aside>
  </section>`;
}

function metricCard({ label, value, digits, suffix, note, extra }) {
  const c = h(`<div class="card stat-card"><div class="stat"><span class="stat__label"></span><span class="stat__value">—</span><span class="stat__note"></span></div><div class="card__meta"></div></div>`);
  c.querySelector('.stat__label').textContent = label;
  c.querySelector('.stat__note').textContent = note;
  c.querySelector('.card__meta').append(badge('results'), ...(extra || []));
  return { el: c, run: () => countUp(c.querySelector('.stat__value'), value, { digits, suffix }) };
}

/** Headline numbers from protocol v2 (real 2015–2025 data, 2023 validation). */
function renderMetricsV2(host, v2) {
  const ladder = Object.entries(v2.e2);
  const [bestKey, best] = ladder.sort((a, b) => a[1].thermocline_rmse - b[1].thermocline_rmse)[0];
  const b4 = v2.e2.B4?.probabilistic;
  const evalNote = `validation 2023 · ${v2.split.profiles.val} profiles, ${v2.split.floats.val} unseen floats`;
  const cards = [
    metricCard({ label: `Thermocline RMSE · best baseline (${bestKey})`, value: best.thermocline_rmse, digits: 2, suffix: '°C', note: `95% CI ${fmt(best.thermocline_ci_95[0])}–${fmt(best.thermocline_ci_95[1])} °C · ${evalNote}` }),
    metricCard({ label: 'Skill vs climatology · thermocline', value: best.skill_thermocline, digits: 2, note: `${best.name}. 1 − MSE / MSE(B0 climatology); B0 = 0.` }),
    b4 ? metricCard({ label: '90% interval coverage · B4', value: b4.coverage_90 * 100, digits: 1, suffix: '%', note: `Deep-ensemble baseline, nominal 90% · mean width ${fmt(b4.mean_width_90, 2)} °C` }) : null,
    metricCard({ label: `D20 error · ${bestKey}`, value: best.d20_rmse_m, digits: 1, suffix: 'm', note: `20 °C isotherm depth, computed the same way on observed and predicted profiles (n = ${best.d20_n})` }),
  ].filter(Boolean);
  host.replaceChildren(...cards.map((c) => c.el));
  const n = h('<p class="note span-all"></p>');
  n.textContent = `These are the protocol-v2 baselines on real 2015–2025 data (train 2015–22, validation 2023; the 2024–25 test period stays locked). AquaSphere's own model is retrained on this data in Phase 4 and must beat ${bestKey} to earn a claim. Full ladder in Experiments.`;
  host.append(n);
  cards.forEach((c) => c.run());
}

/** Phase 6: what the one read of the 2024-25 test period showed. */
function renderFinal(host, f, p4) {
  const a = f.ladder['Tier A v2'];
  const h3 = f.hypotheses.H3;
  const supported = Object.values(f.hypotheses).filter((x) => x.supported).length;
  const evalNote = `test 2024–25 · ${f.split.test_profiles.toLocaleString()} profiles, ${f.split.test_floats} unseen floats`;
  const cards = [
    metricCard({ label: 'Thermocline RMSE · test period', value: a.thermocline_rmse, digits: 2, suffix: '°C', note: `95% CI ${fmt(a.ci[0])}–${fmt(a.ci[1])} °C · ${evalNote}` }),
    metricCard({ label: 'Skill vs climatology · test', value: a.skill_thermocline, digits: 2, note: `Validation 2023 was ${fmt(p4.e7.skill_delayed, 2)}. 1 − MSE / MSE(B0).` }),
    metricCard({ label: '90% interval coverage · test', value: h3.coverage * 100, digits: 1, suffix: '%', note: `95% CI ${(h3.ci[0] * 100).toFixed(1)}–${(h3.ci[1] * 100).toFixed(1)}% · H3 target 87–93%` }),
    metricCard({ label: 'Frozen hypotheses supported', value: supported, digits: 0, suffix: '/5', note: 'Holm-corrected, thresholds fixed before the test period was read' }),
  ];
  host.replaceChildren(...cards.map((c) => c.el));
  const n = h('<p class="note span-all"></p>');
  n.textContent = 'These numbers come from the single, logged read of the 2024–25 test period with the model trained on 2015–22 and calibrated on 2023. Every hypothesis result, supported or not, is in Experiments.';
  host.append(n);
  cards.forEach((c) => c.run());
}

/** Phase 4: the served Tier A v2 model next to the strongest protocol-v2 baseline. */
function renderPhase4(host, p4, v2) {
  const served = p4.e7.delayed;
  const [bestKey, best] = Object.entries(v2.e2).sort((a, b) => a[1].thermocline_rmse - b[1].thermocline_rmse)[0];
  const cov = p4.e6.methods.conformal_mondrian.coverage[0];
  const evalNote = `validation 2023 · ${p4.split.val_profiles} profiles, ${p4.split.val_floats} unseen floats`;
  const cards = [
    metricCard({ label: 'Thermocline RMSE · Tier A v2', value: served.thermocline_rmse, digits: 2, suffix: '°C', note: `95% CI ${fmt(served.ci[0])}–${fmt(served.ci[1])} °C · ${evalNote}` }),
    metricCard({ label: 'Skill vs climatology · thermocline', value: p4.e7.skill_delayed, digits: 2, note: `Best baseline ${bestKey}: ${fmt(best.skill_thermocline, 2)}. 1 − MSE / MSE(B0); B0 = 0.` }),
    metricCard({ label: '90% interval coverage · Mondrian', value: cov.coverage * 100, digits: 1, suffix: '%', note: `95% CI ${(cov.ci_low * 100).toFixed(1)}–${(cov.ci_high * 100).toFixed(1)}% · out-of-fold over floats` }),
    metricCard({ label: 'Skill retained in nowcast', value: p4.e7.skill_ratio * 100, digits: 0, suffix: '%', note: `SST + SLA only vs all sensors · 95% CI ${(p4.e7.skill_ratio_ci[0] * 100).toFixed(0)}–${(p4.e7.skill_ratio_ci[1] * 100).toFixed(0)}%` }),
  ];
  host.replaceChildren(...cards.map((c) => c.el));
  const overlap = served.ci[0] <= best.thermocline_ci_95[1] && best.thermocline_ci_95[0] <= served.ci[1];
  const n = h('<p class="note span-all"></p>');
  n.textContent = `Tier A v2 is the served model: trained on 2015–22, calibrated on 2023, test period still locked. Against the best baseline ${bestKey} (${fmt(best.thermocline_rmse)} °C) its thermocline RMSE is ${fmt(served.thermocline_rmse)} °C`
    + (overlap ? '; the confidence intervals overlap, so on validation it is not shown to be better.' : '.')
    + ' Details in Experiments, Sensors & Modes and Uncertainty.';
  host.append(n);
  cards.forEach((c) => c.run());
}

async function renderMetrics(root, ctx) {
  const host = $(root, '[data-ref="metrics"]');
  host.innerHTML = '<div class="card skeleton" style="min-height:130px"></div>'.repeat(4);
  const [v2, p4] = await Promise.all([
    api.results('metrics_v2').catch(() => null),
    api.results('phase4').catch(() => null),
  ]);
  if (ctx.signal.aborted) return;
  const final = await api.results('final_eval').catch(() => null);
  if (ctx.signal.aborted) return;
  if (final && !final.dry_run && p4?.e7) return renderFinal(host, final, p4);
  if (v2 && p4?.e7) return renderPhase4(host, p4, v2);
  if (v2) return renderMetricsV2(host, v2);
  let metrics;
  let ablation;
  try {
    [metrics, ablation] = await Promise.all([api.results('metrics'), api.results('ablation').catch(() => null)]);
  } catch {
    host.innerHTML = '';
    const c = h('<div class="card span-2"></div>');
    host.append(c);
    (await import('../ui/loaders.js')).pending(c, { title: 'Results file missing', detail: 'web/data/metrics.json could not be loaded. Run "make ui-data" after evaluation.' });
    return;
  }
  if (ctx.signal.aborted) return;
  const m = metrics.baselines[MODEL_KEY];
  const best = Object.entries(metrics.baselines).sort((a, b) => a[1].thermocline_rmse - b[1].thermocline_rmse)[0];
  // Only runs with real inputs count: the audit may have proven the others used synthetic channels.
  const synthetic = await ablationSyntheticChannels();
  const realRuns = (ablation?.results || []).filter((r) => !synthetic.length || ['sla', 'sss', 'wind'].every((s) => r[s] !== 'Yes'));
  const cov = realRuns.length ? realRuns.reduce((a, r) => a + r.coverage_mean, 0) / realRuns.length : null;
  const covNote = synthetic.length
    ? `Empirical, nominal 90% · ${realRuns.map((r) => r.run).join(', ')} only (n = ${ablation.n_val}); runs with synthetic inputs excluded`
    : `Empirical, nominal 90% · ablation validation set (n = ${ablation?.n_val})`;
  const evalNote = `${metrics.n_eval_profiles} held-out profiles from ${metrics.n_eval_floats} floats`;

  const cards = [
    metricCard({ label: 'Thermocline RMSE · 50–150 m', value: m.thermocline_rmse, digits: 2, suffix: '°C', note: `95% CI ${fmt(m.thermocline_ci_95[0])}–${fmt(m.thermocline_ci_95[1])} °C · ${evalNote}` }),
    metricCard({ label: 'Skill vs climatology', value: m.skill_score_overall, digits: 2, note: `1 − MSE / MSE(climatology), all depths. Climatology = 0.` }),
    cov == null
      ? null
      : metricCard({ label: '90% interval coverage', value: cov * 100, digits: 1, suffix: '%', note: covNote }),
    metricCard({ label: 'D20 / MLD error', value: m.d20_rmse, digits: 1, suffix: 'm', note: `D20 RMSE · MLD RMSE ${fmt(m.mld_rmse, 1)} m` }),
  ].filter(Boolean);

  host.replaceChildren(...cards.map((c) => c.el));
  if (best[0] !== MODEL_KEY) {
    const n = h('<p class="note span-all"></p>');
    n.textContent = `Honest comparison: on this split the strongest model is "${best[0]}" (thermocline RMSE ${fmt(best[1].thermocline_rmse)} °C) versus ${fmt(m.thermocline_rmse)} °C for OceanEmbedNet v1. Full ladder in Experiments.`;
    host.append(n);
  }
  cards.forEach((c) => c.run());
}

function renderStatus(root) {
  const dl = $(root, '[data-ref="status"]');
  const s = state;
  const yes = (v) => (v == null ? '—' : v ? 'yes' : 'no');
  const rows = [
    ['API', s.api === 'ok' ? 'healthy · ready' : s.api === 'degraded' ? 'up · not ready' : s.api === 'down' ? 'unreachable' : 'checking…'],
    ['Uptime', s.health ? `${Math.round(s.health.uptime_seconds / 60)} min` : '—'],
    ['Weights', s.ready?.details?.weights === 'untrained' ? 'UNTRAINED (no checkpoint)' : s.ready?.details?.weights || '—'],
    ['Provenance', s.ready?.details?.provenance_status?.replace('_', ' ') || '—'],
    ['Scaler loaded', yes(s.ready?.scaler_loaded)],
    ['Surface store open', yes(s.ready?.store_open)],
    ['Model version', s.ready?.details?.model_version || s.meta?.model_version || '—'],
    ['Data version', s.ready?.details?.data_version || s.meta?.data_version || '—'],
    ['Date range (/meta)', s.meta && !s.meta._demo ? `${s.meta.min_date} → ${s.meta.max_date}` : '—'],
    ['Selected date', s.date || '—'],
    ['Mode', s.mode === 'nowcast' ? 'Nowcast (SST + SLA)' : 'Delayed (all sensors)'],
    ['Data mode', s.demo ? 'Offline demo (synthetic)' : 'API'],
  ];
  dl.replaceChildren();
  for (const [k, v] of rows) {
    const dt = document.createElement('dt');
    const dd = document.createElement('dd');
    dt.textContent = k;
    dd.textContent = v;
    dl.append(dt, dd);
  }
  const badges = $(root, '[data-ref="status-badges"]');
  badges.replaceChildren(
    s.api === 'ok' ? tag('Ready', 'ok') : s.api === 'down' ? tag('Offline', 'unavailable') : s.api === 'degraded' ? tag('Degraded', 'warn') : tag('Checking', 'muted'),
    ...(s.demo ? [badge('demo_synthetic')] : []),
  );

  const mode = $(root, '[data-ref="mode"]');
  mode.replaceChildren(
    tag(s.mode === 'nowcast' ? 'Nowcast mode · SST + SLA' : 'Delayed mode · all sensors', 'heldout', 'Switch in the top bar. Affects the Sensors & Modes view.'),
    ...(s.demo ? [badge('demo_synthetic')] : []),
  );
}

async function initHero(root, ctx) {
  const canvas = $(root, '[data-ref="globe"]');
  const legend = $(root, '[data-ref="legend"]');
  const floatsData = await api.results('floats').catch(() => null);
  const floats = floatsData?.floats || [];
  legend.innerHTML = '<span class="dot dot--float"></span><span data-ref="nf"></span> <span class="dot dot--box"></span>Study domain';
  legend.querySelector('[data-ref="nf"]').textContent = floats.length
    ? `${floats.length} Argo floats, last reported position (${floatsData.source.split('/').pop()})`
    : 'Float positions unavailable';

  if (!allow3D()) {
    canvas.hidden = true;
    const fb = $(root, '[data-ref="fallback"]');
    fb.hidden = false;
    const { createMap } = await import('../ui/map.js');
    const map = await createMap(fb, { label: 'Study domain with Argo float positions' });
    map.setPoints(floats.map((f) => ({ id: f.id, lat: f.lat, lon: f.lon, r: 0.35, color: '#67e8f9', label: `Float ${f.id} · ${f.date}` })));
    return;
  }

  const [{ createGlobe }, landData] = await Promise.all([import('../three/globe.js'), api.asset('land_globe.json')]);
  if (ctx.signal.aborted) return;
  const globe = createGlobe(canvas, {
    land: landData?.rings || [],
    floats,
    domain: state.meta?.domain || DOMAIN,
    labelsEl: $(root, '[data-ref="labels"]'),
    reduced: state.reduced,
  });
  ctx.cleanup(() => globe.dispose());
  // Only render while the hero is on screen
  const io = new IntersectionObserver(([e]) => (e.isIntersecting ? globe.start() : globe.stop()));
  io.observe(canvas);
  ctx.cleanup(() => io.disconnect());
}

function initDescentSection(root, ctx) {
  const stagesEl = $(root, '[data-ref="stages"]');
  STAGES.forEach((s, i) => {
    const el = h(`<article class="stage card" data-stage="${i}">
      <p class="stage__depth mono"></p><h3 class="stage__title"></h3><p class="stage__body"></p><div class="chips"></div></article>`);
    el.querySelector('.stage__depth').textContent = s.depth;
    el.querySelector('.stage__title').textContent = s.title;
    el.querySelector('.stage__body').textContent = s.body;
    el.querySelector('.chips').append(...s.chips.map((c) => { const x = document.createElement('span'); x.className = 'chip'; x.textContent = c; return x; }));
    if (s.cta) el.append(h('<div class="hero__cta"><a class="btn" href="#/experiments">See the experiments</a><a class="btn btn--ghost" href="#/cards">Data &amp; model cards</a></div>'));
    stagesEl.append(el);
  });

  // Gauge ticks at the 15 standard depths
  const track = $(root, '[data-ref="track"]');
  for (const d of DEPTHS) {
    const t = h(`<span class="gauge__tick"><span class="mono"></span></span>`);
    t.style.top = `${depthToProgress(d) * 100}%`;
    t.querySelector('span').textContent = `${d}`;
    track.append(t);
  }

  // Gauge temperature: the model's own profile at the selected point/date, when available.
  let profile = null;
  let profileNote = 'Loading model profile…';
  const where = $(root, '[data-ref="where"]');
  const tempEl = $(root, '[data-ref="temp"]');
  const tempAt = (z) => {
    if (!profile) return null;
    const { depths, temperatures } = profile;
    for (let i = 1; i < depths.length; i++) {
      if (z <= depths[i]) return temperatures[i - 1] + ((temperatures[i] - temperatures[i - 1]) * (z - depths[i - 1])) / (depths[i] - depths[i - 1]);
    }
    return temperatures.at(-1);
  };

  let lastDepth = 0;
  const paintTemp = () => {
    const t = tempAt(lastDepth);
    tempEl.textContent = t == null ? '—' : `${t.toFixed(2)} °C`;
    tempEl.title = profileNote;
  };

  onDate(ctx, async (date) => {
    const { lat, lon } = state.point;
    where.replaceChildren();
    if (!date) { profile = null; profileNote = 'API offline'; where.textContent = 'Model temperature unavailable (API offline)'; paintTemp(); return; }
    try {
      profile = await api.predict({ lat, lon, date }, { signal: ctx.signal });
      profileNote = 'Model prediction';
      const label = document.createElement('span');
      label.textContent = `Model, ${fmtLat(lat)} ${fmtLon(lon)}, ${date} `;
      where.append(label, badge(profile.data_source));
    } catch (err) {
      if (ctx.signal.aborted) return;
      profile = null;
      profileNote = err.kind === 'unavailable' ? 'Data unavailable (503)' : 'API unreachable';
      const note = document.createElement('span');
      note.textContent = `${profileNote} `;
      where.append(note, badge(err.kind === 'unavailable' ? 'unavailable' : 'offline'));
    }
    paintTemp();
  });

  const fill = $(root, '[data-ref="fill"]');
  const marker = $(root, '[data-ref="marker"]');
  const depthEl = $(root, '[data-ref="depth"]');
  const stageEls = [...stagesEl.children];
  const kill = initDescent($(root, '[data-ref="descent"]'), (p, depth) => {
    lastDepth = depth;
    fill.style.height = `${p * 100}%`;
    marker.style.top = `${p * 100}%`;
    depthEl.textContent = `${Math.round(depth)} m`;
    setDepth(p);
    paintTemp();
  }, {
    stages: stageEls,
    reduced: state.reduced || state.perf,
    onStage: (i) => stageEls.forEach((el, k) => el.classList.toggle('is-active', k === i)),
  });
  ctx.cleanup(() => { kill(); setDepth(0); });
}

export default {
  async mount(root, ctx) {
    root.classList.add('page--overview');
    root.innerHTML = template();
    renderStatus(root);
    onState(ctx, ['api', 'health', 'ready', 'meta', 'date', 'mode', 'demo'], () => renderStatus(root));
    initDescentSection(root, ctx);
    await Promise.all([renderMetrics(root, ctx), initHero(root, ctx)]);
    reveal(root, ctx, '.grid > .card');
  },
};
