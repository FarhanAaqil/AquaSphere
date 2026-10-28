import { state, set } from '../state.js';
import * as api from '../api.js';
import { DOMAIN, inDomain, onLand, nioLand, fmtLat, fmtLon, region } from '../geo.js';
import { createMap } from '../ui/map.js';
import { badge, tag } from '../ui/badges.js';
import { loading, errorState, empty } from '../ui/loaders.js';
import { toast } from '../ui/toasts.js';
import { renderProfile } from '../charts/profile.js';
import { h, $, onDate, countUp, fmt, reveal } from './_util.js';

function template() {
  return `
  <div class="page__intro">
    <h2>Predict a profile</h2>
    <p>Pick a point in the study domain. The API resolves surface observations for the selected date, runs the model and
    returns temperature at 15 depths with a conformal 90% interval.</p>
  </div>
  <div class="grid grid--side">
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Location</h3><p class="card__sub">Click the map or type coordinates</p></div></div>
      <div data-ref="map"></div>
      <form class="point-form" data-ref="form" novalidate>
        <label class="field"><span class="field__label">Latitude °N</span>
          <input class="input input--mono" name="lat" type="number" step="0.01" min="${DOMAIN.lat_min}" max="${DOMAIN.lat_max}" required></label>
        <label class="field"><span class="field__label">Longitude °E</span>
          <input class="input input--mono" name="lon" type="number" step="0.01" min="${DOMAIN.lon_min}" max="${DOMAIN.lon_max}" required></label>
        <div class="field"><span class="field__label">Date</span><output class="input input--mono out" data-ref="date">—</output></div>
        <button class="btn" type="submit" data-ref="go"><svg aria-hidden="true"><use href="assets/icons.svg#i-predict"></use></svg>Predict</button>
      </form>
      <p class="card__foot">Date is set in the top bar. Domain ${DOMAIN.lat_min}–${DOMAIN.lat_max}°N, ${DOMAIN.lon_min}–${DOMAIN.lon_max}°E.</p>
    </div>
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Temperature profile</h3><p class="card__sub" data-ref="sub">—</p></div><div class="card__meta" data-ref="badges"></div></div>
      <div class="chart chart--tall" data-ref="chart"></div>
    </div>
  </div>
  <div class="grid grid--4" data-ref="stats"></div>
  <div class="grid grid--2">
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Applicability check</h3><p class="card__sub">Is this point inside what the model was trained on?</p></div><div class="card__meta" data-ref="ad-badge"></div></div>
      <ul class="checks" data-ref="checks"></ul>
    </div>
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Interval width by depth</h3><p class="card__sub">Upper − lower bound of the 90% interval</p></div><div class="card__meta" data-ref="w-badge"></div></div>
      <div class="chart chart--short" data-ref="width"></div>
    </div>
  </div>`;
}

const STAT_DEFS = [
  ['Surface (0 m)', (p) => p.temperatures[0], 2, '°C', (p) => `90% ${fmt(p.interval_lower[0])}–${fmt(p.interval_upper[0])} °C`],
  ['D20 · 20 °C isotherm', (p) => p.d20, 0, 'm', () => 'Thermocline proxy'],
  ['Mixed layer depth', (p) => p.mld, 0, 'm', () => 'From the predicted profile'],
  ['OHC index · 0–300 m', (p) => p.ohc300, 2, '°C', () => 'Depth-averaged temperature'],
];

async function trainingWindow() {
  try {
    const info = await api.results('build_info');
    const art = info.artifacts.find((a) => a.date_range);
    return art ? { from: art.date_range[0], to: art.date_range[1] } : null;
  } catch {
    return null;
  }
}

function renderChecks(root, p, window_) {
  const checks = [
    { ok: inDomain(p.lat, p.lon), text: `Inside study domain (${fmtLat(p.lat)}, ${fmtLon(p.lon)})` },
    { ok: !onLand(p.lat, p.lon), text: 'Over ocean (Natural Earth 1:50m coastline)' },
    window_
      ? { ok: p.date >= window_.from && p.date <= window_.to, text: `Date inside the Argo training window ${window_.from} → ${window_.to}`, fail: `Date ${p.date} is outside the Argo training window ${window_.from} → ${window_.to}: temporal extrapolation` }
      : { ok: null, text: 'Training date window unknown (build_info.json missing)' },
    { ok: !p.in_training_set, text: 'Not a training sample (API in_training_set = false)', fail: 'This exact point/date was in the training partition' },
    { ok: null, text: 'Embedding dissimilarity index: not exposed by the API yet — see Uncertainty tab' },
  ];
  const ul = $(root, '[data-ref="checks"]');
  ul.replaceChildren(...checks.map((c) => {
    const li = document.createElement('li');
    li.className = `check check--${c.ok === null ? 'na' : c.ok ? 'ok' : 'warn'}`;
    li.textContent = c.ok === false && c.fail ? c.fail : c.text;
    return li;
  }));
  const outside = checks.some((c) => c.ok === false);
  $(root, '[data-ref="ad-badge"]').replaceChildren(outside
    ? tag('Outside applicability domain', 'warn', 'At least one check failed — treat this profile with extra caution.')
    : tag('Within applicability domain', 'ok', 'All available checks passed.'));
}

