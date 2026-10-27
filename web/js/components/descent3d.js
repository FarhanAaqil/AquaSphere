/**
 * AquaSphere "Descent" 3D WebGL Engine (Playbook §5 & Appendix A.2)
 * Pure Three.js implementation with procedural geometries, shaders, and auto-tiering.
 */

import { QualityController } from './quality.js';

export class Descent3DEngine {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.options = {
      enableScroll: true,
      enableParallax: true,
      ...options,
    };

    this.quality = new QualityController();
    this.scene = null;
    this.camera = null;
    this.renderer = null;

    // 3D Objects
    this.surfaceMesh = null;
    this.strataGroup = null;
    this.thermoclineMesh = null;
    this.argoFloatGroup = null;
    this.particles = null;
    this.orbitArcs = [];

    // State & Camera targets
    this.scrollProgress = 0.0; // 0.0 (surface 0m) -> 1.0 (abyssal 1000m)
    this.currentDepth = 0;     // in meters
    this.mouse = { x: 0, y: 0 };
    this.parallax = { x: 0, y: 0 };
    this.cameraTargetY = 1.2;
    this.cameraCurrentY = 1.2;

    this.clock = null;
    this.animId = null;
    this.isPaused = false;
    this.observer = null;

    this.init();
  }

  init() {
    if (!window.THREE) {
      console.warn('Three.js not found, rendering static fallback.');
      this.renderFallback();
      return;
    }

    const THREE = window.THREE;
    this.clock = new THREE.Clock();

    // 1. Scene & Depth Fog
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x060b14); // --bg-0
    this.scene.fog = new THREE.FogExp2(0x060b14, 0.095);

    // 2. Camera
    const width = this.canvas.clientWidth || window.innerWidth;
    const height = this.canvas.clientHeight || window.innerHeight;
    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 80);
    this.camera.position.set(0, 1.2, 5.5);

    // 3. Renderer with quality tier DPR
    try {
      this.renderer = new THREE.WebGLRenderer({
        canvas: this.canvas,
        antialias: this.quality.tier !== 'low',
        powerPreference: 'high-performance',
        alpha: false,
      });
      this.renderer.setSize(width, height, false);
      this.renderer.setPixelRatio(this.quality.dpr);
      this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
      this.renderer.toneMappingExposure = 1.1;
    } catch (e) {
      console.warn('WebGL initialization failed:', e);
      this.renderFallback();
      return;
    }

    // 4. Lighting Rig
    this.setupLighting();

    // 5. Build "Descent" Scene Elements
    this.buildSurfaceMesh();
    this.buildSatelliteOrbitArcs();
    this.buildThermalStrata();
    this.buildArgoFloat();
    this.buildParticleField();

    // 6. Listeners & Visibility Observers
    this.setupEventListeners();
    this.setupVisibilityObserver();

    // 7. Start Render Loop
    this.animate();
  }

  setupLighting() {
    const THREE = window.THREE;

    // Ambient light (deep oceanic blue)
    const ambient = new THREE.AmbientLight(0x0d1726, 1.4);
    this.scene.add(ambient);

    // Sun directional light (warm sunlit surface at load)
    this.sunLight = new THREE.DirectionalLight(0xfff4e0, 2.2);
    this.sunLight.position.set(4, 6, 3);
    this.scene.add(this.sunLight);

    // Deep water up-light (subsurface teal glow)
    this.tealLight = new THREE.PointLight(0x2dd4bf, 2.0, 15);
    this.tealLight.position.set(-2, -1.8, 1);
    this.scene.add(this.tealLight);

    // Thermocline amber glow
    this.amberLight = new THREE.PointLight(0xf5a524, 2.5, 8);
    this.amberLight.position.set(0, -1.5, 0);
    this.scene.add(this.amberLight);
  }

  buildSurfaceMesh() {
    const THREE = window.THREE;
    const segs = this.quality.settings.surfaceSegments;
    const geo = new THREE.PlaneGeometry(16, 16, segs, segs);
    geo.rotateX(-Math.PI / 2);

    // Custom shader material for sun glints and surface waves
    this.surfaceMat = new THREE.MeshStandardMaterial({
      color: 0x142b44,
      roughness: 0.22,
      metalness: 0.35,
      wireframe: false,
      flatShading: true,
    });

    this.surfaceMesh = new THREE.Mesh(geo, this.surfaceMat);
    this.surfaceMesh.position.set(0, 0.4, 0);
    this.scene.add(this.surfaceMesh);

    // Store initial vertex positions for wave displacement
    const pos = geo.attributes.position;
    this.initialSurfacePositions = pos.clone();
  }

  buildSatelliteOrbitArcs() {
    const THREE = window.THREE;
    const curve1 = new THREE.EllipseCurve(0, 1.8, 4.8, 2.2, 0, Math.PI, false, 0.3);
    const pts1 = curve1.getPoints(50);
    const geo1 = new THREE.BufferGeometry().setFromPoints(pts1.map(p => new THREE.Vector3(p.x, p.y + 0.4, -p.y * 0.5)));

    const mat = new THREE.LineBasicMaterial({
      color: 0x2dd4bf,
      transparent: true,
      opacity: 0.35,
    });

    const arc1 = new THREE.Line(geo1, mat);
    this.scene.add(arc1);
    this.orbitArcs.push(arc1);

    // Second faint orbital path
    const curve2 = new THREE.EllipseCurve(0, 2.2, 5.4, 2.6, 0, Math.PI, false, -0.4);
    const pts2 = curve2.getPoints(50);
    const geo2 = new THREE.BufferGeometry().setFromPoints(pts2.map(p => new THREE.Vector3(p.x - 0.5, p.y + 0.6, p.y * 0.4)));
    const arc2 = new THREE.Line(geo2, mat);
    this.scene.add(arc2);
    this.orbitArcs.push(arc2);
  }

  buildThermalStrata() {
    const THREE = window.THREE;
    this.strataGroup = new THREE.Group();

    // 1. Epipelagic layer (0 - 100m)
    const epiGeo = new THREE.CylinderGeometry(3.6, 3.4, 0.9, 32, 1, true);
    const epiMat = new THREE.MeshBasicMaterial({
      color: 0x1a405c,
      transparent: true,
      opacity: 0.25,
      side: THREE.DoubleSide,
    });
    const epiMesh = new THREE.Mesh(epiGeo, epiMat);
    epiMesh.position.y = -0.3;
    this.strataGroup.add(epiMesh);

    // 2. THERMOCLINE LAYER (100 - 200m) — Warm Amber Ribbon (Playbook §A.2)
    const thermoGeo = new THREE.CylinderGeometry(3.4, 3.2, 0.6, 32, 1, false);
    const thermoMat = new THREE.MeshStandardMaterial({
      color: 0xf5a524, // --accent-warm
      emissive: 0xf5a524,
      emissiveIntensity: 0.45,
      roughness: 0.3,
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
    });
    this.thermoclineMesh = new THREE.Mesh(thermoGeo, thermoMat);
    this.thermoclineMesh.position.y = -1.2;
    this.strataGroup.add(this.thermoclineMesh);

    // Thermocline glowing indicator ring
    const ringGeo = new THREE.TorusGeometry(3.42, 0.025, 12, 64);
    ringGeo.rotateX(Math.PI / 2);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xf5a524,
      transparent: true,
      opacity: 0.85,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.y = -1.2;
    this.strataGroup.add(ring);

    // 3. Mesopelagic layer (200 - 500m)
    const mesoGeo = new THREE.CylinderGeometry(3.2, 2.9, 1.8, 32, 1, true);
    const mesoMat = new THREE.MeshBasicMaterial({
      color: 0x0d2842,
      transparent: true,
      opacity: 0.3,
      side: THREE.DoubleSide,
    });
    const mesoMesh = new THREE.Mesh(mesoGeo, mesoMat);
    mesoMesh.position.y = -2.4;
    this.strataGroup.add(mesoMesh);

    // 4. Bathypelagic & Abyssal floor (500 - 1000m)
    const bathyGeo = new THREE.CylinderGeometry(2.9, 2.5, 2.4, 32, 1, true);
    const bathyMat = new THREE.MeshBasicMaterial({
      color: 0x071524,
      transparent: true,
      opacity: 0.45,
      side: THREE.DoubleSide,
    });
    const bathyMesh = new THREE.Mesh(bathyGeo, bathyMat);
    bathyMesh.position.y = -4.5;
    this.strataGroup.add(bathyMesh);

    // Benthic seabed slab grid at 1000m
    const seabedGeo = new THREE.PlaneGeometry(8, 8, 16, 16);
    seabedGeo.rotateX(-Math.PI / 2);
    const seabedMat = new THREE.MeshBasicMaterial({
      color: 0x2dd4bf,
      wireframe: true,
      transparent: true,
      opacity: 0.18,
    });
    const seabedMesh = new THREE.Mesh(seabedGeo, seabedMat);
    seabedMesh.position.y = -5.8;
    this.strataGroup.add(seabedMesh);

    this.scene.add(this.strataGroup);
  }

  buildArgoFloat() {
    const THREE = window.THREE;
    this.argoFloatGroup = new THREE.Group();

    // Sleek yellow autonomous float cylinder body
    const bodyGeo = new THREE.CylinderGeometry(0.12, 0.12, 0.95, 24);
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0xe6b800, // Argo yellow
      roughness: 0.35,
      metalness: 0.2,
    });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    this.argoFloatGroup.add(body);

    // CTD sensor antenna cap on top
    const capGeo = new THREE.CylinderGeometry(0.08, 0.12, 0.18, 24);
    const capMat = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.4 });
    const cap = new THREE.Mesh(capGeo, capMat);
    cap.position.y = 0.55;
    this.argoFloatGroup.add(cap);

    // Sensor probe needle
    const needleGeo = new THREE.CylinderGeometry(0.015, 0.015, 0.35, 12);
    const needleMat = new THREE.MeshBasicMaterial({ color: 0x2dd4bf });
    const needle = new THREE.Mesh(needleGeo, needleMat);
    needle.position.y = 0.75;
    this.argoFloatGroup.add(needle);

    // Telemetry sensor pulse ring
    const pulseGeo = new THREE.RingGeometry(0.15, 0.19, 24);
    pulseGeo.rotateX(Math.PI / 2);
    const pulseMat = new THREE.MeshBasicMaterial({
      color: 0x2dd4bf,
      transparent: true,
      opacity: 0.7,
      side: THREE.DoubleSide,
    });
    this.floatPulseRing = new THREE.Mesh(pulseGeo, pulseMat);
    this.floatPulseRing.position.y = 0.88;
    this.argoFloatGroup.add(this.floatPulseRing);

    // Initial position in thermocline layer
    this.argoFloatGroup.position.set(1.4, -1.4, 0.5);
    this.scene.add(this.argoFloatGroup);
  }

  buildParticleField() {
    const THREE = window.THREE;
    const count = this.quality.settings.particleCount;
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const scales = new Float32Array(count);

    for (let i = 0; i < count; i++) {
      // Cylindrical spread through water column
      const r = Math.random() * 4.2;
      const theta = Math.random() * Math.PI * 2;
      positions[i * 3] = r * Math.cos(theta);
      positions[i * 3 + 1] = (Math.random() * 7.0) - 5.8; // Y: +1.2 down to -5.8m
      positions[i * 3 + 2] = r * Math.sin(theta);
      scales[i] = Math.random() * 0.035 + 0.015;
    }

    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('scale', new THREE.BufferAttribute(scales, 1));

    const mat = new THREE.PointsMaterial({
      color: 0x9fb0c8,
      size: 0.035,
      transparent: true,
      opacity: 0.5,
      blending: THREE.AdditiveBlending,
    });

    this.particles = new THREE.Points(geo, mat);
    this.scene.add(this.particles);
  }

  setScrollProgress(progress) {
    // progress is 0.0 (top) to 1.0 (bottom)
    this.scrollProgress = Math.max(0, Math.min(1, progress));
    this.currentDepth = Math.round(this.scrollProgress * 1000);

    // Camera dives from surface y = 1.2 to benthic y = -5.2
    this.cameraTargetY = 1.2 - (this.scrollProgress * 6.4);

    // Darken fog and directional light as depth increases
    if (this.sunLight) {
      this.sunLight.intensity = Math.max(0.1, 2.2 * (1.0 - this.scrollProgress * 1.5));
    }

    // Argo float moves dynamically with the dive
    if (this.argoFloatGroup) {
      // Dives and samples in the 100m - 700m zone
      const floatY = -1.2 - (this.scrollProgress * 3.5);
      this.argoFloatGroup.position.y = floatY;
    }

    // Update external UI HUD if bound
    if (this.onDepthChangeCallback) {
      this.onDepthChangeCallback(this.currentDepth, this.scrollProgress);
    }
  }

  setupEventListeners() {
    window.addEventListener('mousemove', (e) => {
      this.mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      this.mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
    });

    window.addEventListener('resize', () => {
      if (!this.renderer || !this.camera) return;
      const width = this.canvas.clientWidth || window.innerWidth;
      const height = this.canvas.clientHeight || window.innerHeight;
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height, false);
      this.renderer.setPixelRatio(this.quality.dpr);
    });
  }

  setupVisibilityObserver() {
    // 1. Tab visibility (Playbook §7.2)
    document.addEventListener('visibilitychange', () => {
      this.isPaused = document.hidden;
    });

    // 2. IntersectionObserver (Pause when canvas scrolled out of view)
    if ('IntersectionObserver' in window) {
      this.observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          this.isPaused = !entry.isIntersecting;
        });
      }, { threshold: 0.05 });
      this.observer.observe(this.canvas);
    }
  }

  animate() {
    this.animId = requestAnimationFrame(() => this.animate());

    if (this.isPaused) return;

    this.quality.update();

    const delta = this.clock ? this.clock.getDelta() : 0.016;
    const elapsed = this.clock ? this.clock.getElapsedTime() : 0;

    // 1. Smooth Camera Lerp along depth path
    this.cameraCurrentY += (this.cameraTargetY - this.cameraCurrentY) * 0.08;
    this.parallax.x += (this.mouse.x * 0.4 - this.parallax.x) * 0.05;
    this.parallax.y += (this.mouse.y * 0.2 - this.parallax.y) * 0.05;

    this.camera.position.x = this.parallax.x;
    this.camera.position.y = this.cameraCurrentY + this.parallax.y;
    this.camera.lookAt(0, this.cameraCurrentY - 0.2, 0);

    // 2. Animate Ocean Surface Waves
    if (this.surfaceMesh && this.initialSurfacePositions) {
      const pos = this.surfaceMesh.geometry.attributes.position;
      const init = this.initialSurfacePositions;
      for (let i = 0; i < pos.count; i++) {
        const u = init.getX(i);
        const w = init.getZ(i);
        const wave = Math.sin(u * 1.5 + elapsed * 1.8) * 0.06 + Math.cos(w * 1.2 + elapsed * 1.4) * 0.05;
        pos.setY(i, wave);
      }
      pos.needsUpdate = true;
    }

    // 3. Float Argo Probe animation & pulse
    if (this.argoFloatGroup) {
      this.argoFloatGroup.rotation.y += 0.008;
      this.argoFloatGroup.position.x = 1.4 + Math.sin(elapsed * 0.6) * 0.15;
      if (this.floatPulseRing) {
        const scale = 1.0 + (Math.sin(elapsed * 3.0) + 1.0) * 0.4;
        this.floatPulseRing.scale.set(scale, scale, 1);
      }
    }

    // 4. Subtle strata slow rotation
    if (this.strataGroup) {
      this.strataGroup.rotation.y = elapsed * 0.03;
    }

    // 5. Plankton particles buoyant upward drift
    if (this.particles) {
      const pos = this.particles.geometry.attributes.position;
      for (let i = 0; i < pos.count; i++) {
        let y = pos.getY(i) + delta * 0.08;
        if (y > 1.2) y = -5.8;
        pos.setY(i, y);
      }
      pos.needsUpdate = true;
    }

    this.renderer.render(this.scene, this.camera);
  }

  renderFallback() {
    const ctx = this.canvas.getContext('2d');
    if (!ctx) return;
    const w = this.canvas.width = this.canvas.clientWidth || 800;
    const h = this.canvas.height = this.canvas.clientHeight || 500;

    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, '#142b44');
    grad.addColorStop(0.3, '#0d1726');
    grad.addColorStop(1, '#060b14');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    ctx.fillStyle = '#2dd4bf';
    ctx.font = '14px monospace';
    ctx.fillText('AQUASPHERE // SUBSURFACE RECONSTRUCTION ENGINE', 24, 40);
    ctx.fillStyle = '#9fb0c8';
    ctx.fillText('WebGL hardware acceleration disabled. Showing static bathymetric view.', 24, 65);
  }

  destroy() {
    if (this.animId) cancelAnimationFrame(this.animId);
    if (this.observer) this.observer.disconnect();
    if (this.renderer) {
      this.renderer.dispose();
      this.renderer.forceContextLoss();
    }
  }
}
