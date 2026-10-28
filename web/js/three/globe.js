// Hero globe: Earth zooms in on the North Indian Ocean, study domain outlined, Arabian Sea and
// Bay of Bengal labelled, real Argo float positions (web/data/floats.json) bobbing as glints.

import * as THREE from 'three';

const R = 1;

export function latLonToVec3(lat, lon, r = R) {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 180);
  return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
}

const OCEAN_VERT = /* glsl */ `
  varying vec3 vNormal; varying vec3 vView;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vView = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }`;
const OCEAN_FRAG = /* glsl */ `
  varying vec3 vNormal; varying vec3 vView;
  void main() {
    float rim = pow(1.0 - max(dot(vNormal, vView), 0.0), 2.5);
    float light = 0.35 + 0.65 * max(dot(vNormal, normalize(vec3(0.4, 0.6, 0.7))), 0.0);
    vec3 base = mix(vec3(0.012, 0.06, 0.13), vec3(0.03, 0.17, 0.29), light);
    gl_FragColor = vec4(base + vec3(0.13, 0.83, 0.93) * rim * 0.9, 1.0);
  }`;

const FLOAT_VERT = /* glsl */ `
  uniform float uTime; uniform float uPixelRatio;
  attribute float aSeed;
  varying float vPulse;
  void main() {
    vec3 p = position * (1.0 + 0.004 * sin(uTime * 1.6 + aSeed * 30.0));  // gentle bob
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vPulse = 0.6 + 0.4 * sin(uTime * 2.2 + aSeed * 50.0);
    gl_PointSize = (5.0 + 3.0 * vPulse) * uPixelRatio;
    gl_Position = projectionMatrix * mv;
  }`;
const FLOAT_FRAG = /* glsl */ `
  varying float vPulse;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float core = smoothstep(0.18, 0.0, d);
    float halo = smoothstep(0.5, 0.0, d) * 0.55;
    float a = (core + halo) * vPulse;
    if (a < 0.02) discard;
    gl_FragColor = vec4(mix(vec3(0.13, 0.83, 0.93), vec3(1.0), core), a);
  }`;

function ringToLine(ring, r) {
  const pts = [];
  for (let i = 0; i < ring.length - 1; i++) {
    pts.push(latLonToVec3(ring[i][1], ring[i][0], r), latLonToVec3(ring[i + 1][1], ring[i + 1][0], r));
  }
  return pts;
}

/**
 * @param {HTMLCanvasElement} canvas
 * @param {{land: number[][][], floats: {lat:number, lon:number}[], domain: object, labelsEl: HTMLElement, reduced: boolean}} opts
 */
