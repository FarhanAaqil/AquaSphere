// Shared ocean theme for every Plotly chart, plus the single "thermal" colormap
// used by all temperature visuals (Plotly heatmaps, the map canvas and three.js textures).

let plotlyPromise;
/** Plotly is ~4.5 MB, so it loads on first use rather than with the landing page. */
export function loadPlotly() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  plotlyPromise ||= new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'vendor/plotly/plotly.min.js';
    s.onload = () => resolve(window.Plotly);
    s.onerror = () => { plotlyPromise = null; reject(new Error('Could not load Plotly')); };
    document.head.append(s);
  });
  return plotlyPromise;
}

export const C = {
  text: '#e6f1ff',
  muted: '#9fb3c8',
  faint: '#7f93a8',
  grid: 'rgba(103,232,249,0.08)',
  axis: 'rgba(103,232,249,0.22)',
  coral: '#fb7185',
  amber: '#fbbf24',
  teal: '#14b8a6',
  indigo: '#4f46e5',
  night: '#1e1b4b',
  cyan: '#22d3ee',
  glow: '#67e8f9',
  band: 'rgba(34,211,238,0.18)',
  warn: '#f97316',
  error: '#f43f5e',
  ok: '#34d399',
  violet: '#a78bfa',
};

// Cold → warm. Perceptually ordered: deep indigo, indigo, teal, amber, coral.
export const THERMAL_STOPS = [
  [0.0, '#1e1b4b'],
  [0.18, '#3730a3'],
  [0.36, '#4f46e5'],
  [0.55, '#14b8a6'],
  [0.78, '#fbbf24'],
  [1.0, '#fb7185'],
];
export const THERMAL = THERMAL_STOPS;
export const T_RANGE = [5, 31]; // °C, fixed so colours mean the same thing on every view

const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const STOPS_RGB = THERMAL_STOPS.map(([t, h]) => [t, hex(h)]);

/** [r,g,b] 0–255 for a value on the thermal scale. */
export function thermalRGB(v, [lo, hi] = T_RANGE) {
  const t = Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
  for (let i = 1; i < STOPS_RGB.length; i++) {
    const [t1, c1] = STOPS_RGB[i];
    if (t <= t1) {
      const [t0, c0] = STOPS_RGB[i - 1];
      const f = (t - t0) / (t1 - t0);
      return c0.map((c, k) => Math.round(c + (c1[k] - c) * f));
    }
  }
  return STOPS_RGB.at(-1)[1];
}
export const thermalCSS = (v, range) => `rgb(${thermalRGB(v, range).join(',')})`;
export const thermalGradientCSS = () => `linear-gradient(90deg, ${THERMAL_STOPS.map(([t, h]) => `${h} ${t * 100}%`).join(', ')})`;

const FONT = { family: 'Inter, system-ui, sans-serif', color: C.text, size: 12 };
const MONO = 'JetBrains Mono, ui-monospace, monospace';

export function axis(extra = {}) {
  return {
    gridcolor: C.grid,
    zerolinecolor: C.axis,
    linecolor: C.axis,
    tickfont: { family: MONO, size: 11, color: C.muted },
    title: { font: { size: 12, color: C.muted } },
    automargin: true,
    ...extra,
  };
}

export function layout(extra = {}) {
  const { xaxis, yaxis, ...rest } = extra;
  return {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(2,6,23,0.35)',
    font: FONT,
    margin: { l: 56, r: 18, t: 16, b: 48 },
    hoverlabel: { bgcolor: '#041530', bordercolor: C.glow, font: { family: MONO, size: 12, color: C.text } },
    legend: { orientation: 'h', x: 0, y: -0.18, font: { size: 11, color: C.muted }, bgcolor: 'rgba(0,0,0,0)' },
    xaxis: axis(xaxis),
    yaxis: axis(yaxis),
    ...rest,
  };
}

/** Depth axis: 0 m at the top, non-linear-feeling via sqrt-ish tick placement kept simple. */
export function depthAxis(extra = {}) {
  return axis({ title: { text: 'Depth (m)' }, autorange: 'reversed', ticksuffix: ' m', ...extra });
}

export function config(name = 'aquasphere') {
  return {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines', 'hoverCompareCartesian'],
    toImageButtonOptions: { format: 'png', filename: name, scale: 2 },
  };
}

/** Draw (or redraw) a chart and register cleanup with the tab context. */
export async function plot(el, traces, lay, ctx, name) {
  const Plotly = await loadPlotly();
  if (ctx?.signal.aborted) return null;
  await Plotly.react(el, traces, layout(lay), config(name));
  if (ctx && !el.dataset.purgeHooked) {
    el.dataset.purgeHooked = '1';
    ctx.cleanup(() => Plotly.purge(el));
  }
  return Plotly;
}
