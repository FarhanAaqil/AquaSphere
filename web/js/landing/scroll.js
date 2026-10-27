/**
 * GSAP + ScrollTrigger controller for Landing Page ("Descent")
 * Verbatim port of scroll motion from landing_reference.html
 */

export function initScroll(S, reduce) {
  if (window.gsap && window.ScrollTrigger) {
    gsap.registerPlugin(ScrollTrigger);

    ScrollTrigger.create({
      start: 0,
      end: 'max',
      onUpdate: function(s) {
        S.tp = s.progress;
      }
    });

    gsap.utils.toArray('.rv').forEach(function(el) {
      gsap.from(el, {
        y: reduce ? 0 : 28,
        opacity: 0,
        duration: reduce ? 0 : 0.9,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: el,
          start: 'top 88%',
          once: true
        }
      });
    });

    if (!reduce) {
      gsap.to('#hline', {
        scaleY: 1,
        ease: 'none',
        scrollTrigger: {
          trigger: '#how',
          start: 'top 55%',
          end: 'bottom 60%',
          scrub: true
        }
      });
    } else {
      gsap.set('#hline', { scaleY: 1 });
    }

    document.querySelectorAll('.bar').forEach(function(b) {
      var o = { v: 0 };
      var n = b.querySelector('b');
      var target = parseFloat(b.dataset.v);
      ScrollTrigger.create({
        trigger: b,
        start: 'top 88%',
        once: true,
        onEnter: function() {
          gsap.from(b.querySelector('i'), {
            width: 0,
            duration: reduce ? 0 : 1.2,
            ease: 'power3.out'
          });
          gsap.to(o, {
            v: target,
            duration: reduce ? 0 : 1.4,
            ease: 'power2.out',
            onUpdate: function() {
              if (n) n.textContent = o.v.toFixed(2);
            }
          });
        }
      });
    });

    if (document.fonts) {
      document.fonts.ready.then(function() {
        ScrollTrigger.refresh();
      });
    }
  } else {
    document.querySelectorAll('.bar b').forEach(function(n) {
      if (n.parentNode && n.parentNode.dataset.v) {
        n.textContent = n.parentNode.dataset.v;
      }
    });
  }
}
