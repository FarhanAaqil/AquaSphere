/**
 * Legacy adapter for initScene to guarantee full backwards compatibility.
 */
import { OceanScene } from '../scene3d.js';

export function initScene(S, reduce) {
  if (!window.oceanSceneInstance) {
    window.oceanSceneInstance = new OceanScene('gl');
  }
  return window.oceanSceneInstance;
}
