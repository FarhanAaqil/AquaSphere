import { state, set, allow3D } from '../state.js';
import * as api from '../api.js';
import { loadGrid, GRID_STEP } from '../gridData.js';
import { sourceSummary, tag } from '../ui/badges.js';
import { loading, errorState, empty } from '../ui/loaders.js';
import { renderHeatmap } from '../charts/heatmap.js';
import { thermalGradientCSS, T_RANGE } from '../charts/theme.js';
import { $, onDate, reveal } from './_util.js';

const SLICE_DEPTHS = [0, 50, 100, 150, 300, 500, 1000];
const LAYERS = {
  temp: { label: 'Temperature at depth', unit: '°C', scale: 'thermal' },
  d20: { label: 'D20 (20 °C isotherm depth)', unit: 'm', scale: 'depth' },
  mld: { label: 'Mixed layer depth', unit: 'm', scale: 'depth' },
};

function template() {
  return `
  <div class="page__intro">
    <h2>Ocean cube</h2>
    <p>The whole study domain on a ${GRID_STEP}° grid, reconstructed for one date with <span class="mono">/predict_batch</span>
    (all 15 depths per point). Drag to rotate, pick a depth, scrub through the available dates. Land cells are masked.</p>
  </div>
  <div class="card">
    <div class="toolbar">
      <div class="field"><span class="field__label">Depth slice</span><div class="depth-pick" role="radiogroup" aria-label="Depth slice" data-ref="depths"></div></div>
      <span class="spacer"></span>
      <div class="field" style="min-width:min(100%,360px)"><span class="field__label">Date</span>
        <div class="scrubber">
          <button class="icon-btn" data-ref="play" aria-label="Play through dates"><svg aria-hidden="true"><use href="assets/icons.svg#i-play"></use></svg></button>
          <input type="range" min="0" max="0" step="1" data-ref="scrub" aria-label="Date">
          <output data-ref="scrub-out">—</output>
        </div>
      </div>
    </div>
  </div>
  <div class="grid grid--main-side">
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">3-D temperature volume</h3><p class="card__sub" data-ref="sub3d">Slices at ${SLICE_DEPTHS.join(', ')} m · square-root depth axis</p></div><div class="card__meta" data-ref="badges3d"></div></div>
      <div class="cube-stage" data-ref="stage"><div class="cube-labels" data-ref="labels"></div><span class="cube-hint">Drag to rotate · scroll to zoom</span></div>
      <div><div class="colorbar" style="background:${thermalGradientCSS()}"></div><div class="colorbar-labels"><span>${T_RANGE[0]} °C</span><span>fixed scale</span><span>${T_RANGE[1]} °C</span></div></div>
    </div>
    <div class="card">
      <div class="card__head"><div><h3 class="card__title">Map</h3><p class="card__sub" data-ref="sub2d">—</p></div><div class="card__meta" data-ref="badges2d"></div></div>
      <label class="field"><span class="field__label">Layer</span>
        <select class="select" data-ref="layer">${Object.entries(LAYERS).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('')}</select></label>
      <div class="chart" data-ref="map" style="min-height:300px"></div>
      <p class="card__foot" data-ref="foot"></p>
    </div>
  </div>`;
}

