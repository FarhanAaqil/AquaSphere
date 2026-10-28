// Loading / unavailable / pending / empty states. Never filled with stand-in numbers.

import { badge } from './badges.js';

const icon = (id) => `<svg aria-hidden="true"><use href="assets/icons.svg#${id}"></use></svg>`;

function render(el, cls, html) {
  el.replaceChildren();
  const box = document.createElement('div');
  box.className = `state ${cls}`;
  box.innerHTML = html;
  el.append(box);
  return box;
}

export function loading(el, text = 'Loading…') {
  const box = render(el, 'state--loading', `<div class="spinner" role="progressbar" aria-label="${text}"></div><div>${text}</div>`);
  box.setAttribute('aria-busy', 'true');
  return box;
}

const ERROR_COPY = {
  unavailable: ['Data unavailable', 'The API returned 503. No surface observation exists for this request in the local store, disk cache or live feed, so nothing is shown.'],
  offline: ['API unreachable', 'The serving API did not respond. Start it with "make serve", or turn on Offline demo in display settings to explore with clearly-labelled synthetic data.'],
  not_found: ['Nothing found', 'The API has no record for this request.'],
  invalid: ['Request rejected', 'The API rejected these inputs.'],
  server: ['Server error', 'The API failed while handling this request.'],
};

export function errorState(el, err, { retry } = {}) {
  const [title, text] = ERROR_COPY[err?.kind] || ['Something went wrong', String(err?.message || err)];
  const box = render(el, 'state--error', `${icon('i-alert')}<div class="state__title"></div><div class="state__detail"></div>`);
  box.dataset.errorKind = err?.kind || 'unknown';
  box.setAttribute('role', 'alert');
  box.querySelector('.state__title').textContent = title;
  box.querySelector('.state__detail').textContent = err?.detail ? `${text} — ${err.detail}` : text;
  if (err?.kind === 'unavailable') box.prepend(badge('unavailable'));
  if (retry) {
    const b = document.createElement('button');
    b.className = 'btn btn--ghost btn--sm';
    b.innerHTML = `${icon('i-refresh')}Try again`;
    b.addEventListener('click', retry);
    box.append(b);
  }
  return box;
}

/** "Pending" — an experiment or view whose results have not been produced yet. */
export function pending(el, { title, detail, needs } = {}) {
  const box = render(el, 'state--pending', `${icon('i-clock')}<div class="state__title"></div><div class="state__detail"></div>`);
  box.prepend(badge('pending'));
  box.querySelector('.state__title').textContent = title || 'Pending';
  box.querySelector('.state__detail').textContent = detail || 'No results have been produced for this yet.';
  if (needs) {
    const n = document.createElement('div');
    n.className = 'state__detail mono';
    n.textContent = needs;
    box.append(n);
  }
  return box;
}

export function empty(el, title, detail = '') {
  const box = render(el, 'state--empty', `${icon('i-info')}<div class="state__title"></div><div class="state__detail"></div>`);
  box.querySelector('.state__title').textContent = title;
  box.querySelector('.state__detail').textContent = detail;
  return box;
}