async function renderWidth(root, p, ctx) {
  const { plot, C } = await import('../charts/theme.js');
  const w = p.interval_upper.map((u, i) => u - p.interval_lower[i]);
  $(root, '[data-ref="w-badge"]').replaceChildren(badge(p.data_source));
  await plot($(root, '[data-ref="width"]'), [{
    type: 'bar', x: p.depths.map(String), y: w,
    marker: { color: w.map((v) => (v === Math.max(...w) ? C.warn : C.cyan)), opacity: 0.85 },
    hovertemplate: '%{x} m: %{y:.2f} °C wide<extra></extra>',
  }], {
    xaxis: { title: { text: 'Depth (m)' }, type: 'category' },
    yaxis: { title: { text: 'Width (°C)' } },
    margin: { l: 52, r: 12, t: 8, b: 44 },
    showlegend: false,
  }, ctx, 'aquasphere-interval-width');
}

export default {
  async mount(root, ctx) {
    root.innerHTML = template();
    const form = $(root, '[data-ref="form"]');
    const chart = $(root, '[data-ref="chart"]');
    const stats = $(root, '[data-ref="stats"]');
    const sub = $(root, '[data-ref="sub"]');
    const badges = $(root, '[data-ref="badges"]');
    const window_ = trainingWindow();
    await nioLand();

    let req = 0;
    const map = await createMap($(root, '[data-ref="map"]'), {
      label: 'Click to choose a prediction point',
      onPick: ({ lat, lon, inside }) => {
        if (!inside) return toast('That point is outside the 5–30°N, 45–105°E study domain.', { kind: 'warn' });
        run(lat, lon);
      },
    });

    const clearResult = () => {
      stats.replaceChildren();
      $(root, '[data-ref="checks"]').replaceChildren();
      $(root, '[data-ref="ad-badge"]').replaceChildren();
      $(root, '[data-ref="w-badge"]').replaceChildren();
      empty($(root, '[data-ref="width"]'), 'No profile yet');
    };

    async function run(lat, lon) {
      form.lat.value = lat;
      form.lon.value = lon;
      map.setTarget(lat, lon);
      set({ point: { lat, lon } });
      const date = state.date;
      sub.textContent = `${fmtLat(lat)} ${fmtLon(lon)} · ${region(lat, lon)} · ${date || 'no date'}`;
      if (onLand(lat, lon)) {
        badges.replaceChildren();
        clearResult();
        return empty(chart, 'That point is on land', 'AquaSphere reconstructs ocean profiles. Choose a point over water.');
      }
      if (!date) {
        badges.replaceChildren(badge('unavailable'));
        clearResult();
        return errorState(chart, { kind: 'offline' }, { retry: () => location.reload() });
      }
      const my = ++req;
      loading(chart, 'Resolving surface observations and running the model…');
      badges.replaceChildren();
      try {
        const p = await api.predict({ lat, lon, date }, { signal: ctx.signal });
        if (my !== req) return;
        set({ lastPrediction: p });
        chart.replaceChildren();
        delete chart.dataset.drawn;
        badges.replaceChildren(
          badge(p.data_source),
          tag(`model ${p.model_version}`, 'muted'),
          ...(p.in_training_set ? [tag('In training set', 'warn', 'This point/date was part of the training partition.')] : []),
        );
        await renderProfile(chart, {
          depths: p.depths, mean: p.temperatures, lower: p.interval_lower, upper: p.interval_upper,
          climatology: p.climatology, d20: p.d20, mld: p.mld,
        }, ctx, { name: `aquasphere-profile-${lat}-${lon}-${date}` });

        stats.replaceChildren(...STAT_DEFS.map(([label, get, digits, unit, note]) => {
          const c = h('<div class="card stat-card"><div class="stat stat--sm"><span class="stat__label"></span><span class="stat__value"></span><span class="stat__note"></span></div><div class="card__meta"></div></div>');
          c.querySelector('.stat__label').textContent = label;
          c.querySelector('.stat__note').textContent = note(p);
          c.querySelector('.card__meta').append(badge(p.data_source));
          countUp(c.querySelector('.stat__value'), get(p), { digits, suffix: unit });
          return c;
        }));
        renderChecks(root, p, await window_);
        await renderWidth(root, p, ctx);
      } catch (err) {
        if (ctx.signal.aborted || my !== req) return;
        badges.replaceChildren(badge(err.kind === 'unavailable' ? 'unavailable' : 'offline'));
        clearResult();
        errorState(chart, err, { retry: () => run(lat, lon) });
      }
    }

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const lat = Number(form.lat.value);
      const lon = Number(form.lon.value);
      const bad = !Number.isFinite(lat) || !Number.isFinite(lon) || !inDomain(lat, lon);
      form.lat.setAttribute('aria-invalid', String(!Number.isFinite(lat) || lat < DOMAIN.lat_min || lat > DOMAIN.lat_max));
      form.lon.setAttribute('aria-invalid', String(!Number.isFinite(lon) || lon < DOMAIN.lon_min || lon > DOMAIN.lon_max));
      if (bad) return toast(`Enter a latitude ${DOMAIN.lat_min}–${DOMAIN.lat_max} and longitude ${DOMAIN.lon_min}–${DOMAIN.lon_max}.`, { kind: 'warn' });
      run(lat, lon);
    });

    onDate(ctx, (date) => {
      $(root, '[data-ref="date"]').textContent = date || 'unavailable';
      run(state.point.lat, state.point.lon);
    });
    reveal(root, ctx, '.grid > .card');
  },
};
