// Small helpers shared by tab modules.

import { state, subscribe } from '../state.js';
import { pulse } from '../ui/motion.js';

/** Build DOM from an HTML string (trusted, static templates only — data goes in via textContent). */
export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.childElementCount === 1 ? t.content.firstElementChild : t.content;
}

export const $ = (root, sel) => root.querySelector(sel);

/**
 * Run fn(date) once the date is known and again whenever it changes.
 * fn(null) means /meta failed (API offline) and the tab should show that state.
 */
export function onDate(ctx, fn) {
  let last;
  const fire = () => {
    if (!state.metaSettled) return;
    if (state.date === last && last !== undefined) return;
    last = state.date;
    fn(state.date);
  };
  ctx.cleanup(subscribe((s, changed) => { if ('date' in changed || 'metaSettled' in changed) fire(); }));
  fire();
}

/** Re-run fn when any of the given state keys change. */
export function onState(ctx, keys, fn) {
  ctx.cleanup(subscribe((s, changed) => { if (keys.some((k) => k in changed)) fn(s); }));
}

export function fmt(v, digits = 2, unit = '') {
  if (v == null || Number.isNaN(v)) return '—';
  return `${Number(v).toFixed(digits)}${unit}`;
}

/** Animated count-up for stat values; respects reduced motion. */
export function countUp(el, value, { digits = 2, suffix = '', duration = 1.1 } = {}) {
  if (value == null || Number.isNaN(value)) { el.textContent = '—'; return; }
  const write = (v) => { el.innerHTML = `${v.toFixed(digits)}${suffix ? `<small>${suffix}</small>` : ''}`; };
  if (state.reduced || state.perf || !window.gsap) return write(value);
  const o = { v: 0 };
  window.gsap.to(o, { v: value, duration, ease: 'power2.out', onUpdate: () => write(o.v), onComplete: () => pulse(el) });
}

/** Staggered reveal of cards as they enter the viewport. */
export function reveal(root, ctx, sel = '.card') {
  const items = [...root.querySelectorAll(sel)];
  if (state.reduced || state.perf || !window.gsap || !('IntersectionObserver' in window)) return;
  items.forEach((el) => el.classList.add('reveal'));
  const io = new IntersectionObserver((entries) => {
    const shown = entries.filter((e) => e.isIntersecting).map((e) => e.target);
    if (!shown.length) return;
    shown.forEach((el) => io.unobserve(el));
    window.gsap.to(shown, { opacity: 1, y: 0, duration: 0.6, ease: 'power3.out', stagger: 0.07, clearProps: 'transform' });
  }, { rootMargin: '0px 0px -8% 0px' });
  items.forEach((el) => io.observe(el));
  ctx.cleanup(() => io.disconnect());
}

/** Card scaffold: returns { card, body, meta } where meta holds badges. */
export function card({ title, sub = '', cls = '', bodyCls = '' } = {}) {
  const c = h(`<section class="card ${cls}">
    <div class="card__head"><div><h3 class="card__title"></h3><p class="card__sub"></p></div><div class="card__meta"></div></div>
    <div class="card__body ${bodyCls}"></div></section>`);
  c.querySelector('.card__title').textContent = title;
  const subEl = c.querySelector('.card__sub');
  if (sub) subEl.textContent = sub; else subEl.remove();
  return { card: c, body: c.querySelector('.card__body'), meta: c.querySelector('.card__meta') };
}

export function setBadges(metaEl, badges) {
  metaEl.replaceChildren(...[].concat(badges).filter(Boolean));
}