export default {
  async mount(root, ctx) {
    root.innerHTML = template();
    const stage = $(root, '[data-ref="stage"]');
    const mapEl = $(root, '[data-ref="map"]');
    let depth = SLICE_DEPTHS.includes(state.depth) ? state.depth : 100;
    let layer = 'temp';
    let grid = null;
    let cube = null;

    // Depth chips
    const depthsEl = $(root, '[data-ref="depths"]');
    depthsEl.innerHTML = SLICE_DEPTHS.map((d) => `<button class="chip" role="radio" data-depth="${d}">${d} m</button>`).join('');
    const paintDepths = () => {
      for (const b of depthsEl.querySelectorAll('button')) b.setAttribute('aria-checked', String(+b.dataset.depth === depth));
    };
    depthsEl.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      depth = +b.dataset.depth;
      set({ depth });
      paintDepths();
      cube?.setActive(depth);
      drawMap();
    });
    paintDepths();
    $(root, '[data-ref="layer"]').addEventListener('change', (e) => { layer = e.target.value; drawMap(); });

    // Date scrubber over the same list the top-bar picker offers
    // The picker is filled once /meta resolves, which can be after this tab mounts, so the
    // list is re-read every time the date settles (see show()).
    let dates = [];
    const scrub = $(root, '[data-ref="scrub"]');
    const out = $(root, '[data-ref="scrub-out"]');
    const playBtn = $(root, '[data-ref="play"]');
    const syncDates = () => {
      const picker = document.getElementById('date-picker');
      dates = picker?.tagName === 'SELECT' ? [...picker.options].map((o) => o.value).filter((v) => /^\d{4}-/.test(v)) : [];
      scrub.max = String(Math.max(0, dates.length - 1));
      scrub.disabled = dates.length < 2;
      playBtn.disabled = dates.length < 2;
    };
    syncDates();
    scrub.addEventListener('input', () => { out.textContent = dates[+scrub.value] || '—'; });
    scrub.addEventListener('change', () => { if (dates[+scrub.value]) set({ date: dates[+scrub.value] }); });

    let playing = false;
    let busy = false;
    const setPlaying = (on) => {
      playing = on;
      playBtn.setAttribute('aria-label', on ? 'Pause' : 'Play through dates');
      playBtn.querySelector('use').setAttribute('href', `assets/icons.svg#${on ? 'i-pause' : 'i-play'}`);
      if (on && !busy) step();
    };
    const step = () => {
      if (!playing) return;
      const i = (dates.indexOf(state.date) + 1) % dates.length;
      set({ date: dates[i] });
    };
    playBtn.addEventListener('click', () => setPlaying(!playing));
    ctx.cleanup(() => { playing = false; });

    // Messages over the 3D stage (offline / 503) live in their own layer
    const stageMsg = document.createElement('div');
    stageMsg.className = 'cube-msg';
    stage.append(stageMsg);

    // 3D (lazy, only if allowed and visible)
    if (allow3D()) {
      const [{ createOceanCube }, land] = await Promise.all([import('../three/oceanCube.js'), api.asset('land_nio.json')]);
      if (ctx.signal.aborted) return;
      cube = createOceanCube(stage, { land: land?.rings || [], labelsEl: $(root, '[data-ref="labels"]'), reduced: state.reduced });
      ctx.cleanup(() => cube.dispose());
      const io = new IntersectionObserver(([e]) => (e.isIntersecting ? cube.start() : cube.stop()));
      io.observe(stage);
      ctx.cleanup(() => io.disconnect());
    } else {
      empty(stageMsg, '3-D view is off', state.perf ? 'Performance mode is on. The 2-D map shows the same data.' : 'Small screens get the 2-D map only.');
    }

    async function drawMap() {
      if (!grid) return;
      const L = LAYERS[layer];
      const di = grid.depths.indexOf(depth);
      const z = layer === 'temp' ? grid.values[di] : grid[layer];
      $(root, '[data-ref="sub2d"]').textContent = layer === 'temp' ? `${L.label}: ${depth} m · ${grid.date}` : `${L.label} · ${grid.date}`;
      await renderHeatmap(mapEl, { lats: grid.lats, lons: grid.lons, z, unit: L.unit, label: L.label, scale: L.scale }, ctx, `aquasphere-${layer}-${depth}-${grid.date}`);
    }

    async function show(date) {
      syncDates();
      out.textContent = date || '—';
      if (dates.includes(date)) scrub.value = String(dates.indexOf(date));
      const b3 = $(root, '[data-ref="badges3d"]');
      const b2 = $(root, '[data-ref="badges2d"]');
      if (!date) {
        b3.replaceChildren(); b2.replaceChildren();
        errorState(mapEl, { kind: 'offline' });
        if (cube) errorState(stageMsg, { kind: 'offline' });
        return;
      }
      busy = true;
      grid = null;
      loading(mapEl, `Reconstructing the ${GRID_STEP}° grid for ${date}…`);
      try {
        const g = await loadGrid(date, { signal: ctx.signal });
        if (state.date !== date) return;
        grid = g;
        if (cube) stageMsg.replaceChildren();
        const badges = sourceSummary(g.sources);
        b3.replaceChildren(...badges.map((n) => n.cloneNode(true)), tag(`${g.nOcean} ocean cells`, 'muted'));
        b2.replaceChildren(...badges);
        $(root, '[data-ref="foot"]').textContent = `${g.nOcean} ocean cells of ${g.lats.length * g.lons.length}; land masked with the Natural Earth 1:50m coastline.`;
        mapEl.replaceChildren();
        cube?.setData(g, SLICE_DEPTHS);
        cube?.setActive(depth);
        await drawMap();
      } catch (err) {
        if (ctx.signal.aborted) return;
        b3.replaceChildren(); b2.replaceChildren();
        errorState(mapEl, err, { retry: () => show(date) });
        if (cube) errorState(stageMsg, err);
        setPlaying(false);
      } finally {
        busy = false;
        if (playing) setTimeout(step, state.reduced ? 1500 : 900);
      }
    }
    onDate(ctx, show);
    reveal(root, ctx, '.grid > .card');
  },
};
