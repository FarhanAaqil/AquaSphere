/**
 * AquaSphere Cinematic Motion & Interaction Controller
 * Powered by GSAP + ScrollTrigger
 * Custom Magnetic Cursor, Staged Preloader, 3D Tilt Physics, and Magnetic Buttons
 */

export class CinematicController {
  constructor(monolithEngine = null) {
    this.monolith = monolithEngine;
    this.cursorDot = null;
    this.cursorCircle = null;
    this.cursorPos = { x: -100, y: -100 };
    this.circlePos = { x: -100, y: -100 };
    this.isHoveringInteractive = false;
    this.magneticTarget = null;
    this.scrollTriggerInstances = [];

    this.init();
  }

  init() {
    this.setupCustomCursor();
    this.setupMagneticButtons();
    this.setup3DCardTilt();
    this.setupScrollTrigger();
  }

  setupCustomCursor() {
    // Only initialize custom cursor on devices with fine pointer (desktop)
    if (!window.matchMedia('(pointer: fine)').matches) return;

    // Create cursor DOM elements if not already present
    let dot = document.querySelector('.cursor-dot');
    let circle = document.querySelector('.cursor-circle');

    if (!dot) {
      dot = document.createElement('div');
      dot.className = 'cursor-dot';
      document.body.appendChild(dot);
    }

    if (!circle) {
      circle = document.createElement('div');
      circle.className = 'cursor-circle';
      circle.innerHTML = '<span class="cursor-text"></span>';
      document.body.appendChild(circle);
    }

    this.cursorDot = dot;
    this.cursorCircle = circle;

    window.addEventListener('mousemove', (e) => {
      this.cursorPos.x = e.clientX;
      this.cursorPos.y = e.clientY;

      dot.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0)`;
    });

    // Smooth spring follower loop for circle
    const cursorText = circle.querySelector('.cursor-text');
    const updateCircle = () => {
      const spring = 0.16;
      this.circlePos.x += (this.cursorPos.x - this.circlePos.x) * spring;
      this.circlePos.y += (this.cursorPos.y - this.circlePos.y) * spring;

      circle.style.transform = `translate3d(${this.circlePos.x}px, ${this.circlePos.y}px, 0)`;
      requestAnimationFrame(updateCircle);
    };
    requestAnimationFrame(updateCircle);

    // Cursor hover states
    document.addEventListener('mouseover', (e) => {
      const target = e.target.closest('a, button, input[type="range"], .chip, .slab-pill, .btn-regime-focus');
      const is3DCanvas = e.target.closest('#threeMonolithCanvas, .canvas-stage');

      if (is3DCanvas) {
        circle.classList.add('hover-3d');
        if (cursorText) cursorText.textContent = 'EXPLODE';
      } else if (target) {
        circle.classList.add('hover-active');
        if (cursorText) cursorText.textContent = '';
      }
    });

    document.addEventListener('mouseout', (e) => {
      const is3DCanvas = e.target.closest('#threeMonolithCanvas, .canvas-stage');
      const target = e.target.closest('a, button, input[type="range"], .chip, .slab-pill');

      if (is3DCanvas || target) {
        circle.classList.remove('hover-3d', 'hover-active');
        if (cursorText) cursorText.textContent = '';
      }
    });

    document.addEventListener('mousedown', () => {
      circle.classList.add('cursor-pressed');
    });

    document.addEventListener('mouseup', () => {
      circle.classList.remove('cursor-pressed');
    });
  }

  setupMagneticButtons() {
    if (!window.matchMedia('(pointer: fine)').matches) return;

    const buttons = document.querySelectorAll('.btn-cobalt, .btn-tactile, .btn-magnetic');
    buttons.forEach((btn) => {
      btn.addEventListener('mousemove', (e) => {
        const rect = btn.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;

        const distanceX = e.clientX - centerX;
        const distanceY = e.clientY - centerY;

        // Smooth magnetic pull
        const magneticStrength = 0.28;
        btn.style.transform = `translate3d(${distanceX * magneticStrength}px, ${distanceY * magneticStrength}px, 0)`;
      });

      btn.addEventListener('mouseleave', () => {
        btn.style.transform = 'translate3d(0, 0, 0)';
      });
    });
  }

  setup3DCardTilt() {
    const tiltCards = document.querySelectorAll('.card-tilt-3d, .regime-card, .station-slab, .depth-slider-slab');

    tiltCards.forEach((card) => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        // Subtle 3D perspective rotation
        const rotateX = -((y - centerY) / centerY) * 5.0; // max 5 deg
        const rotateY = ((x - centerX) / centerX) * 5.0;

        card.style.transform = `perspective(1000px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) scale3d(1.01, 1.01, 1.01)`;
      });

      card.addEventListener('mouseleave', () => {
        card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)';
      });
    });
  }

  setupScrollTrigger() {
    if (!window.gsap || !window.ScrollTrigger) return;

    const gsap = window.gsap;
    const ScrollTrigger = window.ScrollTrigger;
    gsap.registerPlugin(ScrollTrigger);

    // 1. Full-page Scroll-linked 3D Camera & Strata Timeline
    if (this.monolith) {
      ScrollTrigger.create({
        trigger: document.body,
        start: 'top top',
        end: 'bottom bottom',
        scrub: 1.2,
        onUpdate: (self) => {
          this.monolith.setScrollProgress(self.progress);
        },
      });
    }

    // 2. Section Entrance Reveals
    const revealSections = document.querySelectorAll('.section-showcase, .section-stratum, .section-console');
    revealSections.forEach((sec) => {
      gsap.fromTo(
        sec.querySelectorAll('.section-title, .section-kicker, .regime-card, .depth-slider-slab, .array-matrix-col'),
        { opacity: 0, y: 40 },
        {
          opacity: 1,
          y: 0,
          duration: 0.9,
          stagger: 0.12,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: sec,
            start: 'top 80%',
            toggleActions: 'play none none reverse',
          },
        }
      );
    });

    // 3. Staggered Headline Reveal for Hero Title
    const revealWords = document.querySelectorAll('.hero-title .reveal-word, .hero-subtitle-row .reveal-word');
    if (revealWords.length > 0) {
      gsap.fromTo(
        revealWords,
        { opacity: 0, y: 50, rotateX: 20 },
        {
          opacity: 1,
          y: 0,
          rotateX: 0,
          duration: 1.1,
          stagger: 0.08,
          ease: 'power4.out',
          delay: 0.4,
        }
      );
    }

    // 4. Distinctive Footer Stagger
    const footer = document.querySelector('.studio-footer');
    if (footer) {
      gsap.fromTo(
        footer.querySelectorAll('.footer-top, .footer-bottom'),
        { opacity: 0, y: 30 },
        {
          opacity: 1,
          y: 0,
          duration: 0.8,
          stagger: 0.15,
          scrollTrigger: {
            trigger: footer,
            start: 'top 92%',
          },
        }
      );
    }
  }

  playPreloader(onComplete = null) {
    const loader = document.getElementById('cinematicLoader');
    if (!loader) {
      if (onComplete) onComplete();
      return;
    }

    const countEl = loader.querySelector('.loader-count');
    const barEl = loader.querySelector('.loader-fill');

    let count = 0;
    const interval = setInterval(() => {
      count += Math.floor(Math.random() * 8) + 4;
      if (count >= 100) {
        count = 100;
        clearInterval(interval);

        if (countEl) countEl.textContent = '100%';
        if (barEl) barEl.style.width = '100%';

        // Split-curtain exit animation
        if (window.gsap) {
          const gsap = window.gsap;
          gsap.to(loader, {
            clipPath: 'polygon(0% 0%, 100% 0%, 100% 0%, 0% 0%)',
            duration: 1.0,
            ease: 'power4.inOut',
            onComplete: () => {
              loader.style.display = 'none';
              if (onComplete) onComplete();
            },
          });
        } else {
          loader.style.opacity = '0';
          setTimeout(() => {
            loader.style.display = 'none';
            if (onComplete) onComplete();
          }, 600);
        }
      } else {
        if (countEl) countEl.textContent = `${count < 10 ? '0' : ''}${count}%`;
        if (barEl) barEl.style.width = `${count}%`;
      }
    }, 40);
  }

  destroy() {
    if (window.ScrollTrigger) {
      window.ScrollTrigger.getAll().forEach((t) => t.kill());
    }
    if (this.cursorDot) this.cursorDot.remove();
    if (this.cursorCircle) this.cursorCircle.remove();
  }
}
