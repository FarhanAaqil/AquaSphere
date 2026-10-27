/**
 * AquaSphere Landing Entry ("Descent")
 * Imports scene + scroll, handles pause motion, initializes experience.
 */

import { initScene } from './scene.js';
import { initScroll } from './scroll.js';

document.addEventListener('DOMContentLoaded', () => {
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
});
