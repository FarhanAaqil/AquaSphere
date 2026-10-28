import { state, set } from '../state.js';
import * as api from '../api.js';
import { DOMAIN, inDomain, fmtLat, fmtLon } from '../geo.js';
import { badge, tag } from '../ui/badges.js';
import { loading, errorState, empty } from '../ui/loaders.js';
import { toast } from '../ui/toasts.js';
import { plot, C, THERMAL } from '../charts/theme.js';
import { card, h, $, onDate, reveal } from './_util.js';

// Feature → sensor family (engine.explain_point feature order)
const FAMILY = {
  sst: 'SST', sst_avail: 'SST',
  sla: 'SLA', sla_avail: 'SLA',
  sss: 'SSS', sss_avail: 'SSS',
  ug: 'Currents', vg: 'Currents', ug_avail: 'Currents', vg_avail: 'Currents',
  u10: 'Wind', v10: 'Wind', u10_avail: 'Wind', v10_avail: 'Wind',
  lat: 'Position', lon: 'Position',
  sin_doy: 'Season', cos_doy: 'Season',
};
const FAMILY_COLOR = { SST: C.coral, SLA: C.teal, SSS: C.amber, Currents: C.indigo, Wind: C.violet, Position: C.faint, Season: C.muted };

export default {
  async mount(root, ctx) {
    root.innerHTML = `
      <div class="page__intro"><h2>Explain</h2>
        <p>Which inputs drove a prediction, and where the point sits in embedding space. Attributions come from
        <span class="mono">/explain</span>: |gradient × input| for the predicted temperature at 100 m, normalised to sum to 1.</p></div>
      <div class="card"><form class="toolbar" data-ref="form" novalidate>
        <label class="field field--inline"><span class="field__label">Lat °N</span><input class="input input--mono" name="lat" type="number" step="0.01" style="width:7rem"></label>
        <label class="field field--inline"><span class="field__label">Lon °E</span><input class="input input--mono" name="lon" type="number" step="0.01" style="width:7rem"></label>
        <button class="btn btn--sm" type="submit">Explain this point</button>
        <span class="spacer"></span><span class="count" data-ref="where"></span>
      </form></div>
      <div class="grid grid--main-side" data-ref="row1"></div>
      <div class="grid grid--2" data-ref="row2"></div>`;

    const feat = card({ title: 'Feature attribution', sub: 'Share of total attribution per input feature' });
    const fam = card({ title: 'Which sensors drove it', sub: 'Attribution summed by sensor family' });
    const emb = card({ title: 'Embedding space', sub: '2-D coordinates from /grid for every ocean cell, coloured by SST' });
    const about = card({ title: 'How to read this' });
    feat.body.innerHTML = '<div class="chart chart--tall"></div>';
    fam.body.innerHTML = '<div class="sensor-bars"></div>';
    emb.body.innerHTML = '<div class="chart"></div><p class="note"></p>';
    about.body.innerHTML = `<ul class="plain-list">
      <li>Attribution is local: it explains this one prediction at 100 m, not the model in general.</li>
      <li>"_avail" features are masks telling the model whether a sensor was present; their share shows how much the model leans on knowing a sensor is missing.</li>
      <li>Gradient × input is a first-order method. It is quick and honest about what it is, but it is not integrated gradients over a baseline path even though the API labels it that way.</li>
      <li>The embedding map uses the two numbers <span class="mono">/grid</span> calls pca1 and pca2. In the current backend they are the means of the first and second halves of the 16-d embedding, not true principal components.</li></ul>`;
    $(root, '[data-ref="row1"]').append(feat.card, fam.card);
    $(root, '[data-ref="row2"]').append(emb.card, about.card);
    emb.body.querySelector('.note').textContent = 'Points close together have similar embeddings. The highlighted cell is the grid point nearest the explained location.';

    const form = $(root, '[data-ref="form"]');
    form.lat.value = state.point.lat;
    form.lon.value = state.point.lon;
    const featChart = feat.body.firstChild;
    const famBars = fam.body.firstChild;
    const embChart = emb.body.firstChild;
    let gridPts = null;

    async function explainPoint() {
      const { lat, lon } = state.point;
      const date = state.date;
      $(root, '[data-ref="where"]').textContent = `${fmtLat(lat)} ${fmtLon(lon)} · ${date || '—'}`;
      if (!date) { errorState(featChart, { kind: 'offline' }); famBars.replaceChildren(); return; }
      loading(featChart, 'Computing attributions…');
      famBars.replaceChildren();
      try {
        const r = await api.explain({ lat, lon, date }, { signal: ctx.signal });
        const entries = Object.entries(r.feature_attributions || {}).sort((a, b) => b[1] - a[1]);
        const src = r.data_source || (state.demo ? 'demo_synthetic' : null);
        feat.meta.replaceChildren(badge(src || 'unreported'), tag(`method: ${r.method}`, 'muted'));
        fam.meta.replaceChildren(badge(src || 'unreported'));
        if (!entries.length) {
          empty(featChart, 'No attributions returned', 'The API returned an empty attribution map; the model checkpoint is probably not loaded.');
          return;
        }
        featChart.replaceChildren();
        await plot(featChart, [{
          type: 'bar', orientation: 'h', y: entries.map((e) => e[0]), x: entries.map((e) => e[1] * 100),
          marker: { color: entries.map((e) => FAMILY_COLOR[FAMILY[e[0]]] || C.cyan) },
          hovertemplate: '%{y}: %{x:.1f}%<extra></extra>',
        }], { xaxis: { title: { text: 'Share of attribution (%)' } }, yaxis: { autorange: 'reversed', tickfont: { family: 'JetBrains Mono', size: 11 } }, margin: { l: 90, r: 12, t: 8, b: 44 }, showlegend: false }, ctx, 'aquasphere-attribution');

        const sums = {};
        for (const [k, v] of entries) sums[FAMILY[k] || k] = (sums[FAMILY[k] || k] || 0) + v;
        const fams = Object.entries(sums).sort((a, b) => b[1] - a[1]);
        const max = fams[0][1] || 1;
        famBars.replaceChildren(...fams.map(([name, v]) => {
          const row = h('<div class="sensor-row"><span></span><span class="rung__bar"><span></span></span><span class="rung__val"></span></div>');
          row.children[0].textContent = name;
          row.querySelector('.rung__bar span').style.cssText = `width:${(v / max) * 100}%;background:${FAMILY_COLOR[name] || C.cyan}`;
          row.children[2].textContent = `${(v * 100).toFixed(1)}%`;
          return row;
        }));
        drawEmbedding();
      } catch (err) {
        if (ctx.signal.aborted) return;
        feat.meta.replaceChildren();
        errorState(featChart, err, { retry: explainPoint });
      }
    }

    async function drawEmbedding() {
      if (!gridPts?.length) return;
      const { lat, lon } = state.point;
      const near = gridPts.reduce((best, p) => ((p.lat - lat) ** 2 + (p.lon - lon) ** 2 < (best.lat - lat) ** 2 + (best.lon - lon) ** 2 ? p : best));
      await plot(embChart, [
        {
          type: 'scattergl', mode: 'markers', x: gridPts.map((p) => p.pca1), y: gridPts.map((p) => p.pca2),
          marker: { size: 7, color: gridPts.map((p) => p.sst), colorscale: THERMAL, colorbar: { title: { text: 'SST °C' }, thickness: 10, outlinewidth: 0 }, line: { width: 0 } },
          customdata: gridPts.map((p) => [p.lat, p.lon, p.sst]),
          hovertemplate: '%{customdata[0]:.1f}°N %{customdata[1]:.1f}°E · SST %{customdata[2]:.2f} °C<extra></extra>', name: 'Grid cells',
        },
        { type: 'scatter', mode: 'markers', x: [near.pca1], y: [near.pca2], marker: { size: 16, color: 'rgba(0,0,0,0)', line: { color: '#fff', width: 2 } }, name: 'Explained point', hoverinfo: 'skip' },
      ], { xaxis: { title: { text: 'pca1' }, zeroline: false }, yaxis: { title: { text: 'pca2' }, zeroline: false }, showlegend: false }, ctx, 'aquasphere-embedding');
    }

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const lat = Number(form.lat.value);
      const lon = Number(form.lon.value);
      if (!inDomain(lat, lon)) return toast(`Enter a point inside ${DOMAIN.lat_min}–${DOMAIN.lat_max}°N, ${DOMAIN.lon_min}–${DOMAIN.lon_max}°E.`, { kind: 'warn' });
      set({ point: { lat, lon } });
      explainPoint();
    });

    onDate(ctx, async (date) => {
      explainPoint();
      if (!date) return errorState(embChart, { kind: 'offline' });
      loading(embChart, 'Loading /grid embedding coordinates…');
      try {
        const g = await api.grid({ date, step: 2.5 }, { signal: ctx.signal });
        const { nioLand, onLand } = await import('../geo.js');
        await nioLand();
        gridPts = g.points.filter((p) => !onLand(p.lat, p.lon));
        // /grid responses carry no data_source field, so say that rather than guess one.
        emb.meta.replaceChildren(
          badge(state.demo ? 'demo_synthetic' : 'unreported'),
          tag(`${gridPts.length} ocean cells`, 'muted'),
        );
        embChart.replaceChildren();
        drawEmbedding();
      } catch (err) {
        if (ctx.signal.aborted) return;
        errorState(embChart, err);
      }
    });
    reveal(root, ctx, '.grid > .card');
  },
};
