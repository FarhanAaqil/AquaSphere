// Global underwater background: drifting marine snow, caustic light from above, depth fog.
// All motion runs in shaders (no per-frame CPU work besides uniforms). Pauses when hidden.

import * as THREE from 'three';

const SNOW_VERT = /* glsl */ `
  uniform float uTime;
  uniform float uPixelRatio;
  attribute float aSize;
  attribute float aSeed;
  varying float vAlpha;
  void main() {
    vec3 p = position;
    // slow sinking + lateral wobble, wrapped in a 40-unit tall column
    p.y = mod(p.y - uTime * (0.25 + aSeed * 0.35) + 20.0, 40.0) - 20.0;
    p.x += sin(uTime * 0.3 + aSeed * 12.0) * 0.6;
    p.z += cos(uTime * 0.23 + aSeed * 7.0) * 0.4;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = aSize * uPixelRatio * (28.0 / -mv.z);
    vAlpha = smoothstep(60.0, 8.0, -mv.z) * (0.35 + aSeed * 0.5);
  }`;

const SNOW_FRAG = /* glsl */ `
  uniform vec3 uColor;
  varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.0, d) * vAlpha;
    if (a < 0.01) discard;
    gl_FragColor = vec4(uColor, a);
  }`;

const CAUSTIC_FRAG = /* glsl */ `
  uniform float uTime;
  uniform float uStrength;
  varying vec2 vUv;
  float caustic(vec2 uv, float t) {
    vec2 p = uv * 7.0;
    float c = 0.0;
    for (int i = 1; i < 4; i++) {
      float fi = float(i);
      p += vec2(sin(t * 0.35 + p.y * 0.9 * fi), cos(t * 0.3 + p.x * 0.8 * fi)) * 0.45 / fi;
      c += abs(sin(p.x + p.y)) ;
    }
    return pow(1.0 - c / 3.0, 6.0);
  }
  void main() {
    float c = caustic(vUv, uTime);
    float fade = smoothstep(0.0, 0.9, vUv.y);  // brighter toward the surface
    gl_FragColor = vec4(vec3(0.40, 0.91, 0.98) * c * fade * uStrength, c * fade * uStrength);
  }`;

const PLANE_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;

const SURFACE = new THREE.Color('#0b3a5c');
const DEEP = new THREE.Color('#020617');

export function createBackground(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(SURFACE.clone(), 0.028);
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 120);
  camera.position.set(0, 0, 18);

  // Marine snow
  const N = 1400;
  const pos = new Float32Array(N * 3);
  const size = new Float32Array(N);
  const seed = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 60;
    pos[i * 3 + 1] = (Math.random() - 0.5) * 40;
    pos[i * 3 + 2] = -Math.random() * 50 + 10;
    size[i] = 0.6 + Math.random() * 2.2;
    seed[i] = Math.random();
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('aSize', new THREE.BufferAttribute(size, 1));
  geo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
  const snowMat = new THREE.ShaderMaterial({
    vertexShader: SNOW_VERT,
    fragmentShader: SNOW_FRAG,
    uniforms: { uTime: { value: 0 }, uPixelRatio: { value: renderer.getPixelRatio() }, uColor: { value: new THREE.Color('#bdf4ff') } },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const snow = new THREE.Points(geo, snowMat);
  scene.add(snow);

  // Caustic light sheet near the top of the view
  const causticMat = new THREE.ShaderMaterial({
    vertexShader: PLANE_VERT,
    fragmentShader: CAUSTIC_FRAG,
    uniforms: { uTime: { value: 0 }, uStrength: { value: 0.32 } },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const caustics = new THREE.Mesh(new THREE.PlaneGeometry(70, 30), causticMat);
  caustics.position.set(0, 10, -14);
  caustics.rotation.x = 0.35;
  scene.add(caustics);

  // Parallax
  const target = { x: 0, y: 0 };
  const onMove = (e) => {
    target.x = (e.clientX / window.innerWidth - 0.5) * 2;
    target.y = (e.clientY / window.innerHeight - 0.5) * 2;
  };
  window.addEventListener('pointermove', onMove, { passive: true });

  const resize = () => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  resize();
  window.addEventListener('resize', resize);

  let depth = 0;
  let raf = 0;
  const clock = new THREE.Clock();
  const frame = () => {
    raf = requestAnimationFrame(frame);
    const t = clock.getElapsedTime();
    snowMat.uniforms.uTime.value = t;
    causticMat.uniforms.uTime.value = t;
    camera.position.x += (target.x * 1.2 - camera.position.x) * 0.03;
    camera.position.y += (-target.y * 0.8 - camera.position.y) * 0.03;
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  };
  const onVisibility = () => {
    cancelAnimationFrame(raf);
    if (!document.hidden) { clock.getDelta(); frame(); }
  };
  document.addEventListener('visibilitychange', onVisibility);
  frame();

  return {
    /** 0 = surface, 1 = 1000 m. Dims caustics, thickens fog, shifts fog colour. */
    setDepth(t) {
      depth = Math.min(1, Math.max(0, t));
      causticMat.uniforms.uStrength.value = 0.32 * (1 - depth) ** 2;
      scene.fog.color.copy(SURFACE).lerp(DEEP, depth);
      scene.fog.density = 0.028 + depth * 0.03;
      snowMat.uniforms.uColor.value.set(depth > 0.6 ? '#9be7ff' : '#bdf4ff');
    },
    get depth() { return depth; },
    dispose() {
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
      geo.dispose();
      snowMat.dispose();
      caustics.geometry.dispose();
      causticMat.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      // A lost context can't be reused, so leave a fresh canvas for the next scene.
      const fresh = document.createElement('canvas');
      fresh.id = canvas.id;
      canvas.replaceWith(fresh);
    },
  };
}
