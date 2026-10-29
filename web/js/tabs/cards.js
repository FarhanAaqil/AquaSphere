import { state } from '../state.js';
import * as api from '../api.js';
import { badge, tag } from '../ui/badges.js';
import { pending } from '../ui/loaders.js';
import { C } from '../charts/theme.js';
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
  'The served model and the E3/E7 ablation runs were trained on tables whose SSS, SLA, current and wind columns came from the synthetic demo store (proven by the audit above). Only their SST input is real. They are replaced by models trained on the real 2015–2025 store in roadmap Phase 4.',
  'Decision-support prototype. Not validated for navigation, safety-critical offshore work or search and rescue without independent INCOIS verification.',
  'The API\'s local surface store reports offline_synthetic, so live-looking predictions on this site are driven by fixture inputs unless the source badge says Disk cache or Live.',
  'The Argo archive covers 2025-03-25 → 2025-09-15 only. The documented temporal split (train 2015–22 / val 2023 / test 2024–25) cannot be run on it, so evaluation uses a float-grouped split instead.',
  'The /validation/profile lookup store (tests/fixtures/argo_200.parquet) is mostly training floats for the served model: only 39 of its 200 profiles are held out. The API now returns held-out profiles by default and flags the rest.',
  'The served model (80/20 float split) and metrics.json (70/15/15 float split) use different partitions; they are unified in the evaluation framework v2.',
  'OISST contains Argo near-surface values, so errors at 0–10 m are not an independent test. The blueprint reports headline skill at 20 m and below; the current metrics files still group 0–30 m together.',
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
    lim.body.firstChild.append(...LIMITATIONS.map((t) => { const li = document.createElement('li'); li.textContent = t; return li; }));
    $(root, '[data-ref="row3"]').append(arts.card, lim.card);
    reveal(root, ctx, '.card');
  },
};
