/**
 * AquaSphere 3D Ocean Intelligence Simulation
 * Built on Three.js (r128)
 * Features:
 * - Real-time trochoidal/sinusoidal surface wave shader
 * - Dynamic volumetric depth strata with amber thermocline highlight (50-150m)
 * - 1,400 bioluminescent marine snow particles
 * - Telemetry satellite orbital track
 * - Bobbing autonomous Argo profiling float
 * - Pointer parallax and programmatic depth descent
 */

export class OceanScene {
  constructor(canvasId = 'gl') {
    this.canvas = document.getElementById(canvasId);
    this.reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.state = {
      progress: 0,
      targetProgress: 0,
      paused: false,
      mouseX: 0,
      camX: 0
    };
    this.clock = null;
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.surfUniforms = null;
    this.particleUniforms = null;
    this.argoFloat = null;
    this.satellite = null;
    this.fogColor = null;
    this.cTop = null;
    this.cDeep = null;

    if (this.canvas && typeof window.THREE !== 'undefined') {
      this.init();
    } else {
      document.body.classList.add('nogl');
      console.warn('Three.js or canvas not available, using fallback gradient');
    }
  }

  // Depth in meters to scene units (stretched above 300m for thermocline fidelity)
  depthToY(d) {
    return -(d <= 300 ? d * 0.06 : 18 + (d - 300) * 0.0229);
  }

