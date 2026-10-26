/**
 * AquaSphere Cinematic 3D WebGL Engine
 * Built with Three.js & GSAP — Architectural Bathymetric Monolith
 * Combines Sandstone Blue & Concrete Candy Materiality
 */

export class Monolith3D {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.options = {
      enableExplode: true,
      enableScroll: true,
      enableRaycasting: true,
      ...options,
    };

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.monolithGroup = null;
    this.satelliteGroup = null;
    this.strataLayers = [];
    this.satellites = [];
    this.rings = [];
    this.particles = null;
    this.probeNodes = [];
    this.slicePlane = null;

    // Raycaster for interactive hover & click
    this.raycaster = null;
    this.mouse = { x: -1000, y: -1000 };
    this.hoveredObject = null;
    this.onHoverCallback = null;
    this.onClickCallback = null;

    // Camera & Transform targets
    this.isDragging = false;
    this.previousMousePosition = { x: 0, y: 0 };
    this.baseRotation = { x: 0.22, y: -0.42 };
    this.currentRotation = { x: 0.22, y: -0.42 };
    this.targetRotation = { x: 0.22, y: -0.42 };
    this.mouseParallax = { x: 0, y: 0 };
    this.targetCameraPos = { x: 0, y: 0.4, z: 6.2 };
    this.currentCameraPos = { x: 0, y: 0.4, z: 6.2 };

    // Physics & Animation factors
    this.explodeFactor = 0.0;
    this.targetExplodeFactor = 0.0;
    this.sliceDepth = 100; // 0–1000m
    this.targetSliceY = 0.35;
    this.currentSliceY = 0.35;
    this.pulsePhase = 0;
    this.activeMode = 'assembled'; // 'assembled' | 'exploded' | 'core' | 'sonar' | 'wireframe'

    this.clock = null;
    this.animationFrameId = null;
    this.isVisible = true;

