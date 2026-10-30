import { state } from '../state.js';
import * as api from '../api.js';
import { badge, tag } from '../ui/badges.js';
import { pending } from '../ui/loaders.js';
import { C, plot } from '../charts/theme.js';
import { card, h, $, onState, reveal } from './_util.js';

// Input independence audit (blueprint §10.1): does a product already contain Argo or other
// in-situ T/S, and how is that handled?
const AUDIT_TAG = {
  label: ['Label source', 'ok'],
  verified: ['Verified', 'warn'],
  documented: ['Documented', 'muted'],
  'to-verify': ['To verify', 'pending'],
  fixture: ['Fixture', 'warn'],
};
const SOURCES = [
  { name: 'Argo floats', provider: 'Argo GDAC via Argovis', use: 'Labels: temperature at 15 depths', res: 'Profiles', status: 'label', contains: '—', handling: 'Every float in exactly one split (assert_no_leakage); leakage gap measured in E1.' },
  { name: 'NOAA OISST v2.1', provider: 'NOAA NCEI / ERDDAP', use: 'Input: SST', res: '0.25°, daily', status: 'verified', contains: 'Yes: blends ships, buoys and Argo near-surface values (above ~5 m)', handling: 'Headline skill at 20 m and below; 0–10 m reported separately and flagged.' },
  { name: 'ARMOR3D', provider: 'Copernicus Marine', use: 'Not used (reference only)', res: '0.25°, weekly', status: 'documented', contains: 'Yes: merges satellite fields with in-situ profiles', handling: 'Never an input or target; mooring comparison only (B5, E8).' },
  { name: 'Reanalyses (e.g. GLORYS12)', provider: 'Copernicus Marine', use: 'Not used', res: '1/12°', status: 'documented', contains: 'Yes: assimilate in-situ profiles', handling: 'Not used as training targets; Argo is the label source.' },
  { name: 'NASA SMAP L3 SSS', provider: 'NASA PO.DAAC / RSS', use: 'Input: SSS', res: '0.25°, 8-day', status: 'to-verify', contains: 'Possibly: some products are bias-adjusted with in-situ salinity', handling: 'E3 reported with and without SSS.' },
  { name: 'CMEMS DUACS L4', provider: 'Copernicus Marine', use: 'Input: SLA, geostrophic u/v', res: '0.25°, daily', status: 'to-verify', contains: 'Not expected', handling: 'Confirm in product documentation.' },
  { name: 'ERA5 / CCMP v3', provider: 'ECMWF / RSS', use: 'Input: 10 m wind (delayed mode)', res: '0.25°, daily', status: 'to-verify', contains: 'Not expected', handling: 'Confirm in product documentation; masked in nowcast mode.' },
  { name: 'Local surface store', provider: 'data/store/surface.zarr', use: 'What the API serves first', res: '0.25°, 13 dates', status: 'fixture', contains: 'n/a', handling: 'The API reports it as offline_synthetic: a fixture, not real satellite fields.' },
];

const LIMITATIONS = [
  'Decision-support prototype. Not validated for navigation, safety-critical offshore work or search and rescue without independent INCOIS verification.',
  'Validation 2023 is small once floats seen in training are excluded: 761 profiles from 37 floats. Every Bay of Bengal stratum is too small for claims and is reported descriptively.',
  'OISST contains Argo near-surface values, so errors at 0–10 m are not an independent test. Protocol v2 reports 0–10 m as its own band and headline skill at 20 m and below; the older v1 metrics files still group 0–30 m together.',
  'Under protocol v2 the retrained v1 network (B3) is not distinguishable from climatology; LightGBM (B2) and the deep ensemble (B4) set the bar AquaSphere has to beat, and the B4 90% intervals under-cover (83.8%).',
  'Nowcast mode is evaluated on the final OISST release. The preliminary near-real-time release it would see in live use is replaced after about two weeks and no longer exists for 2023, so that shift is untested until a prospective run.',
  'Time series and drift views use only dates held in the local surface store; dates outside it are not fetched live for a series.',
];