  init() {
    try {
      const THREE = window.THREE;
      const width = window.innerWidth;
      const height = window.innerHeight;

      // 1. Renderer
      this.renderer = new THREE.WebGLRenderer({
        canvas: this.canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance'
      });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      this.renderer.setSize(width, height);

      // 2. Scene & Camera
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 250);
      this.cTop = new THREE.Color('#1a538c');
      this.cDeep = new THREE.Color('#020611');
      this.fogColor = new THREE.Color();
      this.scene.fog = new THREE.FogExp2(0x1a538c, 0.028);

      // 3. Dynamic Wave Surface (90x90 Plane)
      this.surfUniforms = { t: { value: 0 } };
      const surfGeom = new THREE.PlaneGeometry(100, 100, 128, 128);
      const surfMat = new THREE.ShaderMaterial({
        uniforms: this.surfUniforms,
        transparent: true,
        side: THREE.DoubleSide,
        vertexShader: `
          uniform float t;
          varying float vH;
          varying vec2 vUv;
          void main() {
            vUv = uv;
            vec3 p = position;
            float w = sin(p.x * 0.35 + t * 1.1) * 0.28
                    + sin(p.y * 0.45 + t * 1.4) * 0.22
                    + sin((p.x + p.y) * 0.7 + t * 0.8) * 0.12;
            p.z += w;
            vH = w;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
          }
        `,
        fragmentShader: `
          varying float vH;
          varying vec2 vUv;
          void main() {
            vec3 deepBlue = vec3(0.04, 0.20, 0.38);
            vec3 shallowCyan = vec3(0.0, 0.85, 0.95);
            vec3 foamWhite = vec3(0.85, 0.98, 1.0);
            
            float hFactor = smoothstep(-0.35, 0.45, vH);
            vec3 col = mix(deepBlue, shallowCyan, hFactor);
            
            float crest = pow(smoothstep(0.25, 0.5, vH), 2.5);
            col = mix(col, foamWhite, crest * 0.85);
            
            gl_FragColor = vec4(col, 0.90);
          }
        `
      });
      const surfMesh = new THREE.Mesh(surfGeom, surfMat);
      surfMesh.rotation.x = -Math.PI / 2;
      this.scene.add(surfMesh);

      // 4. Volumetric Depth Strata (with glowing amber thermocline at 50-150m)
      const strataDepths = [50, 100, 150, 200, 300, 500, 700, 1000];
      strataDepths.forEach((d, i) => {
        const isThermocline = d >= 50 && d <= 150;
        const stratumColor = isThermocline ? 0xf59e0b : new THREE.Color().setHSL(0.56, 0.75, 0.55 - i * 0.05);

        // Translucent plane
        const planeMat = new THREE.MeshBasicMaterial({
          color: stratumColor,
          transparent: true,
          opacity: isThermocline ? 0.14 : 0.06,
          side: THREE.DoubleSide,
          depthWrite: false
        });
        const plane = new THREE.Mesh(new THREE.PlaneGeometry(75, 75), planeMat);
        plane.rotation.x = -Math.PI / 2;
        plane.position.y = this.depthToY(d);
        this.scene.add(plane);

        // Faint holographic grid helper
        const grid = new THREE.GridHelper(75, 30, isThermocline ? 0xf59e0b : 0x2dd4bf, 0x1e3a8a);
        grid.material.transparent = true;
        grid.material.opacity = isThermocline ? 0.15 : 0.07;
        grid.position.y = this.depthToY(d);
        this.scene.add(grid);
      });

      // 5. Bioluminescent Marine Snow Particles (1,400 points)
      const numParticles = width < 768 ? 700 : 1400;
      const posArray = new Float32Array(numParticles * 3);
      const speedArray = new Float32Array(numParticles);

      for (let i = 0; i < numParticles; i++) {
        posArray[i * 3] = (Math.random() - 0.5) * 46;
        posArray[i * 3 + 1] = -Math.random() * 40;
        posArray[i * 3 + 2] = (Math.random() - 0.5) * 36 - 4;
        speedArray[i] = Math.random();
      }

      const particleGeom = new THREE.BufferGeometry();
      particleGeom.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
      particleGeom.setAttribute('s', new THREE.BufferAttribute(speedArray, 1));

      this.particleUniforms = { t: { value: 0 } };
      const particleMat = new THREE.ShaderMaterial({
        uniforms: this.particleUniforms,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        vertexShader: `
          uniform float t;
          attribute float s;
          varying float vAlpha;
          void main() {
            vec3 p = position;
            p.y = mod(p.y + t * (0.16 + s * 0.32) + 42.0, 42.0) - 40.0;
            p.x += sin(t * 0.35 + s * 22.0) * 0.45;
            vec4 mv = modelViewMatrix * vec4(p, 1.0);
            gl_PointSize = (2.2 + s * 3.2) * (32.0 / -mv.z);
            vAlpha = 0.28 + s * 0.55;
            gl_Position = projectionMatrix * mv;
          }
        `,
        fragmentShader: `
          varying float vAlpha;
          void main() {
            float dist = length(gl_PointCoord - 0.5);
            if (dist > 0.5) discard;
            vec3 cyanSnow = vec3(0.5, 0.95, 0.95);
            gl_FragColor = vec4(cyanSnow, vAlpha * (1.0 - dist * 2.0));
          }
        `
      });

      this.scene.add(new THREE.Points(particleGeom, particleMat));

      // 6. Orbiting Space Telemetry Satellite Ring
      const orbitRing = new THREE.Mesh(
        new THREE.TorusGeometry(12, 0.025, 6, 128),
        new THREE.MeshBasicMaterial({ color: 0x2dd4bf, transparent: true, opacity: 0.45 })
      );
      orbitRing.rotation.x = Math.PI / 2.3;
      orbitRing.position.set(0, 7.5, -4);
      this.scene.add(orbitRing);

      this.satellite = new THREE.Mesh(
        new THREE.BoxGeometry(0.55, 0.28, 0.28),
        new THREE.MeshBasicMaterial({ color: 0xeaf2ff })
      );
      orbitRing.add(this.satellite);

      // 7. Bobbing Autonomous Argo Profiling Float (at ~500m depth)
      this.argoFloat = new THREE.Group();
      // Hull
      const hull = new THREE.Mesh(
        new THREE.CylinderGeometry(0.14, 0.14, 1.5, 16),
        new THREE.MeshBasicMaterial({ color: 0xeaf2ff })
      );
      this.argoFloat.add(hull);
      // Sensor cap
      const cap = new THREE.Mesh(
        new THREE.SphereGeometry(0.19, 14, 14),
        new THREE.MeshBasicMaterial({ color: 0x2dd4bf })
      );
      cap.position.y = 0.85;
      this.argoFloat.add(cap);
      // Satellite antenna
      const ant = new THREE.Mesh(
        new THREE.CylinderGeometry(0.015, 0.015, 1.1, 8),
        new THREE.MeshBasicMaterial({ color: 0x9fb0c8 })
      );
      ant.position.y = 1.45;
      this.argoFloat.add(ant);

      this.argoFloat.position.set(3.5, this.depthToY(500), -3);
      this.scene.add(this.argoFloat);

      // 8. Event Listeners
      this.bindEvents();

      // 9. Animation Loop
      this.clock = new THREE.Clock();
      this.animate();
    } catch (err) {
      console.error('Three.js initialization error:', err);
      document.body.classList.add('nogl');
    }
  }

  bindEvents() {
    if (!this.reduceMotion) {
      window.addEventListener('pointermove', (e) => {
        this.state.mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
      });
    }

    window.addEventListener('resize', () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      this.renderer.setSize(width, height);
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
    });

    const pauseBtn = document.getElementById('pause');
    if (pauseBtn) {
      pauseBtn.addEventListener('click', () => {
        this.state.paused = !this.state.paused;
        pauseBtn.setAttribute('aria-pressed', this.state.paused);
        pauseBtn.textContent = this.state.paused ? 'Resume motion' : 'Pause motion';
      });
    }
  }

  setDepthProgress(progress) {
    this.state.targetProgress = Math.max(0, Math.min(1, progress));
  }

  animate() {
    requestAnimationFrame(() => this.animate());

    const dt = Math.min(this.clock.getDelta(), 0.05);
    let t = this.surfUniforms.t.value;

    if (!this.state.paused) {
      t += dt * (this.reduceMotion ? 0.2 : 1.0);
      this.surfUniforms.t.value = t;
      this.particleUniforms.t.value = t;
    }

    // Smooth scroll / depth progress easing
    this.state.progress += (this.state.targetProgress - this.state.progress) * (this.reduceMotion ? 1.0 : 0.06);
    this.state.camX += (this.state.mouseX - this.state.camX) * 0.05;

    const p = this.state.progress;

    // Camera positioning
    this.camera.position.set(this.state.camX * 1.5, 3.2 - p * 38.0, 16.5 - p * 6.5);
    this.camera.lookAt(0, this.camera.position.y - 1.4, 0);

    // Fog & clear color depth gradient
    this.fogColor.copy(this.cTop).lerp(this.cDeep, Math.min(1, p * 1.6));
    this.scene.fog.color.copy(this.fogColor);
    this.renderer.setClearColor(this.fogColor, 1.0);
    this.scene.fog.density = 0.028 + 0.022 * p;

    // Satellite rotation
    const satAngle = t * 0.35;
    this.satellite.position.set(Math.cos(satAngle) * 12, Math.sin(satAngle) * 12, 0);

    // Argo float bobbing
    this.argoFloat.position.y = this.depthToY(500) + Math.sin(t * 0.45) * 3.5;

    // Update fixed right-hand depth gauge
    const depthMeters = Math.round(p * 1000);
    const gfill = document.getElementById('gfill');
    const gtxt = document.getElementById('gtxt');
    if (gfill) gfill.style.height = `${p * 100}%`;
    if (gtxt) {
      gtxt.textContent = `${depthMeters} m`;
      gtxt.style.top = `${p * 100}%`;
    }

    this.renderer.render(this.scene, this.camera);
  }
}