    this.init();
  }

  init() {
    if (!window.THREE) {
      console.warn('Three.js not loaded. Falling back to canvas.');
      this.renderFallback();
      return;
    }

    const THREE = window.THREE;
    this.clock = new THREE.Clock();
    this.raycaster = new THREE.Raycaster();

    // 1. Scene
    this.scene = new THREE.Scene();

    // 2. Camera
    const width = this.canvas.clientWidth || window.innerWidth;
    const height = this.canvas.clientHeight || window.innerHeight;
    const aspect = width / height;
    this.camera = new THREE.PerspectiveCamera(40, aspect, 0.1, 100);
    this.camera.position.set(0, 3.5, 9.5); // Initial camera pose for cinematic entrance

    // 3. Renderer
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.25;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // 4. Studio Lighting
    this.setupLighting(THREE);

    // 5. Build 3D Architectural Monolith & Satellites
    this.buildMonolith(THREE);
    this.buildSatellites(THREE);
    this.buildDepthSlicePlane(THREE);

    // 6. Event Handlers
    this.setupEvents(THREE);

    // 7. Start Animation Loop
    this.animate = this.animate.bind(this);
    this.animate();

    // 8. Play Opening Cinematic Camera Swoop
    this.playIntroAnimation();
  }

  setupLighting(THREE) {
    // Ambient light - Midnight Navy bounce
    const ambientLight = new THREE.AmbientLight(0x1f2937, 1.4);
    this.scene.add(ambientLight);

    // Key directional light - warm studio sunlight
    this.keyLight = new THREE.DirectionalLight(0xfff5ea, 2.6);
    this.keyLight.position.set(5, 8, 5);
    this.keyLight.castShadow = true;
    this.keyLight.shadow.mapSize.width = 1024;
    this.keyLight.shadow.mapSize.height = 1024;
    this.keyLight.shadow.camera.near = 0.5;
    this.keyLight.shadow.camera.far = 22;
    this.keyLight.shadow.bias = -0.0008;
    this.scene.add(this.keyLight);

    // Rim light - Electric Cobalt Blue
    const rimLight = new THREE.DirectionalLight(0x3882f6, 3.2);
    rimLight.position.set(-6, -2, -5);
    this.scene.add(rimLight);

    // Warm sandstone ground bounce light
    const bounceLight = new THREE.DirectionalLight(0xd9c3a5, 1.2);
    bounceLight.position.set(3, -5, 2);
    this.scene.add(bounceLight);

    // Volumetric Core Point Light
    this.corePointLight = new THREE.PointLight(0x3882f6, 3.0, 5.0);
    this.corePointLight.position.set(0, 0.1, 0);
    this.scene.add(this.corePointLight);

    // Precision Chartreuse Beacon Light
    this.beaconLight = new THREE.PointLight(0x86ff00, 1.6, 4.0);
    this.beaconLight.position.set(1.5, 0.6, 1.3);
    this.scene.add(this.beaconLight);
  }

  buildMonolith(THREE) {
    this.monolithGroup = new THREE.Group();

    // Materials Palette matching specification
    const concreteMat = new THREE.MeshStandardMaterial({
      color: 0xd9d0cb,
      roughness: 0.86,
      metalness: 0.08,
      bumpScale: 0.06,
    });

    const sandstoneMat = new THREE.MeshStandardMaterial({
      color: 0xd9c3a5,
      roughness: 0.70,
      metalness: 0.05,
    });

    const earthBrownMat = new THREE.MeshStandardMaterial({
      color: 0xa67c52,
      roughness: 0.82,
      metalness: 0.12,
    });

    const charcoalMat = new THREE.MeshStandardMaterial({
      color: 0x2e2e2e,
      roughness: 0.45,
      metalness: 0.35,
    });

    const cobaltOceanMat = new THREE.MeshPhysicalMaterial({
      color: 0x1c71e4,
      emissive: 0x002e6a,
      emissiveIntensity: 0.35,
      roughness: 0.15,
      metalness: 0.1,
      transmission: 0.72,
      thickness: 1.4,
      transparent: true,
      opacity: 0.88,
    });

    this.wireframeMat = new THREE.MeshBasicMaterial({
      color: 0x3882f6,
      wireframe: true,
      transparent: true,
      opacity: 0.3,
    });

    // Layer 1: Bottom Benthic Concrete Slab (Deep Seafloor)
    const basePlateGeo = new THREE.BoxGeometry(2.5, 0.26, 2.5);
    const basePlate = new THREE.Mesh(basePlateGeo, concreteMat);
    basePlate.position.y = -1.2;
    basePlate.castShadow = true;
    basePlate.receiveShadow = true;
    basePlate.userData = {
      name: 'Benthic Concrete Foundation',
      depthRange: '1000m+ Seafloor Bedrock',
      baseY: -1.2,
      explodeOffset: -0.75,
      lithology: 'Basaltic Crust / Calcareous Ooze',
    };
    this.monolithGroup.add(basePlate);
    this.strataLayers.push(basePlate);

    // Layer 2: Deep Earth Brown Sub-Benthic Strata
    const earthLayerGeo = new THREE.BoxGeometry(2.3, 0.32, 2.3);
    const earthLayer = new THREE.Mesh(earthLayerGeo, earthBrownMat);
    earthLayer.position.y = -0.88;
    earthLayer.castShadow = true;
    earthLayer.receiveShadow = true;
    earthLayer.userData = {
      name: 'Sub-Benthic Lithic Strata',
      depthRange: '700–1000m Bathyal Zone',
      baseY: -0.88,
      explodeOffset: -0.42,
      lithology: 'Terrigenous Clay Sediment',
    };
    this.monolithGroup.add(earthLayer);
    this.strataLayers.push(earthLayer);

    // Layer 3: Warm Sandstone Bathymetric Strata
    const sandstoneLayerGeo = new THREE.BoxGeometry(2.1, 0.38, 2.1);
    const sandstoneLayer = new THREE.Mesh(sandstoneLayerGeo, sandstoneMat);
    sandstoneLayer.position.y = -0.5;
    sandstoneLayer.castShadow = true;
    sandstoneLayer.receiveShadow = true;
    sandstoneLayer.userData = {
      name: 'Sedimentary Sandstone Strata',
      depthRange: '200–700m Mesopelagic Layer',
      baseY: -0.5,
      explodeOffset: -0.18,
      lithology: 'Siliceous Pelagic Sandstone',
    };
    this.monolithGroup.add(sandstoneLayer);
    this.strataLayers.push(sandstoneLayer);

    // Layer 4: Translucent Crystalline Cobalt Ocean Column (0–1000m Water Mass)
    const oceanCoreGeo = new THREE.BoxGeometry(1.95, 1.05, 1.95);
    const oceanCore = new THREE.Mesh(oceanCoreGeo, cobaltOceanMat);
    oceanCore.position.y = 0.25;
    oceanCore.castShadow = true;
    oceanCore.userData = {
      name: 'Crystalline Oceanic Core',
      depthRange: '0–200m Epipelagic Halocline',
      baseY: 0.25,
      explodeOffset: 0.15,
      lithology: 'Hydrographic Water Mass (SST 28.4°C / 34.2 PSU)',
    };
    this.monolithGroup.add(oceanCore);
    this.strataLayers.push(oceanCore);
    this.oceanCoreMesh = oceanCore;

    // Wireframe ghost overlay on ocean core
    const wireCore = new THREE.Mesh(oceanCoreGeo, this.wireframeMat);
    wireCore.position.y = 0.25;
    wireCore.scale.set(1.002, 1.002, 1.002);
    wireCore.userData = { baseY: 0.25, explodeOffset: 0.15 };
    this.monolithGroup.add(wireCore);
    this.strataLayers.push(wireCore);

    // Layer 5: Top Epipelagic Cast Concrete Cap
    const topCapGeo = new THREE.BoxGeometry(2.15, 0.2, 2.15);
    const topCap = new THREE.Mesh(topCapGeo, concreteMat);
    topCap.position.y = 0.92;
    topCap.castShadow = true;
    topCap.receiveShadow = true;
    topCap.userData = {
      name: 'Epipelagic Surface Slab',
      depthRange: '0–30m Surface Mixed Layer',
      baseY: 0.92,
      explodeOffset: 0.52,
      lithology: 'Upper Wind-Stirred Mixed Layer',
    };
    this.monolithGroup.add(topCap);
    this.strataLayers.push(topCap);

    // Precision Top Charcoal Reticle Collar
    const reticleGeo = new THREE.BoxGeometry(1.4, 0.09, 1.4);
    const reticle = new THREE.Mesh(reticleGeo, charcoalMat);
    reticle.position.y = 1.08;
    reticle.castShadow = true;
    reticle.userData = {
      name: 'Satellite Calibration Collar',
      depthRange: 'Altimetry Reference 0m',
      baseY: 1.08,
      explodeOffset: 0.78,
      lithology: 'Acoustic Registration Collar',
    };
    this.monolithGroup.add(reticle);
    this.strataLayers.push(reticle);

    // Floating Bathymetric Contour Rings (Rotating Sonar Isobaths)
    this.addContourRing(THREE, 1.7, 0.25, 0x3882f6, 0.006, 0.75); // 200m Cobalt
    this.addContourRing(THREE, 1.95, -0.3, 0x86ff00, -0.008, 0.85); // 500m Chartreuse
    this.addContourRing(THREE, 2.2, -0.75, 0xff4d6d, 0.005, 0.65); // 800m Punch Pink

    // Internal Buoyant Particulate Field (Planktonic & Optical Backscatter)
    this.buildParticles(THREE);

    // Argo Sensor Floats (Miniature active probes)
    this.addProbeNode(THREE, 1.45, 0.45, 0.85, 0x86ff00, 'ARGO-4902148');
    this.addProbeNode(THREE, -1.35, -0.25, -1.15, 0xff4d6d, 'ARGO-2903381');

    this.scene.add(this.monolithGroup);
  }

  addContourRing(THREE, radius, yPos, colorHex, rotSpeed, opacity) {
    const ringGeo = new THREE.TorusGeometry(radius, 0.014, 16, 64);
    const ringMat = new THREE.MeshBasicMaterial({ color: colorHex, transparent: true, opacity });
    const ringMesh = new THREE.Mesh(ringGeo, ringMat);
    ringMesh.rotation.x = Math.PI / 2;
    ringMesh.position.y = yPos;
    this.monolithGroup.add(ringMesh);
    this.rings.push({ mesh: ringMesh, rotSpeed, baseY: yPos, radius });
  }

  buildParticles(THREE) {
    const particleCount = 180;
    const particleGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {
      positions[i * 3 + 0] = (Math.random() - 0.5) * 1.8;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 0.95 + 0.25;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 1.8;

      const rnd = Math.random();
      if (rnd < 0.55) {
        colors[i * 3 + 0] = 0.22;
        colors[i * 3 + 1] = 0.51;
        colors[i * 3 + 2] = 0.96; // Electric Cobalt
      } else if (rnd < 0.82) {
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
      size: 0.048,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
    });

    this.particles = new THREE.Points(particleGeo, particleMat);
    this.monolithGroup.add(this.particles);
  }

  buildSatellites(THREE) {
    this.satelliteGroup = new THREE.Group();

    // 4 floating geometric architectural shards orbiting at varying z-depths
    const satConfigs = [
      { geo: new THREE.TetrahedronGeometry(0.24), color: 0xd9c3a5, pos: [2.5, 1.2, -1.2], speed: 0.8 },
      { geo: new THREE.OctahedronGeometry(0.28), color: 0x3882f6, pos: [-2.6, 0.4, 1.4], speed: 1.1 },
      { geo: new THREE.BoxGeometry(0.3, 0.3, 0.3), color: 0xd9d0cb, pos: [2.2, -1.1, 1.1], speed: 0.9 },
      { geo: new THREE.TetrahedronGeometry(0.22), color: 0x86ff00, pos: [-2.0, -0.9, -1.5], speed: 1.3 },
    ];

    satConfigs.forEach((cfg, idx) => {
      const mat = new THREE.MeshStandardMaterial({
        color: cfg.color,
        roughness: 0.6,
        metalness: 0.2,
      });
      const mesh = new THREE.Mesh(cfg.geo, mat);
      mesh.position.set(...cfg.pos);
      mesh.castShadow = true;
      this.satelliteGroup.add(mesh);

      this.satellites.push({
        mesh,
        basePos: new THREE.Vector3(...cfg.pos),
        speed: cfg.speed,
        phase: idx * 1.5,
      });
    });

    this.scene.add(this.satelliteGroup);
  }

  buildDepthSlicePlane(THREE) {
    // Glowing laser cutting slice plane that moves with depth slider
    const planeGeo = new THREE.PlaneGeometry(2.6, 2.6);
    const planeMat = new THREE.MeshBasicMaterial({
      color: 0x86ff00,
      transparent: true,
      opacity: 0.22,
      side: THREE.DoubleSide,
    });
    this.slicePlane = new THREE.Mesh(planeGeo, planeMat);
    this.slicePlane.rotation.x = Math.PI / 2;
    this.slicePlane.position.y = 0.35;
    this.slicePlane.visible = true;

    // Glowing border edges
    const edgesGeo = new THREE.EdgesGeometry(planeGeo);
    const edgesMat = new THREE.LineBasicMaterial({ color: 0x86ff00, linewidth: 2 });
    const wireframeBorder = new THREE.LineSegments(edgesGeo, edgesMat);
    this.slicePlane.add(wireframeBorder);

    this.monolithGroup.add(this.slicePlane);
  }

  addProbeNode(THREE, x, y, z, colorHex, label) {
    const probeGroup = new THREE.Group();
    probeGroup.position.set(x, y, z);

    // Mini cylinder probe body
    const bodyGeo = new THREE.CylinderGeometry(0.045, 0.045, 0.18, 12);
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x2e2e2e, metalness: 0.8, roughness: 0.2 });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    probeGroup.add(body);

    // Luminous beacon tip
    const tipGeo = new THREE.SphereGeometry(0.048, 12, 12);
    const tipMat = new THREE.MeshBasicMaterial({ color: colorHex });
    const tip = new THREE.Mesh(tipGeo, tipMat);
    tip.position.y = 0.1;
    probeGroup.add(tip);

    // Thin acoustic laser line to monolith core
    const lineMat = new THREE.LineDashedMaterial({
      color: colorHex,
      dashSize: 0.1,
      gapSize: 0.05,
      transparent: true,
      opacity: 0.45,
    });
    const lineGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(-x * 0.8, -y * 0.8, -z * 0.8),
    ]);
    const tether = new THREE.Line(lineGeo, lineMat);
    probeGroup.add(tether);

    probeGroup.userData = {
      basePos: new THREE.Vector3(x, y, z),
      phase: Math.random() * Math.PI * 2,
      label,
    };

    this.monolithGroup.add(probeGroup);
    this.probeNodes.push(probeGroup);
  }

  setupEvents(THREE) {
    // Mouse drag interaction for manual 3D rotation
    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    window.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const inCanvas =
        e.clientX >= rect.left &&
        e.clientX <= rect.right &&
        e.clientY >= rect.top &&
        e.clientY <= rect.bottom;

      // Normalized Device Coordinates for Raycasting
      this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      if (this.isDragging) {
        const deltaX = e.clientX - this.previousMousePosition.x;
        const deltaY = e.clientY - this.previousMousePosition.y;

        this.targetRotation.y += deltaX * 0.008;
        this.targetRotation.x += deltaY * 0.008;
        this.targetRotation.x = Math.max(-0.85, Math.min(0.85, this.targetRotation.x));

        this.previousMousePosition = { x: e.clientX, y: e.clientY };
      } else {
        // Subtle mouse parallax across the window
        const normX = (e.clientX - window.innerWidth / 2) / (window.innerWidth / 2);
        const normY = (e.clientY - window.innerHeight / 2) / (window.innerHeight / 2);

        this.mouseParallax.x = normX * 0.28;
        this.mouseParallax.y = normY * 0.22;
      }

      // Check raycast hover
      if (this.options.enableRaycasting && inCanvas) {
        this.checkRaycastHover();
      }
    });

    // Canvas click for interactive stratum inspection
    this.canvas.addEventListener('click', (e) => {
      if (this.hoveredObject && this.onClickCallback) {
        this.onClickCallback(this.hoveredObject.userData);
      } else if (!this.isDragging) {
        // Toggle explode state on direct click
        if (this.activeMode === 'assembled') {
          this.setMode('exploded');
        } else {
          this.setMode('assembled');
        }
      }
    });

    // Touch support for mobile
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
        this.targetRotation.x = Math.max(-0.85, Math.min(0.85, this.targetRotation.x));

        this.previousMousePosition = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    }, { passive: true });

    // Window resize
    window.addEventListener('resize', () => {
      this.handleResize();
    });

    // Visibility Observer
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          this.isVisible = entry.isIntersecting;
        });
      }, { threshold: 0.05 });
      observer.observe(this.canvas);
    }
  }

  checkRaycastHover() {
    if (!this.camera || !this.raycaster) return;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.strataLayers, false);

    if (intersects.length > 0) {
      const topHit = intersects[0].object;
      if (this.hoveredObject !== topHit) {
        if (this.hoveredObject) {
          this.hoveredObject.scale.set(1, 1, 1);
        }
        this.hoveredObject = topHit;
        this.hoveredObject.scale.set(1.025, 1.025, 1.025);

        if (this.onHoverCallback) {
          this.onHoverCallback(topHit.userData);
        }
      }
    } else {
      if (this.hoveredObject) {
        this.hoveredObject.scale.set(1, 1, 1);
        this.hoveredObject = null;
        if (this.onHoverCallback) {
          this.onHoverCallback(null);
        }
      }
    }
  }

  playIntroAnimation() {
    if (window.gsap) {
      const gsap = window.gsap;
      // Staged camera swoop entrance
      gsap.fromTo(
        this.camera.position,
        { x: 0, y: 3.5, z: 9.5 },
        {
          x: 0,
          y: 0.4,
          z: 6.2,
          duration: 2.2,
          ease: 'power3.out',
          onUpdate: () => {
            this.targetCameraPos.z = this.camera.position.z;
            this.targetCameraPos.y = this.camera.position.y;
          },
        }
      );

      gsap.fromTo(
        this.monolithGroup.rotation,
        { y: -Math.PI },
        { y: -0.42, duration: 2.4, ease: 'power2.out' }
      );
    }
  }

  setScrollProgress(progress) {
    // Progress normalized from 0.0 to 1.0 down the entire page
    // 0.0: Hero View
    // 0.25: Strata Deconstruction (Explosion)
    // 0.50: Hydrostatic Benchmark Slice
    // 0.75: Editorial Basin Regimes
    // 1.00: Deep Intelligence Console

    if (progress < 0.2) {
      // Hero
      this.targetExplodeFactor = progress * 1.5;
      this.targetCameraPos.z = 6.2 - progress * 2.0;
      this.targetCameraPos.y = 0.4 + progress * 0.5;
      this.targetRotation.y = -0.42 + progress * 2.0;
    } else if (progress < 0.5) {
      // Strata Deconstruction
      const sub = (progress - 0.2) / 0.3;
      this.targetExplodeFactor = 0.3 + sub * 0.7; // Full explode
      this.targetCameraPos.z = 5.8 - sub * 0.8;
      this.targetCameraPos.y = 0.5 + sub * 0.4;
      this.targetRotation.y = 0.2 + sub * 1.4;
    } else if (progress < 0.75) {
      // Hydrostatic Benchmark
      const sub = (progress - 0.5) / 0.25;
      this.targetExplodeFactor = 1.0 - sub * 0.6;
      this.targetCameraPos.z = 5.0 + sub * 0.8;
      this.targetRotation.y = 1.6 + sub * 1.2;
    } else {
      // Regimes & Console
      const sub = (progress - 0.75) / 0.25;
      this.targetExplodeFactor = 0.4 - sub * 0.4;
      this.targetCameraPos.z = 5.8 + sub * 0.8;
      this.targetRotation.y = 2.8 + sub * 1.4;
    }
  }

  setDepthSlice(depthMeters) {
    this.sliceDepth = Math.max(0, Math.min(1000, depthMeters));
    // Map 0–1000m to 3D Y-axis range [0.85 to -1.15]
    this.targetSliceY = 0.85 - (this.sliceDepth / 1000.0) * 2.0;

    if (this.slicePlane) {
      this.slicePlane.visible = true;
    }
  }

  setMode(mode) {
    this.activeMode = mode;
    switch (mode) {
      case 'exploded':
        this.targetExplodeFactor = 1.0;
        this.targetRotation.x = 0.32;
        this.targetRotation.y = -0.15;
        break;
      case 'core':
        this.targetExplodeFactor = 0.3;
        this.targetRotation.x = 0.08;
        this.targetRotation.y = Math.PI * 0.28;
        break;
      case 'sonar':
        this.triggerSonarWave();
        break;
      case 'wireframe':
        this.targetExplodeFactor = 0.2;
        break;
      case 'assembled':
      default:
        this.targetExplodeFactor = 0.0;
        this.targetRotation.x = 0.22;
        this.targetRotation.y = -0.42;
        break;
    }
  }

  triggerSonarWave() {
    this.pulsePhase = 0;
    this.activeMode = 'sonar';
  }

  handleResize() {
    if (!this.renderer || !this.camera) return;
    const width = this.canvas.clientWidth || window.innerWidth;
    const height = this.canvas.clientHeight || window.innerHeight;
    if (width === 0 || height === 0) return;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  animate() {
    this.animationFrameId = requestAnimationFrame(this.animate);

    if (!this.isVisible) return;

    const delta = this.clock ? this.clock.getDelta() : 0.016;
    const elapsed = this.clock ? this.clock.getElapsedTime() : 0;

    // Smooth inertia lerping for rotation
    const lerpSpeed = 0.065;
    const targetY = this.targetRotation.y + this.mouseParallax.x;
    const targetX = this.targetRotation.x + this.mouseParallax.y;

    this.currentRotation.y += (targetY - this.currentRotation.y) * lerpSpeed;
    this.currentRotation.x += (targetX - this.currentRotation.x) * lerpSpeed;

    // Continuous subtle idle drift when not dragging
    if (!this.isDragging) {
      this.targetRotation.y += 0.0016;
    }

    // Camera position interpolation
    this.currentCameraPos.z += (this.targetCameraPos.z - this.currentCameraPos.z) * 0.05;
    this.currentCameraPos.y += (this.targetCameraPos.y - this.currentCameraPos.y) * 0.05;
    this.camera.position.z = this.currentCameraPos.z;
    this.camera.position.y = this.currentCameraPos.y;

    if (this.monolithGroup) {
      this.monolithGroup.rotation.y = this.currentRotation.y;
      this.monolithGroup.rotation.x = this.currentRotation.x;

      // Animate strata explosion separation
      this.explodeFactor += (this.targetExplodeFactor - this.explodeFactor) * 0.08;
      this.strataLayers.forEach((layer) => {
        if (layer.userData && layer.userData.baseY !== undefined) {
          layer.position.y = layer.userData.baseY + layer.userData.explodeOffset * this.explodeFactor;
        }
      });

      // Animate depth laser slice plane
      this.currentSliceY += (this.targetSliceY - this.currentSliceY) * 0.1;
      if (this.slicePlane) {
        this.slicePlane.position.y = this.currentSliceY;
      }

      // Animate floating contour rings
      this.rings.forEach((r, idx) => {
        r.mesh.rotation.z += r.rotSpeed;
        r.mesh.position.y = r.baseY + Math.sin(elapsed * 1.5 + idx) * 0.045;
      });

      // Animate buoyant particulate field
      if (this.particles) {
        const positions = this.particles.geometry.attributes.position.array;
        for (let i = 0; i < positions.length / 3; i++) {
          positions[i * 3 + 1] += Math.sin(elapsed * 1.2 + i) * 0.0014;
        }
        this.particles.geometry.attributes.position.needsUpdate = true;
      }

      // Animate probe bobbing & laser line
      this.probeNodes.forEach((p) => {
        p.userData.phase += delta * 2.0;
        p.position.y = p.userData.basePos.y + Math.sin(p.userData.phase) * 0.09;
      });

      // Animate floating satellite shards
      this.satellites.forEach((sat) => {
        sat.phase += delta * sat.speed;
        sat.mesh.position.y = sat.basePos.y + Math.sin(sat.phase) * 0.18;
        sat.mesh.rotation.x += 0.01;
        sat.mesh.rotation.y += 0.015;
      });

      // Core point light breathing pulse
      if (this.corePointLight) {
        this.corePointLight.intensity = 2.2 + Math.sin(elapsed * 2.5) * 0.8;
      }

      // Sonar mode pulse wave
      if (this.activeMode === 'sonar') {
        this.pulsePhase += delta * 4.0;
        this.rings.forEach((r, i) => {
          const s = 1.0 + Math.sin(this.pulsePhase - i * 0.6) * 0.22;
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
