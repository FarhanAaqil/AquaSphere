// Current "depth" of the page (0 = surface, 1 = 1000 m). Tints CSS and the background scene.

let sink = null;

export function registerDepthSink(fn) {
  sink = fn;
}

export function setDepth(t) {
  const v = Math.min(1, Math.max(0, t));
  document.documentElement.style.setProperty('--depth-t', v.toFixed(3));
  sink?.(v);
}
