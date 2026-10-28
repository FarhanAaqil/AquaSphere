import { state, set, subscribe } from '../state.js';
import { results } from '../api.js';
import { toast } from './toasts.js';

const STATUS_TEXT = {
  ok: 'API ready',
  degraded: 'API up · model not ready',
  down: 'API offline',
  unknown: 'Connecting…',
};

/**
 * Dates offered = dates present in the surface store (web/data/dates.json), clipped to the
 * /meta range. If that list is missing we fall back to a native date input bounded by /meta.
 */
async function availableDates(meta) {
  try {
    const { dates } = await results('dates');
    return dates.filter((d) => d >= meta.min_date && d <= meta.max_date);
  } catch {
    return [];
  }
}

export async function populateDates(meta) {
  let picker = document.getElementById('date-picker');
  const dates = await availableDates(meta);

  if (dates.length) {
    picker.innerHTML = dates.map((d) => `<option value="${d}">${d}</option>`).join('');
    picker.title = `${dates.length} dates with surface observations in the local store`;
  } else {
    const input = document.createElement('input');
    input.type = 'date';
    input.id = picker.id;
    input.className = 'input input--mono';
    input.min = meta.min_date;
    input.max = meta.max_date;
    input.setAttribute('aria-describedby', 'date-hint');
    picker.replaceWith(input);
    picker = input;
  }

  const initial = dates.includes(state.date) ? state.date : dates.length ? dates[Math.floor(dates.length / 2)] : meta.max_date;
  picker.value = initial;
  picker.disabled = false;
  set({ date: initial });

  picker.addEventListener('change', () => {
    const v = picker.value;
    if (!v || v < meta.min_date || v > meta.max_date) {
      toast(`Choose a date between ${meta.min_date} and ${meta.max_date}.`, { kind: 'warn' });
      picker.value = state.date;
      return;
    }
    set({ date: v });
  });
  subscribe((s, changed) => { if ('date' in changed && picker.value !== s.date) picker.value = s.date; });
  return dates;
}

export function initTopbar({ onExport }) {
  // Mode switch (Nowcast = SST + SLA only; Delayed = all sensors). It changes how the
  // ablation results are read; /predict itself has no mode parameter.
  const modeSwitch = document.getElementById('mode-switch');
  const paintMode = () => {
    for (const b of modeSwitch.querySelectorAll('button')) b.setAttribute('aria-checked', String(b.dataset.mode === state.mode));
  };
  modeSwitch.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b) set({ mode: b.dataset.mode });
  });
  modeSwitch.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      set({ mode: state.mode === 'nowcast' ? 'delayed' : 'nowcast' });
      modeSwitch.querySelector('[aria-checked="true"]')?.focus();
    }
  });
  paintMode();

  // Status pill
  const pill = document.getElementById('status-pill');
  const paintStatus = () => {
    const key = state.demo ? 'demo' : state.api;
    pill.dataset.state = key;
    pill.querySelector('.status-pill__text').textContent = state.demo ? `Demo · ${STATUS_TEXT[state.api]}` : STATUS_TEXT[state.api];
    pill.title = state.ready
      ? `Model ${state.ready.details?.model_version} · store ${state.ready.store_open ? 'open' : 'closed'}`
      : STATUS_TEXT[state.api];
  };
  pill.addEventListener('click', () => { location.hash = '#/overview'; requestAnimationFrame(() => document.getElementById('system-status')?.scrollIntoView({ block: 'center' })); });

  // Settings popover
  const btn = document.getElementById('settings-btn');
  const pop = document.getElementById('settings');
  const setOpen = (open) => { pop.hidden = !open; btn.setAttribute('aria-expanded', String(open)); };
  btn.addEventListener('click', () => setOpen(pop.hidden));
  document.addEventListener('click', (e) => { if (!pop.hidden && !pop.contains(e.target) && !btn.contains(e.target)) setOpen(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !pop.hidden) { setOpen(false); btn.focus(); } });

  const perf = document.getElementById('perf-toggle');
  const demo = document.getElementById('demo-toggle');
  perf.checked = state.perf;
  demo.checked = state.demo;
  perf.addEventListener('change', () => set({ perf: perf.checked }));
  demo.addEventListener('change', () => set({ demo: demo.checked }));
  document.getElementById('export-btn').addEventListener('click', () => { setOpen(false); onExport(); });

  const paintDemo = () => {
    document.getElementById('demo-badge').hidden = !state.demo;
    document.getElementById('demo-banner').hidden = !state.demo;
    document.body.classList.toggle('demo-on', state.demo);
    demo.checked = state.demo;
  };

  subscribe((s, changed) => {
    if ('mode' in changed) paintMode();
    if ('api' in changed || 'demo' in changed || 'ready' in changed) paintStatus();
    if ('demo' in changed) paintDemo();
    if ('perf' in changed) perf.checked = s.perf;
  });
  paintStatus();
  paintDemo();
}
