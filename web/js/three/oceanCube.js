// The study domain as a 3-D volume: horizontal temperature slices stacked by depth, coastline
// on the surface plane, orbit controls. Slices are DataTextures coloured with the shared thermal map.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { thermalRGB, T_RANGE } from '../charts/theme.js';

const SX = 6;          // 60° of longitude
const SZ = 2.5;        // 25° of latitude
const SY = 2.6;        // 0–1000 m (square-root stretched)
const DOM = { lon0: 45, lon1: 105, lat0: 5, lat1: 30 };

const px = (lon) => ((lon - DOM.lon0) / (DOM.lon1 - DOM.lon0) - 0.5) * SX;
const pz = (lat) => -((lat - DOM.lat0) / (DOM.lat1 - DOM.lat0) - 0.5) * SZ;
export const py = (depth) => -Math.sqrt(depth / 1000) * SY;

/**
 * @param {HTMLElement} host container (positioned)
 * @param {{land:number[][][], labelsEl:HTMLElement, reduced:boolean}} opts
 */
export function createOceanCube(host, { land, labelsEl, reduced }) {
  const canvas = document.createElement('canvas');
  host.prepend(canvas);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  camera.position.set(4.6, 3.2, 6.2);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 4;
  controls.maxDistance = 14;
  controls.target.set(0, -SY / 2, 0);
  controls.autoRotate = !reduced;
  controls.autoRotateSpeed = 0.35;
  controls.addEventListener('start', () => { controls.autoRotate = false; });

  const disposables = [];
  const track = (o) => { disposables.push(o); return o; };

  // Box edges
  const boxGeo = track(new THREE.EdgesGeometry(new THREE.BoxGeometry(SX, SY, SZ)));
  const box = new THREE.LineSegments(boxGeo, track(new THREE.LineBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.25 })));
  box.position.y = -SY / 2;
  scene.add(box);

  // Coastline on the surface plane
  const coast = [];
  for (const ring of land) {
    for (let i = 0; i < ring.length - 1; i++) {
      const [a, b] = [ring[i], ring[i + 1]];
      const inside = (p) => p[0] >= DOM.lon0 && p[0] <= DOM.lon1 && p[1] >= DOM.lat0 && p[1] <= DOM.lat1;
      if (!inside(a) || !inside(b)) continue;
      coast.push(new THREE.Vector3(px(a[0]), 0.012, pz(a[1])), new THREE.Vector3(px(b[0]), 0.012, pz(b[1])));
    }
  }
  const coastGeo = track(new THREE.BufferGeometry().setFromPoints(coast));
  scene.add(new THREE.LineSegments(coastGeo, track(new THREE.LineBasicMaterial({ color: 0xbfe9f5, transparent: true, opacity: 0.7 }))));

  const planeGeo = track(new THREE.PlaneGeometry(SX, SZ));
  let slices = [];   // { depth, mesh, tex, label }
  let active = null;

  function clearSlices() {
    for (const s of slices) {
      scene.remove(s.mesh);
      s.tex.dispose();
      s.mesh.material.dispose();
      s.label.remove();
    }
    slices = [];
  }

  /**
   * @param {{depths:number[], lats:number[], lons:number[], values:(number|null)[][][]}} grid
   *        values[depthIndex][latIndex][lonIndex]
   * @param {number[]} show depths to draw as slices
   */
  function setData(grid, show) {
    clearSlices();
    const nx = grid.lons.length;
    const nz = grid.lats.length;
    for (const depth of show) {
      const di = grid.depths.indexOf(depth);
      if (di < 0) continue;
      const data = new Uint8Array(nx * nz * 4);
      for (let j = 0; j < nz; j++) {
        for (let i = 0; i < nx; i++) {
          const v = grid.values[di][j][i];
          const k = (j * nx + i) * 4;
          if (v == null) { data[k + 3] = 0; continue; }
          const [r, g, b] = thermalRGB(v, T_RANGE);
          data[k] = r; data[k + 1] = g; data[k + 2] = b; data[k + 3] = 255;
        }
      }
      const tex = new THREE.DataTexture(data, nx, nz, THREE.RGBAFormat);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.magFilter = THREE.NearestFilter; // show true grid cells; linear would smear land into the ocean
      tex.minFilter = THREE.NearestFilter;
      tex.needsUpdate = true;
      const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0.4, side: THREE.DoubleSide, depthWrite: false });
      const mesh = new THREE.Mesh(planeGeo, mat);
      mesh.rotation.x = -Math.PI / 2;   // texture row 0 (south) ends up at +z (front)
      mesh.position.y = py(depth);
      scene.add(mesh);
      const label = document.createElement('span');
      label.className = 'cube-label';
      label.textContent = `${depth} m`;
      labelsEl.append(label);
      slices.push({ depth, mesh, tex, label });
    }
    setActive(active ?? show[0]);
  }

  function setActive(depth) {
    active = depth;
    for (const s of slices) {
      const on = s.depth === depth;
      s.mesh.material.opacity = on ? 0.96 : 0.28;
      s.mesh.renderOrder = on ? 2 : 1;
      s.label.classList.toggle('is-active', on);
    }
  }

  const resize = () => {
    const w = host.clientWidth;
    const h = host.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  const ro = new ResizeObserver(resize);
  ro.observe(host);
  resize();

  const anchor = new THREE.Vector3();
  let raf = 0;
  let running = false;
  const frame = () => {
    raf = requestAnimationFrame(frame);
    controls.update();
    renderer.render(scene, camera);
    const w = host.clientWidth;
    const h = host.clientHeight;
    for (const s of slices) {
      anchor.set(SX / 2 + 0.12, s.mesh.position.y, SZ / 2).project(camera);
      s.label.style.transform = `translate(${((anchor.x + 1) / 2) * w}px, ${((1 - anchor.y) / 2) * h - 8}px)`;
    }
  };

  return {
    setData,
    setActive,
    start() { if (!running) { running = true; frame(); } },
    stop() { running = false; cancelAnimationFrame(raf); },
    dispose() {
      this.stop();
      ro.disconnect();
      clearSlices();
      controls.dispose();
      disposables.forEach((d) => d.dispose());
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    },
  };
}
