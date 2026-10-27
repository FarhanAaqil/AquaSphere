/**
 * AquaSphere Landing Entry ("Descent")
 * Imports scene + scroll, handles pause motion, initializes experience and data-driven evidence.
 */

import { initScene } from './scene.js';
import { initScroll, setupEvidenceBars } from './scroll.js';

document.addEventListener('DOMContentLoaded', async () => {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const state = { p: 0, tp: 0, paused: false };

  const pauseBtn = document.getElementById('pause');
  if (pauseBtn) {
    pauseBtn.addEventListener('click', () => {
      state.paused = !state.paused;
      pauseBtn.setAttribute('aria-pressed', state.paused);
      pauseBtn.textContent = state.paused ? 'Resume motion' : 'Pause motion';
    });
  }

  initScroll(state, reduce);
  initScene(state, reduce);

  // Dynamic metrics population from /data/metrics.json (or /validation API fallback)
  try {
    const res = await fetch('/data/metrics.json');
    if (res.ok) {
      const metrics = await res.json();
      setupEvidenceBars(metrics, reduce);
    } else {
      const fallbackRes = await fetch('/validation');
      if (fallbackRes.ok) {
        const metrics = await fallbackRes.json();
        setupEvidenceBars(metrics, reduce);
      }
    }
  } catch (err) {
    console.error('Failed to load metrics data:', err);
  }
});
