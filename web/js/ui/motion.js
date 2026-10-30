// Interaction and motion layer: page transitions, a request progress bar, card spotlight and
// tilt, click ripples, a sliding nav indicator and update pulses. Everything here is cosmetic,
// delegated from document level so tabs need no wiring, and switched off by reduced motion or
// performance mode (body.reduced / body.perf).

const quiet = () => document.body.classList.contains('reduced') || document.body.classList.contains('perf');
const coarse = window.matchMedia('(pointer: coarse)');

// ── Request progress bar ──────────────────────────────────────────────────────
let inflight = 0;
let hideTimer;
function paintProgress() {
  const bar = document.getElementById('progress');
  if (!bar) return;
  clearTimeout(hideTimer);
  if (inflight > 0) {
    bar.classList.add('is-active');
    bar.classList.remove('is-done');
  } else {
    bar.classList.add('is-done');
    hideTimer = setTimeout(() => bar.classList.remove('is-active', 'is-done'), 450);
  }
}
/** api.js reports each request start (+1) and end (-1). */
export function trackRequest(delta) {
  inflight = Math.max(0, inflight + delta);
  paintProgress();
}

// ── Card spotlight (cursor-following glow) and stat-tile tilt ─────────────────
function onPointerMove(e) {
  if (quiet() || coarse.matches) return;
  const card = e.target.closest?.('.card');
  if (!card) return;
  const r = card.getBoundingClientRect();
  const x = e.clientX - r.left;
  const y = e.clientY - r.top;
  card.style.setProperty('--mx', `${x}px`);
  card.style.setProperty('--my', `${y}px`);
  if (card.classList.contains('stat-card') || card.classList.contains('metric-card')) {
    const rx = ((y / r.height) - 0.5) * -5;
    const ry = ((x / r.width) - 0.5) * 6;
    card.style.transform = `perspective(900px) rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg) translateY(-2px)`;
  }
}
function onPointerOut(e) {
  const card = e.target.closest?.('.card');
  if (card && !card.contains(e.relatedTarget)) card.style.transform = '';
}

// ── Click ripples on buttons, chips and segmented controls ────────────────────
function onPointerDown(e) {
  if (quiet()) return;
  const host = e.target.closest?.('.btn, .chip, .segmented button, .nav__link, .icon-btn');
  if (!host) return;
  const r = host.getBoundingClientRect();
  const size = Math.max(r.width, r.height) * 1.6;
  const dot = document.createElement('span');
  dot.className = 'ripple';
  dot.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - r.left - size / 2}px;top:${e.clientY - r.top - size / 2}px`;
  host.append(dot);
  dot.addEventListener('animationend', () => dot.remove(), { once: true });
}

// ── Sliding nav indicator ─────────────────────────────────────────────────────
export function moveNavIndicator() {
  const nav = document.getElementById('nav');
  const active = nav?.querySelector('[aria-current="page"]');
  let ind = nav?.querySelector('.nav__indicator');
  if (!nav || !active) return;
  if (!ind) {
    ind = document.createElement('span');
    ind.className = 'nav__indicator';
    ind.setAttribute('aria-hidden', 'true');
    nav.prepend(ind);
  }
  ind.style.transform = `translateY(${active.offsetTop}px)`;
  ind.style.height = `${active.offsetHeight}px`;
  nav.classList.add('has-indicator');
}

// ── Page transition: a sweep of light down the water column, then the page rises in ──
export function pageIn(page) {
  if (quiet() || !page) return;
  const sweep = document.getElementById('page-sweep');
  if (sweep) {
    sweep.classList.remove('is-on');
    void sweep.offsetWidth; // restart the animation
    sweep.classList.add('is-on');
  }
  const gsap = window.gsap;
  if (!gsap) return;
  const intro = page.querySelector('.page__intro');
  if (intro) {
    gsap.fromTo(intro.children, { opacity: 0, y: 18, filter: 'blur(6px)' }, {
      opacity: 1, y: 0, filter: 'blur(0px)', duration: 0.7, ease: 'power3.out', stagger: 0.08, clearProps: 'filter,transform',
    });
  }
}

// ── Pulse a value when it changes (stats, KPIs) ───────────────────────────────
export function pulse(el) {
  if (quiet() || !el) return;
  el.classList.remove('is-pulsing');
  void el.offsetWidth;
  el.classList.add('is-pulsing');
}

export function initMotion() {
  document.addEventListener('pointermove', onPointerMove, { passive: true });
  document.addEventListener('pointerout', onPointerOut, { passive: true });
  document.addEventListener('pointerdown', onPointerDown, { passive: true });
  window.addEventListener('resize', moveNavIndicator, { passive: true });
}
