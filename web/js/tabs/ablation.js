import { state } from '../state.js';
import * as api from '../api.js';
import { badge, tag } from '../ui/badges.js';
import { pending } from '../ui/loaders.js';
import { plot, C } from '../charts/theme.js';
import { card, h, $, onState, fmt, reveal } from './_util.js';
import { ablationSyntheticChannels, describeChannels } from '../audit.js';

// E7 definition: Nowcast = sensors available within hours (SST + SLA);
// Delayed = all sensors incl. 8-day SMAP SSS and reanalysis winds/currents.
const NOWCAST_RUN = 'A2 (+ SLA)';
const DELAYED_RUN = 'A4 (+ Wind/Curr)';
const SENSORS = ['sst', 'sla', 'sss', 'wind', 'patch', 'ssl'];
const SENSOR_LABEL = { sst: 'SST', sla: 'SLA', sss: 'SSS', wind: 'Wind/Curr', patch: 'Patch CNN', ssl: 'SSL pre-train' };

export default {
  async mount(root, ctx) {
    root.innerHTML = `
      <div class="page__intro"><h2>Sensor ablation &amp; modes</h2>
        <p><strong>E3</strong> adds one sensor family at a time and re-trains. <strong>E7</strong> asks how much skill survives in
        nowcast mode, when only fast-arriving sensors (SST + SLA) are available, compared with delayed mode using every sensor.
        The mode switch in the top bar picks which side is highlighted; it does not change <span class="mono">/predict</span>, which has no mode parameter.</p></div>
      <div class="grid grid--main-side" data-ref="top"></div>
      <div data-ref="table"></div>`;

    let ab;
    try { ab = await api.results('ablation'); } catch {
      const c = card({ title: 'E3 sensor ladder' });
      root.append(c.card);
      pending(c.body, { title: 'Ablation results missing', needs: 'web/data/ablation.json (make ablate && make ui-data)' });
      return;
    }
    const runs = ab.results;
    // A run is compromised if it used any channel the audit proved synthetic (all but SST).
    const synthetic = await ablationSyntheticChannels();
    const fake = (r) => synthetic.length > 0 && ['sla', 'sss', 'wind'].some((s) => r[s] === 'Yes');
    if (synthetic.length) {
      const warn = h('<p class="note note--warn"></p>');
      warn.textContent = `Audit finding: the table these runs were trained on (tests/fixtures/argo_200.parquet) carries ${describeChannels(synthetic)} values copied from the synthetic demo store, not satellite observations. Only SST is real. Every run except A1 therefore measures the effect of generated fields: these numbers are not evidence about real sensors. They will be re-run on the real 2015–2025 store.`;
      root.querySelector('.page__intro').append(warn);
    }
    const ladder = card({ title: 'E3 · sensor ladder', sub: `Thermocline RMSE (50–150 m), mean ± std over ${ab.seeds.length} seeds · n_train ${ab.n_train}, n_val ${ab.n_val}` });
    ladder.meta.append(badge('results'), ...(synthetic.length ? [tag('Synthetic inputs', 'warn', 'Hatched runs used generated SSS/SLA/wind fields.')] : []));
    ladder.body.innerHTML = '<div class="chart"></div>';
    const modes = card({ title: 'E7 · nowcast vs delayed', sub: 'Skill retained when slow sensors are unavailable' });
    modes.meta.append(synthetic.length ? badge('pending') : badge('results'));
    $(root, '[data-ref="top"]').append(ladder.card, modes.card);

    const drawLadder = () => plot(ladder.body.firstChild, [{
      type: 'bar', orientation: 'h', y: runs.map((r) => r.run), x: runs.map((r) => r.thermo_rmse_mean),
      error_x: { type: 'data', array: runs.map((r) => r.thermo_rmse_std), color: C.glow, thickness: 1.2 },
      marker: {
        color: runs.map((r) => (fake(r) ? 'rgba(249,115,22,0.45)' : r.run === (state.mode === 'nowcast' ? NOWCAST_RUN : DELAYED_RUN) ? C.cyan : 'rgba(20,184,166,0.55)')),
        pattern: { shape: runs.map((r) => (fake(r) ? '/' : '')), fgcolor: C.warn, size: 6 },
      },
      customdata: runs.map((r) => [r.skill_score_mean, r.coverage_mean * 100]),
      hovertemplate: '%{y}<br>RMSE %{x:.3f} °C · skill %{customdata[0]:.3f} · coverage %{customdata[1]:.1f}%<extra></extra>',
    }], { xaxis: { title: { text: 'Thermocline RMSE (°C) — lower is better' } }, yaxis: { autorange: 'reversed' }, margin: { l: 130, r: 16, t: 8, b: 48 }, showlegend: false }, ctx, 'aquasphere-e3-ladder');

    const now = runs.find((r) => r.run === NOWCAST_RUN);
    const del = runs.find((r) => r.run === DELAYED_RUN);
    const drawModes = () => {
      if (!now || !del) return pending(modes.body, { title: 'Pending', needs: `Runs "${NOWCAST_RUN}" and "${DELAYED_RUN}" in ablation.json` });
      if (fake(now) || fake(del)) {
        return pending(modes.body, {
          title: 'Pending real data',
          detail: `E7 compares SST + SLA against all sensors, and in these runs every channel except SST was synthetic (${describeChannels(synthetic)}). A skill-retained figure from them would be meaningless, so none is shown.`,
          needs: 'Re-run on argo_nio_collocated.parquet (real 2015–2025 store), roadmap Phase 4',
        });
      }
      const box = (r, label, key) => `<div class="mode-box ${state.mode === key ? 'is-active' : ''}">
        <div class="stat__label">${label}</div>
        <div class="stat"><span class="stat__value">${fmt(r.thermo_rmse_mean)}<small>°C</small></span>
        <span class="stat__note">± ${fmt(r.thermo_rmse_std)} · skill ${fmt(r.skill_score_mean)}</span></div></div>`;
      const retained = now.skill_score_mean / del.skill_score_mean;
      const noise = Math.abs(now.thermo_rmse_mean - del.thermo_rmse_mean) < Math.max(now.thermo_rmse_std, del.thermo_rmse_std);
      modes.body.innerHTML = `<div class="mode-compare">${box(now, 'Nowcast · SST + SLA', 'nowcast')}<span class="vs">vs</span>${box(del, 'Delayed · all sensors', 'delayed')}</div>
        <div class="stat" style="margin-top:var(--sp-4)"><span class="stat__label">Skill retained in nowcast</span><span class="stat__value">${(retained * 100).toFixed(0)}<small>%</small></span>
        <span class="stat__note">skill(nowcast) / skill(delayed)</span></div><p class="note"></p>`;
      modes.body.querySelector('.note').textContent = noise
        ? `The RMSE difference (${fmt(Math.abs(now.thermo_rmse_mean - del.thermo_rmse_mean), 3)} °C) is smaller than the seed-to-seed spread, so on this ${ab.n_val}-profile validation set the two modes are not distinguishable. Retained skill above 100% means extra sensors did not help here, not that fewer sensors are better in general.`
        : `Difference exceeds the seed spread on the ${ab.n_val}-profile validation set.`;
      if (retained > 1) modes.body.querySelector('.note').classList.add('note--warn');
    };

    // Run table
    const tbl = card({ title: 'All runs', sub: 'Which inputs each run used' });
    tbl.meta.append(badge('results'));
    tbl.body.innerHTML = `<div class="table-wrap" tabindex="0" role="region" aria-label="All ablation runs"><table class="table"><thead><tr><th>Run</th>${SENSORS.map((s) => `<th>${SENSOR_LABEL[s]}</th>`).join('')}<th class="num">Thermo RMSE</th><th class="num">Skill</th><th class="num">Coverage</th></tr></thead><tbody></tbody></table></div>`;
    const best = Math.min(...runs.map((r) => r.thermo_rmse_mean));
    for (const r of runs) {
      const tr = h(`<tr><td></td>${SENSORS.map((s) => `<td>${r[s] === 'Yes' ? '●' : '<span style="color:var(--text-faint)">–</span>'}</td>`).join('')}<td class="num"></td><td class="num"></td><td class="num"></td></tr>`);
      tr.cells[0].textContent = r.run;
      if (fake(r)) tr.cells[0].append(' ', tag('synthetic inputs', 'warn'));
      tr.cells[SENSORS.length + 1].textContent = `${fmt(r.thermo_rmse_mean, 3)} ± ${fmt(r.thermo_rmse_std, 3)}`;
      tr.cells[SENSORS.length + 2].textContent = fmt(r.skill_score_mean, 3);
      tr.cells[SENSORS.length + 3].textContent = `${(r.coverage_mean * 100).toFixed(1)}%`;
      if (r.thermo_rmse_mean === best) tr.classList.add('is-best');
      tbl.body.querySelector('tbody').append(tr);
    }
    $(root, '[data-ref="table"]').append(tbl.card);

    await drawLadder();
    drawModes();
    onState(ctx, ['mode'], () => { drawLadder(); drawModes(); });
    reveal(root, ctx, '.card');
  },
};
