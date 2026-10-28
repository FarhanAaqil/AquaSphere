import { state } from '../state.js';
import * as api from '../api.js';
import { badge, tag } from '../ui/badges.js';
import { pending } from '../ui/loaders.js';
import { C } from '../charts/theme.js';
import { card, h, $, onState, reveal } from './_util.js';

// Sensor inventory. Independence status records what has actually been checked in this repo.
const SOURCES = [
  { name: 'Argo floats', provider: 'Argo GDAC via Argovis', use: 'Labels: temperature at 15 depths', res: 'Profiles', audit: ['ok', 'Float-grouped split, no float in two partitions (assert_no_leakage); leakage gap measured in E1'] },
  { name: 'NOAA OISST v2.1', provider: 'NOAA NCEI / ERDDAP', use: 'Input: SST (live fallback in the API)', res: '0.25°, daily', audit: ['warn', 'OISST assimilates in-situ data incl. Argo near-surface; overlap with labels not audited'] },
  { name: 'CMEMS DUACS L4', provider: 'Copernicus Marine', use: 'Input: SLA, geostrophic u/v', res: '0.25°, daily', audit: ['muted', 'Not audited'] },
  { name: 'NASA SMAP L3', provider: 'NASA PO.DAAC / RSS', use: 'Input: SSS', res: '0.25°, 8-day', audit: ['muted', 'Not audited'] },
  { name: 'ERA5 / CCMP v3', provider: 'ECMWF / RSS', use: 'Input: 10 m wind', res: '0.25°, daily', audit: ['muted', 'Not audited'] },
  { name: 'Local surface store', provider: 'data/store/surface.zarr', use: 'What the API serves first', res: '0.25°, 13 dates', audit: ['warn', 'API reports it as offline_synthetic: a fixture, not real satellite fields'] },
];

const LIMITATIONS = [
  'Decision-support prototype. Not validated for navigation, safety-critical offshore work or search and rescue without independent INCOIS verification.',
  'The API\'s local surface store reports offline_synthetic, so live-looking predictions on this site are driven by fixture inputs unless the source badge says Disk cache or Live.',
  'The Argo archive covers 2025-03-25 → 2025-09-15 only. The documented temporal split (train 2015–22 / val 2023 / test 2024–25) cannot be run on it, so evaluation uses a float-grouped split instead.',
  'The /validation/profile lookup store (tests/fixtures/argo_200.parquet) mostly contains training floats: 141 of its 200 profiles. The Profile Explorer hides and labels them.',
  'The API sets in_training_set = false unconditionally, so per-prediction training membership cannot be trusted from the API alone.',
  'The validation endpoint fills missing depths with 0.0 °C and includes them in its RMSE. The explorer recomputes RMSE on observed depths only.',
  'On the current split a gradient-boosted tree baseline (HistGBDT) beats OceanEmbedNet v1 on thermocline RMSE.',
  'Interval coverage is identical across all ablation runs (std ≈ 0) on 38 validation profiles; calibration evidence is thin.',
  'No dissimilarity index or reliability diagram exists yet; those views are pending.',
];

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
      kv(model.body.firstChild, [
        ['Serving model', state.ready?.details?.model_version || state.meta?.model_version],
        ['Serving data version', state.ready?.details?.data_version || state.meta?.data_version],
        ['Checkpoint', state.ready?.details?.checkpoint_path],
        ['Evaluated model', metrics ? `${metrics.model_version} (metrics.json)` : null],
        ['Evaluated data', metrics?.data_version],
        ['Git SHA', info?.git_sha ? `${info.git_sha.slice(0, 12)}${info.git_dirty ? ' (uncommitted changes)' : ''}` : 'not recorded'],
        ['Branch', info?.git_branch],
        ['Web data built', info?.generated_at],
        ['Architecture', 'Encoder → 16-d L2-normalised embedding → heteroscedastic decoder (15 depths, mean + σ) → split conformal 90%'],
      ]);
    };
    paintModel();
    onState(ctx, ['ready', 'meta'], paintModel);

    // Splits
    const split = card({ title: 'Training & evaluation split', sub: 'What was documented vs what the data allows' });
    if (metrics) {
      split.meta.append(badge('results'));
      const n = metrics.n_train_profiles + metrics.n_eval_profiles;
      const tr = (metrics.n_train_profiles / n) * 100;
      split.body.innerHTML = `
        <div class="stat__label">Used for evaluation · ${metrics.split}</div>
        <div class="split-bar" role="img" aria-label="Training ${metrics.n_train_profiles} profiles, held-out ${metrics.n_eval_profiles} profiles">
          <div style="width:${tr}%;background:${C.teal}">Train ${metrics.n_train_profiles}</div>
          <div style="width:${100 - tr}%;background:${C.cyan}">Held out ${metrics.n_eval_profiles}</div></div>
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
    src.body.innerHTML = '<div class="table-wrap"><table class="table"><thead><tr><th>Source</th><th>Provider</th><th>Role</th><th>Resolution</th><th>Independence audit</th></tr></thead><tbody></tbody></table></div>';
    for (const s of SOURCES) {
      const tr = h('<tr><td></td><td></td><td></td><td class="mono"></td><td></td></tr>');
      [s.name, s.provider, s.use, s.res].forEach((v, i) => { tr.cells[i].textContent = v; });
      tr.cells[4].append(tag(s.audit[0] === 'ok' ? 'Checked' : s.audit[0] === 'warn' ? 'Concern' : 'Not audited', s.audit[0] === 'ok' ? 'ok' : s.audit[0] === 'warn' ? 'warn' : 'muted'));
      const note = document.createElement('div');
      note.className = 'card__foot';
      note.textContent = s.audit[1];
      tr.cells[4].append(note);
      src.body.querySelector('tbody').append(tr);
    }
    $(root, '[data-ref="row2"]').append(src.card);

    // Artifacts + limitations
    const arts = card({ title: 'Data artefacts', sub: 'SHA-256 from data/manifest.json, re-verified when the web data was built' });
    if (info?.artifacts?.length) {
      arts.meta.append(badge('results'));
      arts.body.innerHTML = '<div class="table-wrap"><table class="table"><thead><tr><th>Artefact</th><th>Rows / dates</th><th>SHA-256</th><th>Check</th></tr></thead><tbody></tbody></table></div>';
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
    lim.body.firstChild.append(...LIMITATIONS.map((t) => { const li = document.createElement('li'); li.textContent = t; return li; }));
    $(root, '[data-ref="row3"]').append(arts.card, lim.card);
    reveal(root, ctx, '.card');
  },
};
