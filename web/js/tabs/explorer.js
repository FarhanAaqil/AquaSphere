import { state } from '../state.js';
import * as api from '../api.js';
import { fmtLat, fmtLon } from '../geo.js';
import { createMap } from '../ui/map.js';
import { badge, tag } from '../ui/badges.js';
import { loading, errorState, pending } from '../ui/loaders.js';
import { renderProfile } from '../charts/profile.js';
import { plot, C } from '../charts/theme.js';
import { h, $, fmt, reveal } from './_util.js';

const Z90 = 1.645;
const SPLIT_COLOR = { test: '#22d3ee', val: '#14b8a6', train: '#7f93a8', unknown: '#a78bfa' };

function template() {
  return `
  <div class="page__intro">
    <h2>Profile explorer</h2>
    <p>Compare the model against Argo profiles it was not trained on. Points are the profiles in the API's validation lookup
    store, tagged with the float-grouped split used in evaluation. Profiles from training floats are hidden unless you ask for
    them, and are marked when shown.</p>
  </div>
  <div class="card">
    <div class="toolbar">
      <div class="chips" role="group" aria-label="Region filter" data-ref="regions">
        <button class="chip" aria-pressed="true" data-region="all">All</button>
        <button class="chip" aria-pressed="false" data-region="Arabian Sea">Arabian Sea</button>
        <button class="chip" aria-pressed="false" data-region="Bay of Bengal">Bay of Bengal</button>
      </div>
      <label class="switch"><input type="checkbox" data-ref="show-train"><span>Show in-training profiles</span></label>
      <span class="spacer"></span>
      <span class="count" data-ref="count"></span>
      <span class="card__meta" data-ref="store-badge"></span>
    </div>
  </div>
  <div class="grid grid--side">
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Held-out profiles</h3><p class="card__sub">Click a point to compare</p></div></div>
      <div data-ref="map"></div>
      <div class="legend-row">
        <span><i style="background:${SPLIT_COLOR.test}"></i>Test float</span>
        <span><i style="background:${SPLIT_COLOR.val}"></i>Validation float</span>
        <span><i style="background:${SPLIT_COLOR.train}"></i>Training float (in training)</span>
      </div>
      <dl class="kv" data-ref="info"></dl>
    </div>
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Predicted vs observed</h3><p class="card__sub" data-ref="sub">—</p></div><div class="card__meta" data-ref="badges"></div></div>
      <div class="chart chart--tall" data-ref="chart"></div>
      <p class="note" data-ref="note" hidden></p>
    </div>
  </div>
  <div class="grid grid--main-side">
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Error by depth</h3><p class="card__sub">Predicted − observed, whiskers = ±1.645σ (Gaussian 90%)</p></div><div class="card__meta" data-ref="err-badges"></div></div>
      <div class="chart" data-ref="errors"></div>
    </div>
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Scores</h3><p class="card__sub">For the selected profile</p></div></div>
      <div class="grid grid--2" data-ref="scores"></div>
    </div>
  </div>`;
}

function score(label, value, note) {
  const c = h('<div class="stat stat--sm"><span class="stat__label"></span><span class="stat__value"></span><span class="stat__note"></span></div>');
  c.querySelector('.stat__label').textContent = label;
  c.querySelector('.stat__value').textContent = value;
  c.querySelector('.stat__note').textContent = note;
  return c;
}