export function createGlobe(canvas, { land, floats, domain, labelsEl, reduced }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 50);

  const globe = new THREE.Group();
  scene.add(globe);

  const sphereGeo = new THREE.SphereGeometry(R, 96, 64);
  const oceanMat = new THREE.ShaderMaterial({ vertexShader: OCEAN_VERT, fragmentShader: OCEAN_FRAG });
  globe.add(new THREE.Mesh(sphereGeo, oceanMat));

  // Atmosphere halo
  const haloGeo = new THREE.SphereGeometry(R * 1.12, 64, 48);
  const haloMat = new THREE.ShaderMaterial({
    vertexShader: OCEAN_VERT,
    fragmentShader: /* glsl */ `varying vec3 vNormal; varying vec3 vView;
      void main() { float a = pow(1.0 - abs(dot(vNormal, vView)), 3.0); gl_FragColor = vec4(0.2, 0.75, 0.95, a * 0.55); }`,
    side: THREE.BackSide, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  globe.add(new THREE.Mesh(haloGeo, haloMat));

  // Coastlines
  const landPts = land.flatMap((ring) => ringToLine(ring, R * 1.002));
  const landGeo = new THREE.BufferGeometry().setFromPoints(landPts);
  const landMat = new THREE.LineBasicMaterial({ color: 0x7fb6cf, transparent: true, opacity: 0.55 });
  globe.add(new THREE.LineSegments(landGeo, landMat));

  // Study domain outline (5–30°N, 45–105°E)
  const { lat_min: la0, lat_max: la1, lon_min: lo0, lon_max: lo1 } = domain;
  const boxRing = [];
  for (let lo = lo0; lo <= lo1; lo += 1) boxRing.push([lo, la0]);
  for (let la = la0; la <= la1; la += 1) boxRing.push([lo1, la]);
  for (let lo = lo1; lo >= lo0; lo -= 1) boxRing.push([lo, la1]);
  for (let la = la1; la >= la0; la -= 1) boxRing.push([lo0, la]);
  const boxGeo = new THREE.BufferGeometry().setFromPoints(ringToLine(boxRing, R * 1.004));
  const boxMat = new THREE.LineBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.95 });
  globe.add(new THREE.LineSegments(boxGeo, boxMat));

  // Floats
  const fPos = new Float32Array(floats.length * 3);
  const fSeed = new Float32Array(floats.length);
  floats.forEach((f, i) => {
    latLonToVec3(f.lat, f.lon, R * 1.006).toArray(fPos, i * 3);
    fSeed[i] = (i * 0.618) % 1;
  });
  const floatGeo = new THREE.BufferGeometry();
  floatGeo.setAttribute('position', new THREE.BufferAttribute(fPos, 3));
  floatGeo.setAttribute('aSeed', new THREE.BufferAttribute(fSeed, 1));
  const floatMat = new THREE.ShaderMaterial({
    vertexShader: FLOAT_VERT, fragmentShader: FLOAT_FRAG,
    uniforms: { uTime: { value: 0 }, uPixelRatio: { value: renderer.getPixelRatio() } },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  globe.add(new THREE.Points(floatGeo, floatMat));

  // HTML labels projected each frame
  const labels = [
    { text: 'Arabian Sea', lat: 15, lon: 64 },
    { text: 'Bay of Bengal', lat: 15, lon: 89 },
  ].map((l) => {
    const el = document.createElement('span');
    el.className = 'globe-label';
    el.textContent = l.text;
    labelsEl.append(el);
    return { ...l, el, v: latLonToVec3(l.lat, l.lon, R * 1.01) };
  });

  // Camera: from far, off-axis to a close view centred on the NIO
  const focus = latLonToVec3(17.5, 75, 1);
  const startPos = latLonToVec3(10, 20, 6.5);
  const endPos = focus.clone().multiplyScalar(3.3).add(new THREE.Vector3(0, -0.35, 0));
  const anim = { t: reduced ? 1 : 0 };
  const placeCamera = () => {
    const e = anim.t;
    camera.position.copy(startPos).lerp(endPos, e).normalize().multiplyScalar(THREE.MathUtils.lerp(startPos.length(), endPos.length(), e));
    camera.lookAt(focus.clone().multiplyScalar(e * 0.55));
  };
  placeCamera();
  let tween = null;
  if (!reduced && window.gsap) {
    tween = window.gsap.to(anim, { t: 1, duration: 3.2, ease: 'power3.inOut', delay: 0.2, onUpdate: placeCamera });
  }

  const pointer = { x: 0, y: 0 };
  const onMove = (e) => {
    const r = canvas.getBoundingClientRect();
    pointer.x = ((e.clientX - r.left) / r.width - 0.5) * 2;
    pointer.y = ((e.clientY - r.top) / r.height - 0.5) * 2;
  };
  window.addEventListener('pointermove', onMove, { passive: true });

  const resize = () => {
    const { clientWidth: w, clientHeight: h } = canvas;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  const tmp = new THREE.Vector3();
  const camDir = new THREE.Vector3();
  let raf = 0;
  let running = false;
  const clock = new THREE.Clock();
  const frame = () => {
    raf = requestAnimationFrame(frame);
    const t = clock.getElapsedTime();
    floatMat.uniforms.uTime.value = t;
    // gentle drift + pointer tilt
    const targetY = reduced ? 0 : Math.sin(t * 0.08) * 0.06 + pointer.x * 0.08;
    const targetX = reduced ? 0 : pointer.y * 0.05;
    globe.rotation.y += (targetY - globe.rotation.y) * 0.04;
    globe.rotation.x += (targetX - globe.rotation.x) * 0.04;
    renderer.render(scene, camera);

    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    camDir.copy(camera.position).normalize();
    for (const l of labels) {
      tmp.copy(l.v).applyMatrix4(globe.matrixWorld);
      const facing = tmp.clone().normalize().dot(camDir) > 0.2;
      tmp.project(camera);
      l.el.style.transform = `translate(-50%, -50%) translate(${((tmp.x + 1) / 2) * w}px, ${((1 - tmp.y) / 2) * h}px)`;
      l.el.style.opacity = facing ? String(Math.min(1, anim.t * 1.4 - 0.3)) : '0';
    }
  };

  return {
    start() { if (!running) { running = true; clock.getDelta(); frame(); } },
    stop() { running = false; cancelAnimationFrame(raf); },
    dispose() {
      this.stop();
      tween?.kill();
      ro.disconnect();
      window.removeEventListener('pointermove', onMove);
      labels.forEach((l) => l.el.remove());
      [sphereGeo, haloGeo, landGeo, boxGeo, floatGeo].forEach((g) => g.dispose());
      [oceanMat, haloMat, landMat, boxMat, floatMat].forEach((m) => m.dispose());
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}
