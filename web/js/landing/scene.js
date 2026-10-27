/**
 * Three.js 3D Ocean Scene ("Descent")
 * Verbatim port of 3D WebGL scene from landing_reference.html
 */

export function initScene(S, reduce) {
  var gfill = document.getElementById('gfill');
  var gtxt = document.getElementById('gtxt');
  var last = -1;

  try {
    var gl = document.getElementById('gl');
    if (!gl || typeof THREE === 'undefined') {
      document.body.classList.add('nogl');
      return;
    }

    var R = new THREE.WebGLRenderer({ canvas: gl, antialias: true });
    R.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    R.setSize(window.innerWidth, window.innerHeight);

    var sc = new THREE.Scene();
    var cam = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 200);
    var cTop = new THREE.Color('#2a6fa8');
    var cDeep = new THREE.Color('#03060c');
    var cc = new THREE.Color();
    sc.fog = new THREE.FogExp2(0x2a6fa8, 0.03);

    /* metres to scene units, stretched above 300 m */
    var Y = function(d) {
      return -(d <= 300 ? d * 0.06 : 18 + (d - 300) * 0.0229);
    };

    var su = { t: { value: 0 } };
    var surf = new THREE.Mesh(
      new THREE.PlaneGeometry(90, 90, 128, 128),
      new THREE.ShaderMaterial({
        uniforms: su,
        transparent: true,
        side: THREE.DoubleSide,
        vertexShader: 'uniform float t;varying float h;void main(){vec3 p=position;float w=sin(p.x*.35+t)*.25+sin(p.y*.5+t*1.3)*.18+sin((p.x+p.y)*.8+t*.8)*.08;p.z+=w;h=w;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}',
        fragmentShader: 'varying float h;void main(){vec3 c=mix(vec3(.04,.22,.36),vec3(.18,.62,.7),smoothstep(-.3,.4,h));c+=pow(smoothstep(.28,.45,h),2.)*.6;gl_FragColor=vec4(c,.88);}'
      })
    );
    surf.rotation.x = -Math.PI / 2;
    sc.add(surf);

    [50, 100, 150, 200, 300, 500, 700, 1000].forEach(function(d, i) {
      var th = d >= 50 && d <= 150;
      var m = new THREE.Mesh(
        new THREE.PlaneGeometry(70, 70),
        new THREE.MeshBasicMaterial({
          color: th ? 0xf5a524 : new THREE.Color().setHSL(0.56, 0.7, 0.55 - i * 0.05),
          transparent: true,
          opacity: th ? 0.1 : 0.07,
          side: THREE.DoubleSide,
          depthWrite: false
        })
      );
      m.rotation.x = -Math.PI / 2;
      m.position.y = Y(d);
      sc.add(m);

      var g = new THREE.GridHelper(70, 35, 0x2dd4bf, 0x2dd4bf);
      g.material.transparent = true;
      g.material.opacity = 0.08;
      g.position.y = Y(d);
      sc.add(g);
    });

    var N = window.innerWidth < 700 ? 700 : 1600;
    var pa = new Float32Array(N * 3);
    var ps = new Float32Array(N);
    for (var i = 0; i < N; i++) {
      pa[i * 3] = (Math.random() - 0.5) * 44;
      pa[i * 3 + 1] = -Math.random() * 38;
      pa[i * 3 + 2] = (Math.random() - 0.5) * 34 - 4;
      ps[i] = Math.random();
    }
    var pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.BufferAttribute(pa, 3));
    pg.setAttribute('s', new THREE.BufferAttribute(ps, 1));
    var pu = { t: { value: 0 } };
    sc.add(new THREE.Points(
      pg,
      new THREE.ShaderMaterial({
        uniforms: pu,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        vertexShader: 'uniform float t;attribute float s;varying float a;void main(){vec3 p=position;p.y=mod(p.y+t*(.15+s*.3)+40.,40.)-38.;p.x+=sin(t*.3+s*20.)*.4;vec4 mv=modelViewMatrix*vec4(p,1.);gl_PointSize=(2.+s*3.)*(30./-mv.z);a=.25+s*.5;gl_Position=projectionMatrix*mv;}',
        fragmentShader: 'varying float a;void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;gl_FragColor=vec4(.7,.95,.95,a*(1.-d*2.));}'
      })
    ));

    var orb = new THREE.Mesh(
      new THREE.TorusGeometry(11, 0.02, 6, 128),
      new THREE.MeshBasicMaterial({ color: 0x2dd4bf, transparent: true, opacity: 0.5 })
    );
    orb.rotation.x = Math.PI / 2.4;
    orb.position.set(0, 7, -4);
    sc.add(orb);

    var sat = new THREE.Mesh(
      new THREE.BoxGeometry(0.5, 0.25, 0.25),
      new THREE.MeshBasicMaterial({ color: 0xeaf2ff })
    );
    orb.add(sat);

    var fl = new THREE.Group();
    fl.add(new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.12, 1.4, 12),
      new THREE.MeshBasicMaterial({ color: 0xeaf2ff })
    ));
    var cap = new THREE.Mesh(
      new THREE.SphereGeometry(0.18, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0x2dd4bf })
    );
    cap.position.y = 0.8;
    fl.add(cap);

    var ant = new THREE.Mesh(
      new THREE.CylinderGeometry(0.015, 0.015, 1, 6),
      new THREE.MeshBasicMaterial({ color: 0x9fb0c8 })
    );
    ant.position.y = 1.4;
    fl.add(ant);
    fl.position.set(3.2, Y(500), -3);
    sc.add(fl);

    var mx = 0, cx = 0;
    if (!reduce) {
      window.addEventListener('pointermove', function(e) {
        mx = (e.clientX / window.innerWidth - 0.5) * 2;
      });
    }

    window.addEventListener('resize', function() {
      R.setSize(window.innerWidth, window.innerHeight);
      cam.aspect = window.innerWidth / window.innerHeight;
      cam.updateProjectionMatrix();
    });

    var clock = new THREE.Clock();
    var t = 0;

    (function loop() {
      requestAnimationFrame(loop);
      var dt = Math.min(clock.getDelta(), 0.05);
      if (!S.paused) {
        t += dt * (reduce ? 0.15 : 1);
      }
      S.p += (S.tp - S.p) * (reduce ? 1 : 0.06);
      cx += (mx - cx) * 0.05;
      var p = S.p;

      cam.position.set(cx * 1.4, 3 - p * 38, 16 - 6 * p);
      cam.lookAt(0, cam.position.y - 1.5, 0);

      cc.copy(cTop).lerp(cDeep, Math.min(1, p * 1.6));
      sc.fog.color.copy(cc);
      R.setClearColor(cc);
      sc.fog.density = 0.03 + 0.02 * p;

      su.t.value = t;
      pu.t.value = t;

      var a = t * 0.3;
      sat.position.set(Math.cos(a) * 11, Math.sin(a) * 11, 0);
      fl.position.y = Y(500) + Math.sin(t * 0.4) * 4;

      var dm = Math.round(p * 1000);
      if (dm !== last) {
        last = dm;
        if (gtxt) gtxt.textContent = dm + ' m';
        if (gfill) gfill.style.height = (p * 100) + '%';
        if (gtxt) gtxt.style.top = (p * 100) + '%';
      }

      R.render(sc, cam);
    })();
  } catch (e) {
    console.error('WebGL initialization failed:', e);
    document.body.classList.add('nogl');
  }
}