export default {
  async mount(root, ctx) {
    root.innerHTML = template();
    const chart = $(root, '[data-ref="chart"]');
    const errors = $(root, '[data-ref="errors"]');
    const badges = $(root, '[data-ref="badges"]');
    const note = $(root, '[data-ref="note"]');

    let store;
    try {
      store = await api.results('heldout');
    } catch {
      pending(chart, { title: 'Held-out index missing', detail: 'web/data/heldout.json was not found. Run "python scripts/build_web_data.py".' });
      return;
    }
    $(root, '[data-ref="store-badge"]').replaceChildren(tag(store.split_rule ? 'Split: float-grouped, seed 42' : 'Split unknown', 'muted', store.split_rule || ''));
    const byFloat = new Map(store.profiles.map((p) => [p.float_id, p.split]));

    const filter = { region: 'all', train: false };
    let selected = null;
    const map = await createMap($(root, '[data-ref="map"]'), { label: 'Held-out Argo profile positions' });

    const visible = () => store.profiles.filter((p) =>
      (filter.region === 'all' || p.region === filter.region) && (filter.train || p.split !== 'train'));

    const paint = () => {
      const pts = visible();
      const counts = pts.reduce((a, p) => ({ ...a, [p.split]: (a[p.split] || 0) + 1 }), {});
      $(root, '[data-ref="count"]').textContent =
        `${pts.length} profiles · test ${counts.test || 0} · val ${counts.val || 0}${filter.train ? ` · train ${counts.train || 0}` : ''}`;
      map.setPoints(pts.map((p) => ({
        id: p.profile_id, lat: p.lat, lon: p.lon, r: 0.45, color: SPLIT_COLOR[p.split] || SPLIT_COLOR.unknown, muted: p.split === 'train',
        label: `${p.profile_id} · ${p.date} · ${p.region} · ${p.split === 'train' ? 'IN TRAINING' : `${p.split} float`}`,
        data: p,
      })), { onClick: (pt) => select(pt.data), selected: selected?.profile_id });
    };

    async function select(p) {
      selected = p;
      paint();
      map.setTarget(p.lat, p.lon);
      $(root, '[data-ref="sub"]').textContent = `${p.profile_id} · ${fmtLat(p.lat)} ${fmtLon(p.lon)} · ${p.date}`;
      loading(chart, 'Fetching the held-out profile and the model prediction…');
      errors.replaceChildren();
      badges.replaceChildren();
      note.hidden = true;
      try {
        const r = await api.validationProfile({ lat: p.lat, lon: p.lon, date: p.date }, { signal: ctx.signal });
        if (selected !== p) return;
        render(r, p);
      } catch (err) {
        if (ctx.signal.aborted || selected !== p) return;
        badges.replaceChildren(badge(err.kind === 'unavailable' ? 'unavailable' : 'offline'));
        errorState(chart, err, { retry: () => select(p) });
        $(root, '[data-ref="scores"]').replaceChildren();
      }
    }

    async function render(r, p) {
      // The API fills depths without an observation with 0.0. Nowhere in 0–1000 m of the
      // North Indian Ocean is at 0 °C, so treat those as missing rather than plotting them.
      const obs = r.true_temperatures.map((t) => (t === 0 ? null : t));
      const nObs = obs.filter((t) => t != null).length;
      const split = state.demo ? 'demo' : byFloat.get(String(r.float_id)) || 'unknown';
      const inTraining = split === 'train';

      badges.replaceChildren(
        badge(r.data_source, 'Label as returned by /validation/profile.'),
        inTraining ? tag('In training', 'warn', 'This float was in the training split; this is not a held-out comparison.') : tag(split === 'demo' ? 'Synthetic' : `${split} float · held out`, split === 'demo' ? 'demo' : 'heldout'),
      );
      if (String(r.profile_id) !== p.profile_id && !state.demo) {
        note.hidden = false;
        note.textContent = `The API matched the nearest stored profile, ${r.profile_id} (${fmt(r.distance_km, 1)} km away), rather than ${p.profile_id}.`;
      } else if (r.data_source === 'offline_synthetic') {
        note.hidden = false;
        note.textContent = 'The API labels this response "offline_synthetic". Observed temperatures are the stored Argo profile; the prediction is driven only by that profile\'s collocated SST.';
      }

      chart.replaceChildren();
      delete chart.dataset.drawn;
      const lower = r.pred_temperatures.map((t, i) => t - Z90 * r.uncertainties[i]);
      const upper = r.pred_temperatures.map((t, i) => t + Z90 * r.uncertainties[i]);
      await renderProfile(chart, {
        depths: r.depths, mean: r.pred_temperatures, lower, upper, bandLabel: '±1.645σ (Gaussian 90%)', observed: obs,
      }, ctx, { name: `aquasphere-heldout-${r.profile_id}` });

      // Error bars
      const resid = r.pred_temperatures.map((t, i) => (obs[i] == null ? null : t - obs[i]));
      const half = r.uncertainties.map((u) => Z90 * u);
      const inside = resid.map((e, i) => (e == null ? null : Math.abs(e) <= half[i]));
      $(root, '[data-ref="err-badges"]').replaceChildren(badge(r.data_source));
      await plot(errors, [{
        type: 'bar', orientation: 'h', y: r.depths.map((d) => `${d} m`), x: resid,
        error_x: { type: 'data', array: half, color: 'rgba(103,232,249,0.6)', thickness: 1.2, width: 3 },
        marker: { color: inside.map((v) => (v == null ? 'rgba(0,0,0,0)' : v ? C.teal : C.warn)) },
        customdata: r.depths.map((d, i) => [obs[i] == null ? 'no observation' : inside[i] ? 'inside 90%' : 'outside 90%']),
        hovertemplate: '%{y}: %{x:+.2f} °C · %{customdata[0]}<extra></extra>',
      }], {
        xaxis: { title: { text: 'Predicted − observed (°C)' }, zeroline: true, zerolinecolor: C.glow },
        yaxis: { autorange: 'reversed', type: 'category' },
        margin: { l: 64, r: 12, t: 8, b: 44 },
        showlegend: false,
      }, ctx, `aquasphere-errors-${r.profile_id}`);

      const valid = resid.filter((e) => e != null);
      const rmseObs = valid.length ? Math.sqrt(valid.reduce((a, e) => a + e * e, 0) / valid.length) : null;
      const thermo = r.depths.map((d, i) => (d >= 50 && d <= 150 ? resid[i] : null)).filter((e) => e != null);
      const rmseThermo = thermo.length ? Math.sqrt(thermo.reduce((a, e) => a + e * e, 0) / thermo.length) : null;
      // Blueprint §10.1: OISST contains Argo near-surface values, so 0–10 m is not a clean test.
      const deep = r.depths.map((d, i) => (d >= 20 ? resid[i] : null)).filter((e) => e != null);
      const rmseDeep = deep.length ? Math.sqrt(deep.reduce((a, e) => a + e * e, 0) / deep.length) : null;
      const cover = inside.filter((v) => v != null);
      $(root, '[data-ref="scores"]').replaceChildren(
        score('RMSE · observed depths', rmseObs == null ? '—' : `${rmseObs.toFixed(2)} °C`, `${nObs} of ${r.depths.length} depths observed`),
        score('RMSE · 20 m and below', rmseDeep == null ? '—' : `${rmseDeep.toFixed(2)} °C`, 'Headline depths: 0–10 m excluded, input SST contains Argo near-surface data'),
        score('Thermocline RMSE', rmseThermo == null ? '—' : `${rmseThermo.toFixed(2)} °C`, '50–150 m, observed depths'),
        score('Inside ±1.645σ', cover.length ? `${cover.filter(Boolean).length}/${cover.length}` : '—', 'Depths where the observation falls in the band'),
        score('RMSE · API', `${fmt(r.rmse)} °C`, 'As returned; includes zero-filled missing depths'),
      );
      const info = $(root, '[data-ref="info"]');
      info.replaceChildren();
      for (const [k, v] of [['Float', r.float_id], ['Cycle', r.cycle], ['Date', r.date], ['Position', `${fmtLat(r.lat)} ${fmtLon(r.lon)}`], ['Region', p.region], ['Split', split]]) {
        const dt = document.createElement('dt'); dt.textContent = k;
        const dd = document.createElement('dd'); dd.textContent = v;
        info.append(dt, dd);
      }
    }

    $(root, '[data-ref="regions"]').addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      filter.region = b.dataset.region;
      for (const c of b.parentElement.children) c.setAttribute('aria-pressed', String(c === b));
      paint();
    });
    $(root, '[data-ref="show-train"]').addEventListener('change', (e) => { filter.train = e.target.checked; paint(); });

    paint();
    const first = visible().find((p) => p.split === 'test') || visible()[0];
    if (first) select(first);
    reveal(root, ctx, '.grid > .card');
  },
};
