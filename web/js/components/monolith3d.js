/**
 * AquaSphere 3D Architectural Monolith Experience
 * Built with Three.js — Combines Sandstone Blue and Concrete Candy materiality
 */

export class Monolith3D {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.options = {
      enableExplode: true,
      enableScroll: true,
      ...options,
    };

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.monolithGroup = null;
    this.strataLayers = [];
    this.rings = [];
    this.particles = null;
    this.probeNodes = [];

    // Interaction states
    this.isHovered = false;
    this.isDragging = false;
    this.previousMousePosition = { x: 0, y: 0 };
    this.targetRotation = { x: 0.25, y: -0.45 };
    this.currentRotation = { x: 0.25, y: -0.45 };
    this.mouseParallax = { x: 0, y: 0 };
    this.explodeFactor = 0.0;
    this.targetExplodeFactor = 0.0;
    this.pulsePhase = 0;
    this.activeMode = 'assembled'; // 'assembled' | 'exploded' | 'sonar' | 'core'

    this.animationFrameId = null;
    this.isVisible = true;

    this.init();
  }

  init() {
    if (!window.THREE) {
      console.warn('Three.js not loaded. Falling back to 2D canvas.');
      this.renderFallback();
      return;
    }

    const THREE = window.THREE;

    // 1. Scene
    this.scene = new THREE.Scene();

    // 2. Camera
    const aspect = this.canvas.clientWidth / (this.canvas.clientHeight || 1);
    this.camera = new THREE.PerspectiveCamera(40, aspect, 0.1, 100);
    this.camera.position.set(0, 0.4, 6.2);

    // 3. Renderer
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });
    this.renderer.setSize(this.canvas.clientWidth, this.canvas.clientHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.15;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // 4. Lighting Setup (Studio Architecture Lighting)
    this.setupLighting(THREE);

    // 5. Build Monolith Geometry & Materials
    this.buildMonolith(THREE);

    // 6. Event Listeners
    this.setupEvents();

    // 7. Start Loop
    this.animate = this.animate.bind(this);
    this.animate();
  }

  setupLighting(THREE) {
    // Ambient light - Midnight Navy bounce
    const ambientLight = new THREE.AmbientLight(0x1f2937, 1.2);
    this.scene.add(ambientLight);

    // Key directional light - warm studio sunlight
    const keyLight = new THREE.DirectionalLight(0xfff5ea, 2.2);
    keyLight.position.set(4, 7, 5);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.width = 1024;
    keyLight.shadow.mapSize.height = 1024;
    keyLight.shadow.camera.near = 0.5;
    keyLight.shadow.camera.far = 20;
    keyLight.shadow.bias = -0.001;
    this.scene.add(keyLight);

    // Rim light - Electric Cobalt Blue
    const rimLight = new THREE.DirectionalLight(0x3882f6, 2.6);
    rimLight.position.set(-6, -2, -5);
    this.scene.add(rimLight);

    // Warm sandstone bounce light
    const bounceLight = new THREE.DirectionalLight(0xd9c3a5, 0.9);
    bounceLight.position.set(3, -4, 2);
    this.scene.add(bounceLight);

    // Focal point light for oceanic crystal core
    this.corePointLight = new THREE.PointLight(0x3882f6, 2.5, 4);
    this.corePointLight.position.set(0, 0, 0);
    this.scene.add(this.corePointLight);

    // Precision beacon light - Chartreuse ping
    this.beaconLight = new THREE.PointLight(0x86ff00, 1.2, 3);
    this.beaconLight.position.set(1.4, 0.6, 1.2);
    this.scene.add(this.beaconLight);
  }

  buildMonolith(THREE) {
    this.monolithGroup = new THREE.Group();

    // Materials Palette matching specification
    const concreteMat = new THREE.MeshStandardMaterial({
      color: 0xd9d0cb,
      roughness: 0.88,
      metalness: 0.08,
      bumpScale: 0.05,
    });

    const sandstoneMat = new THREE.MeshStandardMaterial({
      color: 0xd9c3a5,
      roughness: 0.72,
      metalness: 0.05,
    });

    const earthBrownMat = new THREE.MeshStandardMaterial({
      color: 0xa67c52,
      roughness: 0.82,
      metalness: 0.12,
    });

    const charcoalMat = new THREE.MeshStandardMaterial({
      color: 0x2e2e2e,
      roughness: 0.5,
      metalness: 0.35,
    });

    const cobaltOceanMat = new THREE.MeshPhysicalMaterial({
      color: 0x1c71e4,
      emissive: 0x002e6a,
      emissiveIntensity: 0.25,
      roughness: 0.18,
      metalness: 0.1,
      transmission: 0.65,
      thickness: 1.2,
      transparent: true,
      opacity: 0.85,
    });

    const wireframeMat = new THREE.MeshBasicMaterial({
      color: 0x3882f6,
      wireframe: true,
      transparent: true,
      opacity: 0.25,
    });

    // Layer 1: Bottom Benthic Concrete Slabs (Deep Seafloor)
    const basePlateGeo = new THREE.BoxGeometry(2.4, 0.22, 2.4);
    const basePlate = new THREE.Mesh(basePlateGeo, concreteMat);
    basePlate.position.y = -1.15;
    basePlate.castShadow = true;
    basePlate.receiveShadow = true;
    basePlate.userData = { baseY: -1.15, explodeOffset: -0.6 };
    this.monolithGroup.add(basePlate);
    this.strataLayers.push(basePlate);

    // Layer 2: Deep Earth Brown Sub-Benthic Layer
    const earthLayerGeo = new THREE.BoxGeometry(2.2, 0.3, 2.2);
    const earthLayer = new THREE.Mesh(earthLayerGeo, earthBrownMat);
    earthLayer.position.y = -0.85;
    earthLayer.castShadow = true;
    earthLayer.receiveShadow = true;
    earthLayer.userData = { baseY: -0.85, explodeOffset: -0.35 };
    this.monolithGroup.add(earthLayer);
    this.strataLayers.push(earthLayer);

    // Layer 3: Warm Sandstone Bathymetric Strata
    const sandstoneLayerGeo = new THREE.BoxGeometry(2.05, 0.35, 2.05);
    const sandstoneLayer = new THREE.Mesh(sandstoneLayerGeo, sandstoneMat);
    sandstoneLayer.position.y = -0.5;
    sandstoneLayer.castShadow = true;
    sandstoneLayer.receiveShadow = true;
    sandstoneLayer.userData = { baseY: -0.5, explodeOffset: -0.15 };
    this.monolithGroup.add(sandstoneLayer);
    this.strataLayers.push(sandstoneLayer);

    // Layer 4: Translucent Electric Cobalt Oceanic Column (0–1000m Water Mass)
    const oceanCoreGeo = new THREE.BoxGeometry(1.9, 0.95, 1.9);
    const oceanCore = new THREE.Mesh(oceanCoreGeo, cobaltOceanMat);
    oceanCore.position.y = 0.2;
    oceanCore.castShadow = true;
    oceanCore.userData = { baseY: 0.2, explodeOffset: 0.1 };
    this.monolithGroup.add(oceanCore);
    this.strataLayers.push(oceanCore);

    // Wireframe ghost overlay on ocean core
    const wireCore = new THREE.Mesh(oceanCoreGeo, wireframeMat);
    wireCore.position.y = 0.2;
    wireCore.scale.set(1.002, 1.002, 1.002);
    wireCore.userData = { baseY: 0.2, explodeOffset: 0.1 };
    this.monolithGroup.add(wireCore);
    this.strataLayers.push(wireCore);

    // Layer 5: Top Epipelagic Cap (Sculpted Surface Slab with Chamfered Corners)
    const topCapGeo = new THREE.BoxGeometry(2.1, 0.18, 2.1);
    const topCap = new THREE.Mesh(topCapGeo, concreteMat);
    topCap.position.y = 0.85;
    topCap.castShadow = true;
    topCap.receiveShadow = true;
    topCap.userData = { baseY: 0.85, explodeOffset: 0.45 };
    this.monolithGroup.add(topCap);
    this.strataLayers.push(topCap);

    // Precision Top Charcoal Reticle Collar
    const reticleGeo = new THREE.BoxGeometry(1.4, 0.08, 1.4);
    const reticle = new THREE.Mesh(reticleGeo, charcoalMat);
    reticle.position.y = 1.0;
    reticle.castShadow = true;
    reticle.userData = { baseY: 1.0, explodeOffset: 0.65 };
    this.monolithGroup.add(reticle);
    this.strataLayers.push(reticle);

    // Floating Bathymetric Contour Rings (Sonar depth isobaths)
    const ringGeo1 = new THREE.TorusGeometry(1.65, 0.015, 16, 64);
    const ringMat1 = new THREE.MeshBasicMaterial({ color: 0x3882f6, transparent: true, opacity: 0.75 });
    const ring1 = new THREE.Mesh(ringGeo1, ringMat1);
    ring1.rotation.x = Math.PI / 2;
    ring1.position.y = 0.2;
    this.monolithGroup.add(ring1);
    this.rings.push({ mesh: ring1, rotSpeed: 0.006, baseY: 0.2 });

    const ringGeo2 = new THREE.TorusGeometry(1.85, 0.012, 16, 64);
    const ringMat2 = new THREE.MeshBasicMaterial({ color: 0x86ff00, transparent: true, opacity: 0.85 });
    const ring2 = new THREE.Mesh(ringGeo2, ringMat2);
    ring2.rotation.x = Math.PI / 2 + 0.1;
    ring2.position.y = -0.3;
    this.monolithGroup.add(ring2);
    this.rings.push({ mesh: ring2, rotSpeed: -0.008, baseY: -0.3 });

    const ringGeo3 = new THREE.TorusGeometry(2.05, 0.01, 16, 64);
    const ringMat3 = new THREE.MeshBasicMaterial({ color: 0xff4d6d, transparent: true, opacity: 0.6 });
    const ring3 = new THREE.Mesh(ringGeo3, ringMat3);
    ring3.rotation.x = Math.PI / 2 - 0.08;
    ring3.position.y = -0.7;
    this.monolithGroup.add(ring3);
    this.rings.push({ mesh: ring3, rotSpeed: 0.004, baseY: -0.7 });

    // Internal Buoyant Particulate Field (Oceanic hydrographic particles)
    const particleCount = 120;
    const particleGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {
      positions[i * 3 + 0] = (Math.random() - 0.5) * 1.6;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 0.8 + 0.2;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 1.6;

      const rnd = Math.random();
      if (rnd < 0.6) {
        colors[i * 3 + 0] = 0.22;
        colors[i * 3 + 1] = 0.51;
        colors[i * 3 + 2] = 0.96; // Cobalt
      } else if (rnd < 0.85) {
        colors[i * 3 + 0] = 0.85;
        colors[i * 3 + 1] = 0.76;
        colors[i * 3 + 2] = 0.65; // Sandstone
      } else {
        colors[i * 3 + 0] = 0.52;
        colors[i * 3 + 1] = 1.0;
        colors[i * 3 + 2] = 0.0; // Chartreuse
      }
    }

    particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    particleGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const particleMat = new THREE.PointsMaterial({
      size: 0.045,
      vertexColors: true,
      transparent: true,
      opacity: 0.9,
    });

    this.particles = new THREE.Points(particleGeo, particleMat);
    this.monolithGroup.add(this.particles);

    // Argo Float Sensor Probes (Miniature active beacons)
    this.addProbeNode(THREE, 1.4, 0.45, 0.8, 0x86ff00, 'ARGO-4902148');
    this.addProbeNode(THREE, -1.3, -0.25, -1.1, 0xff4d6d, 'ARGO-2903381');

    this.scene.add(this.monolithGroup);
  }

  addProbeNode(THREE, x, y, z, colorHex, label) {
    const probeGroup = new THREE.Group();
    probeGroup.position.set(x, y, z);

    // Mini cylinder body
    const bodyGeo = new THREE.CylinderGeometry(0.04, 0.04, 0.16, 12);
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x2e2e2e, metalness: 0.8, roughness: 0.2 });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    probeGroup.add(body);

    // Glowing tip beacon
    const tipGeo = new THREE.SphereGeometry(0.045, 12, 12);
    const tipMat = new THREE.MeshBasicMaterial({ color: colorHex });
    const tip = new THREE.Mesh(tipGeo, tipMat);
    tip.position.y = 0.09;
    probeGroup.add(tip);

    probeGroup.userData = {
      basePos: new THREE.Vector3(x, y, z),
      phase: Math.random() * Math.PI * 2,
      label,
    };

    this.monolithGroup.add(probeGroup);
    this.probeNodes.push(probeGroup);
  }

  setupEvents() {
    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    window.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const inView =
        e.clientX >= rect.left &&
        e.clientX <= rect.right &&
        e.clientY >= rect.top &&
        e.clientY <= rect.bottom;

      this.isHovered = inView;

      if (this.isDragging) {
        const deltaX = e.clientX - this.previousMousePosition.x;
        const deltaY = e.clientY - this.previousMousePosition.y;

        this.targetRotation.y += deltaX * 0.008;
        this.targetRotation.x += deltaY * 0.008;

        this.targetRotation.x = Math.max(-0.8, Math.min(0.8, this.targetRotation.x));
        this.previousMousePosition = { x: e.clientX, y: e.clientY };
      } else if (inView) {
        const normX = (e.clientX - (rect.left + rect.width / 2)) / (rect.width / 2);
        const normY = (e.clientY - (rect.top + rect.height / 2)) / (rect.height / 2);

        this.mouseParallax.x = normX * 0.25;
        this.mouseParallax.y = normY * 0.2;
      }
    });

    this.canvas.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        this.isDragging = true;
        this.previousMousePosition = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    }, { passive: true });

    window.addEventListener('touchend', () => {
      this.isDragging = false;
    });

    window.addEventListener('touchmove', (e) => {
      if (this.isDragging && e.touches.length === 1) {
        const deltaX = e.touches[0].clientX - this.previousMousePosition.x;
        const deltaY = e.touches[0].clientY - this.previousMousePosition.y;

        this.targetRotation.y += deltaX * 0.01;
        this.targetRotation.x += deltaY * 0.01;
        this.targetRotation.x = Math.max(-0.8, Math.min(0.8, this.targetRotation.x));

        this.previousMousePosition = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    }, { passive: true });

    window.addEventListener('scroll', () => {
      if (!this.options.enableScroll) return;
      const scrollY = window.scrollY || window.pageYOffset;
      const scrollMax = document.documentElement.scrollHeight - window.innerHeight;
      const progress = scrollMax > 0 ? Math.min(1, Math.max(0, scrollY / 1200)) : 0;

      this.camera.position.z = 6.2 - progress * 1.4;
      this.camera.position.y = 0.4 + progress * 0.6;
      this.targetRotation.y = -0.45 + progress * Math.PI * 0.65;
    }, { passive: true });

    window.addEventListener('resize', () => {
      this.handleResize();
    });

    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          this.isVisible = entry.isIntersecting;
        });
      }, { threshold: 0.1 });
      observer.observe(this.canvas);
    }
  }

  handleResize() {
    if (!this.renderer || !this.camera) return;
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (width === 0 || height === 0) return;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  setMode(mode) {
    this.activeMode = mode;
    switch (mode) {
      case 'exploded':
        this.targetExplodeFactor = 1.0;
        this.targetRotation.x = 0.35;
        this.targetRotation.y = -0.2;
        break;
      case 'core':
        this.targetExplodeFactor = 0.25;
        this.targetRotation.x = 0.1;
        this.targetRotation.y = Math.PI * 0.25;
        break;
      case 'sonar':
        this.targetExplodeFactor = 0.0;
        this.pulsePhase = 0;
        break;
      case 'assembled':
      default:
        this.targetExplodeFactor = 0.0;
        this.targetRotation.x = 0.25;
        this.targetRotation.y = -0.45;
        break;
    }
  }

  triggerSonarWave() {
    this.pulsePhase = 0;
    this.activeMode = 'sonar';
  }

  animate() {
    this.animationFrameId = requestAnimationFrame(this.animate);

    if (!this.isVisible) return;

    const lerpSpeed = 0.06;
    const targetY = this.targetRotation.y + (this.isHovered ? this.mouseParallax.x : 0);
    const targetX = this.targetRotation.x + (this.isHovered ? this.mouseParallax.y : 0);

    this.currentRotation.y += (targetY - this.currentRotation.y) * lerpSpeed;
    this.currentRotation.x += (targetX - this.currentRotation.x) * lerpSpeed;

    if (!this.isDragging && !this.isHovered) {
      this.targetRotation.y += 0.0018;
    }

    if (this.monolithGroup) {
      this.monolithGroup.rotation.y = this.currentRotation.y;
      this.monolithGroup.rotation.x = this.currentRotation.x;

      this.explodeFactor += (this.targetExplodeFactor - this.explodeFactor) * 0.08;
      this.strataLayers.forEach((layer) => {
        if (layer.userData && layer.userData.baseY !== undefined) {
          layer.position.y = layer.userData.baseY + layer.userData.explodeOffset * this.explodeFactor;
        }
      });

      this.rings.forEach((r, idx) => {
        r.mesh.rotation.z += r.rotSpeed;
        r.mesh.position.y = r.baseY + Math.sin(Date.now() * 0.002 + idx) * 0.04;
      });

      if (this.particles) {
        const positions = this.particles.geometry.attributes.position.array;
        for (let i = 0; i < positions.length / 3; i++) {
          positions[i * 3 + 1] += Math.sin(Date.now() * 0.0015 + i) * 0.0012;
        }
        this.particles.geometry.attributes.position.needsUpdate = true;
      }

      this.probeNodes.forEach((p) => {
        p.userData.phase += 0.03;
        p.position.y = p.userData.basePos.y + Math.sin(p.userData.phase) * 0.08;
      });

      if (this.corePointLight) {
        this.corePointLight.intensity = 2.0 + Math.sin(Date.now() * 0.003) * 0.6;
      }

      if (this.activeMode === 'sonar') {
        this.pulsePhase += 0.05;
        this.rings.forEach((r, i) => {
          const s = 1.0 + Math.sin(this.pulsePhase - i * 0.5) * 0.15;
          r.mesh.scale.set(s, s, s);
        });
        if (this.pulsePhase > Math.PI * 4) {
          this.activeMode = 'assembled';
          this.rings.forEach((r) => r.mesh.scale.set(1, 1, 1));
        }
      }
    }

    this.renderer.render(this.scene, this.camera);
  }

  renderFallback() {
    const ctx = this.canvas.getContext('2d');
    if (!ctx) return;
    const w = (this.canvas.width = this.canvas.clientWidth);
    const h = (this.canvas.height = this.canvas.clientHeight);

    ctx.fillStyle = '#1f2937';
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = '#3882f6';
    ctx.lineWidth = 2;
    ctx.strokeRect(w * 0.25, h * 0.25, w * 0.5, h * 0.5);

    ctx.fillStyle = '#ebedf4';
    ctx.font = '14px Space Mono, monospace';
    ctx.textAlign = 'center';
    ctx.fillText('AQUASPHERE 3D MONOLITH [BATHYMETRIC STRATA]', w / 2, h / 2);
  }

  destroy() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    if (this.renderer) {
      this.renderer.dispose();
    }
  }
}