/** Limitations that depend on which checkpoint the API is serving right now. */
function servedLimitations(modelVersion) {
  if (String(modelVersion || '').startsWith('tier_a_v2')) {
    return [
      'The served model is Tier A v2: trained on 2015–2022 only, calibrated per region and monsoon season on 2023. Its validation numbers are in Experiments and Uncertainty; the 2024–25 test period has not been read.',
      'Calibration strata in the Bay of Bengal have 12–14 floats each, so their coverage estimates are wide; the conformal calibrator falls back to region or global quantiles where a stratum has fewer than 30 scores at a depth.',
    ];
  }
  return [
    'The served checkpoint is the v1 model, trained on tables whose SSS, SLA, current and wind columns came from the synthetic demo store (proven by the audit above), with an 80/20 float split of a 2025 snapshot. Run make eval-phase4 to train and serve Tier A v2.',
    'The v1 model reports no dissimilarity index, so the applicability-domain views stay pending while it is served.',
  ];
}

function kv(dl, rows) {
  dl.replaceChildren();
  for (const [k, v] of rows) {
    const dt = document.createElement('dt'); dt.textContent = k;
    const dd = document.createElement('dd'); dd.textContent = v ?? '—';
    dl.append(dt, dd);
  }
}

export default {
  async mount(root, ctx) {
    root.innerHTML = `
      <div class="page__intro"><h2>Data &amp; model cards</h2>
        <p>Provenance for everything on this site: which data, which model build, which split, and what is known not to work.</p>
        <div class="hero__cta no-print"><button class="btn" data-ref="export"><svg aria-hidden="true"><use href="assets/icons.svg#i-export"></use></svg>Export report (PDF)</button></div></div>
      <div class="grid grid--2" data-ref="row1"></div>
      <div data-ref="row2"></div>
      <div class="grid grid--2" data-ref="row3"></div>`;
    $(root, '[data-ref="export"]').addEventListener('click', () => document.getElementById('export-btn').click());

    const [info, metrics, heldout] = await Promise.all([
      api.results('build_info').catch(() => null),
      api.results('metrics').catch(() => null),
      api.results('heldout').catch(() => null),
    ]);

    // Model card
    const model = card({ title: 'Model card', sub: 'Live from /ready and /meta, plus the build that produced this page' });
    model.body.innerHTML = '<dl class="kv"></dl>';
    const paintModel = () => {
      model.meta.replaceChildren(state.ready ? tag('Live /ready', 'live') : tag('API offline', 'unavailable'), ...(info ? [badge('results')] : []));
      const d = state.ready?.details || {};
      kv(model.body.firstChild, [
        ['Serving model', d.model_version || state.meta?.model_version],
        ['Serving data version', d.data_version || state.meta?.data_version],
        ['Checkpoint', d.checkpoint_path],
        ['Weights', d.weights],
        ['Provenance', d.provenance_status ? `${d.provenance_status.replace('_', ' ')}: ${d.provenance_detail}` : null],
        ['Trained at commit', d.git_sha ? d.git_sha.slice(0, 12) : 'not recorded in checkpoint'],
        ['Training data SHA-256', d.data_sha256 ? d.data_sha256.slice(0, 16) + '…' : 'not recorded in checkpoint'],
        ['Training split', d.training_membership],
        ['Evaluated model', metrics ? `${metrics.model_version} (metrics.json)` : null],
        ['Evaluated data', metrics?.data_version],
        ['Web data built at commit', info?.git_sha ? `${info.git_sha.slice(0, 12)}${info.git_dirty ? ' (uncommitted changes)' : ''}` : 'not recorded'],
        ['Branch', info?.git_branch],
        ['Web data built', info?.generated_at],
        ['Architecture', String(d.model_version || '').startsWith('tier_a_v2')
          ? '18 inputs (7 sensors + availability flags, position, season) → 16-d L2-normalised embedding → heteroscedastic anomaly decoder over the 2015–2022 climatology → Mondrian conformal 90% by region × season, per mode → dissimilarity index'
          : 'Encoder → 16-d L2-normalised embedding → heteroscedastic decoder (15 depths, mean + σ) → split conformal 90%'],
      ]);
    };
    paintModel();
    onState(ctx, ['ready', 'meta'], paintModel);

    // Splits: protocol v2 once its results exist, else the old snapshot split
    const split = card({ title: 'Training & evaluation split', sub: 'What was documented vs what the data allows' });
    const v2 = await api.results('metrics_v2').catch(() => null);
    if (v2) {
      split.card.querySelector('.card__sub').textContent = 'Protocol v2: time-blocked and float-grouped, as the blueprint specifies';
      split.meta.append(badge('results'), tag('Test locked', 'heldout', 'Read once, in the final evaluation (roadmap Phase 6).'));
      const p = v2.split.profiles;
      const total = p.train + p.val + p.test;
      const w = (k) => `${((p[k] / total) * 100).toFixed(1)}%`;
      split.body.innerHTML = `
        <div class="split-bar" role="img" aria-label="Train ${p.train} profiles, validation ${p.val}, test ${p.test}">
          <div style="width:${w('train')};background:${C.teal}">Train 2015–22 · ${p.train.toLocaleString()}</div>
          <div style="width:${w('val')};min-width:3.5em;background:${C.amber}" title="Validation 2023">${p.val}</div>
          <div style="width:${w('test')};min-width:4.5em;background:${C.coral}" title="Test 2024–25 (locked)">${p.test.toLocaleString()}</div></div>
        <p class="card__foot"></p><p class="note"></p>`;
      split.body.querySelector('.card__foot').textContent = `Profiles in each partition: train ${p.train.toLocaleString()} (${v2.split.floats.train} floats), validation 2023 ${p.val} (${v2.split.floats.val} floats), test 2024–25 ${p.test.toLocaleString()} (${v2.split.floats.test} floats).`;
      split.body.querySelector('.note').textContent = `Every float belongs to the first period it appears in, so ${v2.split.dropped_profiles.val.toLocaleString()} validation-year and ${v2.split.dropped_profiles.test.toLocaleString()} test-year profiles from floats already seen earlier are excluded. Hypotheses were frozen before the test period was read (docs/hypotheses.yaml).`;
    } else if (metrics) {
      split.meta.append(badge('results'));
      const n = metrics.n_train_profiles + metrics.n_eval_profiles;
      const tr = (metrics.n_train_profiles / n) * 100;
      split.body.innerHTML = `
        <div class="stat__label">Used for evaluation · ${metrics.split}</div>
        <div class="split-bar" role="img" aria-label="Training ${metrics.n_train_profiles} profiles, held-out ${metrics.n_eval_profiles} profiles">
          <div style="width:${tr}%;background:${C.teal}">Train ${metrics.n_train_profiles}</div>
          <div style="width:${100 - tr}%;background:${C.cyan}" title="Held out ${metrics.n_eval_profiles}">${metrics.n_eval_profiles}</div></div>
        <p class="card__foot">Float-grouped 70 / 15 / 15 by float ID, seed 42. Held-out = validation partition (${metrics.n_eval_floats} floats); test partition kept aside.</p>
        <div class="stat__label" style="margin-top:var(--sp-3)">Documented temporal split</div>
        <div class="split-bar" style="opacity:.55"><div style="width:61%;background:${C.teal}">Train 2015–22</div><div style="width:13%;background:${C.amber}">Val 2023</div><div style="width:26%;background:${C.coral}">Test 2024–25</div></div>
        <p class="note note--warn"></p>`;
      const art = info?.artifacts?.find((a) => a.date_range);
      split.body.querySelector('.note').textContent = art
        ? `Not used: the Argo archive only spans ${art.date_range[0]} → ${art.date_range[1]}, so a 2015–2025 temporal split is not possible with the data in this repository.`
        : 'Not used: the archive date range could not be read from build_info.json.';
    } else {
      pending(split.body, { needs: 'web/data/metrics.json' });
    }
    $(root, '[data-ref="row1"]').append(model.card, split.card);

    // Sources
    const src = card({ title: 'Data sources & independence audit', sub: 'Whether each input could leak information about the labels' });
    src.body.innerHTML = '<div class="table-wrap" tabindex="0" role="region" aria-label="Data sources and independence audit"><table class="table"><thead><tr><th>Source</th><th>Role</th><th>Resolution</th><th>Contains Argo / in-situ?</th><th>Audit</th><th>Handling</th></tr></thead><tbody></tbody></table></div>';
    for (const s of SOURCES) {
      const tr = h('<tr><td></td><td></td><td class="mono"></td><td></td><td></td><td></td></tr>');
      tr.cells[0].textContent = s.name;
      const prov = document.createElement('div');
      prov.className = 'card__foot';
      prov.textContent = s.provider;
      tr.cells[0].append(prov);
      [s.use, s.res, s.contains].forEach((v, i) => { tr.cells[i + 1].textContent = v; });
      const [label, cls] = AUDIT_TAG[s.status];
      tr.cells[4].append(tag(label, cls));
      tr.cells[5].textContent = s.handling;
      src.body.querySelector('tbody').append(tr);
    }
    $(root, '[data-ref="row2"]').append(src.card);

    // Synthetic-input audit: proven by re-collocating each table against the demo store
    const audit = await api.results('input_audit').catch(() => null);
    const aud = card({ title: 'Synthetic-input audit', sub: 'Which tables carry satellite columns copied from the synthetic demo store' });
    if (audit) {
      aud.meta.append(badge('results'));
      aud.body.innerHTML = '<div class="table-wrap" tabindex="0" role="region" aria-label="Synthetic-input audit"><table class="table"><thead><tr><th>Table</th><th>Used by</th><th>Result</th><th>Synthetic columns</th></tr></thead><tbody></tbody></table></div><p class="card__foot"></p>';
      const label = {
        synthetic_found: ['Synthetic inputs', 'warn'],
        clean: ['Clean', 'ok'],
        no_satellite_columns: ['SST only', 'ok'],
        not_checked: ['Not checked', 'muted'],
        store_not_synthetic: ['Not applicable', 'muted'],
      };
      for (const t of audit.tables) {
        const tr = h('<tr><td class="mono"></td><td></td><td></td><td class="mono"></td></tr>');
        tr.cells[0].textContent = t.table;
        tr.cells[1].textContent = t.used_by;
        const [text, cls] = label[t.status] || [t.status, 'muted'];
        tr.cells[2].append(tag(text, cls));
        tr.cells[3].textContent = t.synthetic_channels.join(', ') || '—';
        aud.body.querySelector('tbody').append(tr);
      }
      aud.body.querySelector('.card__foot').textContent = `Method: ${audit.tables[0]?.method || '—'}. Generated ${audit.generated_at}.`;
    } else {
      aud.meta.append(badge('pending'));
      pending(aud.body, { needs: 'web/data/input_audit.json (python scripts/build_web_data.py)' });
    }
    $(root, '[data-ref="row2"]').append(aud.card);

    // Coverage of the real multi-year data (aquasphere.data.coverage)
    const cov = await api.results('data_coverage').catch(() => null);
    const covCard = card({ title: 'Data coverage · real 2015–2025 data', sub: 'What the open-data surface store and the Argo archive actually contain' });
    if (cov) {
      covCard.meta.append(badge('results'));
      const s = cov.store;
      const a = cov.argo;
      covCard.body.innerHTML = `
        <div class="grid grid--2">
          <div><div class="stat__label">Surface store · ${s.first} → ${s.last} · ${s.n_dates} days</div>
            <div class="table-wrap" tabindex="0" role="region" aria-label="Satellite variable coverage"><table class="table"><thead><tr><th>Variable</th><th class="num">Days with data</th><th>From</th></tr></thead><tbody data-ref="vars"></tbody></table></div></div>
          <div><div class="stat__label" data-ref="argo-head"></div><div class="chart chart--short" data-ref="years"></div></div>
        </div>
        <div class="table-wrap" tabindex="0" role="region" aria-label="Argo profiles by basin and season"><table class="table"><thead><tr><th>Basin · season</th><th class="num">Profiles</th></tr></thead><tbody data-ref="strata"></tbody></table></div>
        <p class="card__foot" data-ref="foot"></p>`;
      for (const [v, info] of Object.entries(s.variables)) {
        const tr = h('<tr><td class="mono"></td><td class="num"></td><td class="mono"></td></tr>');
        [v, info.days_with_data, info.first_day || '—'].forEach((x, i) => { tr.cells[i].textContent = x; });
        $(covCard.body, '[data-ref="vars"]').append(tr);
      }
      for (const [k, n] of Object.entries(a.by_region_season).sort()) {
        const tr = h('<tr><td></td><td class="num"></td></tr>');
        tr.cells[0].textContent = k.replace(' | ', ' · ');
        tr.cells[1].textContent = n.toLocaleString();
        $(covCard.body, '[data-ref="strata"]').append(tr);
      }
      $(covCard.body, '[data-ref="argo-head"]').textContent = `Argo · ${a.profiles.toLocaleString()} profiles from ${a.floats} floats · ${a.first} → ${a.last}`;
      const modes = a.by_data_mode ? Object.entries(a.by_data_mode).map(([k, n]) => `${{ D: 'delayed', A: 'adjusted', R: 'real-time' }[k] || k} ${n.toLocaleString()}`).join(' · ') : '';
      const chans = a.channel_availability ? Object.entries(a.channel_availability).map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`).join(', ') : '';
      $(covCard.body, '[data-ref="foot"]').textContent = [modes && `Data mode: ${modes}.`, chans && `Channel availability at profiles: ${chans}.`, `Generated ${cov.generated_at}.`].filter(Boolean).join(' ');
      const years = Object.keys(a.by_year);
      plot($(covCard.body, '[data-ref="years"]'), [{
        type: 'bar', x: years, y: years.map((y) => a.by_year[y]), marker: { color: C.teal },
        hovertemplate: '%{x}: %{y} profiles<extra></extra>',
      }], { yaxis: { title: { text: 'Profiles' } }, margin: { l: 56, r: 8, t: 8, b: 32 }, showlegend: false }, ctx, 'aquasphere-argo-by-year');
    } else {
      covCard.meta.append(badge('pending'));
      pending(covCard.body, { title: 'Pending', detail: 'The real 2015–2025 data has not been built on this machine yet.', needs: 'make data && make ui-data' });
    }
    $(root, '[data-ref="row2"]').append(covCard.card);

    // Artifacts + limitations
    const arts = card({ title: 'Data artefacts', sub: 'SHA-256 from data/manifest.json, re-verified when the web data was built' });
    if (info?.artifacts?.length) {
      arts.meta.append(badge('results'));
      arts.body.innerHTML = '<div class="table-wrap" tabindex="0" role="region" aria-label="Data artefacts and hashes"><table class="table"><thead><tr><th>Artefact</th><th>Rows / dates</th><th>SHA-256</th><th>Check</th></tr></thead><tbody></tbody></table></div>';
      for (const a of info.artifacts) {
        const tr = h('<tr><td></td><td class="mono"></td><td class="mono" style="word-break:break-all;font-size:11px"></td><td></td></tr>');
        tr.cells[0].textContent = a.path;
        tr.cells[1].textContent = [a.row_count, a.date_range?.join(' → ')].filter(Boolean).join(' · ') || (a.key === 'heldout_store' ? `${heldout?.profiles?.length ?? '—'} profiles` : '—');
        tr.cells[2].textContent = a.sha256 || '—';
        tr.cells[3].append(a.verified === true ? tag('Matches manifest', 'ok') : a.verified === false ? tag('Mismatch', 'unavailable') : tag('Not in manifest', 'muted'));
        arts.body.querySelector('tbody').append(tr);
      }
    } else {
      pending(arts.body, { needs: 'web/data/build_info.json (python scripts/build_web_data.py)' });
    }
    const lim = card({ title: 'Known limitations', sub: 'Found while building this interface; stated rather than hidden' });
    lim.body.innerHTML = '<ul class="plain-list"></ul>';
    const paintLimits = () => {
      const items = [...servedLimitations(state.ready?.details?.model_version || state.meta?.model_version), ...LIMITATIONS];
      lim.body.firstChild.replaceChildren(...items.map((t) => { const li = document.createElement('li'); li.textContent = t; return li; }));
    };
    paintLimits();
    onState(ctx, ['ready', 'meta'], paintLimits);
    $(root, '[data-ref="row3"]').append(arts.card, lim.card);
    reveal(root, ctx, '.card');
  },
};
