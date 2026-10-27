/**
 * GSAP + ScrollTrigger controller for Landing Page ("Descent")
 * Verbatim port of scroll motion from landing_reference.html with data-driven evidence bars.
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

    if (document.fonts) {
      document.fonts.ready.then(function() {
        ScrollTrigger.refresh();
      });
    }
  }
}

export function setupEvidenceBars(data, reduce) {
  if (!data || !data.baselines) return;

  const profEl = document.getElementById('ev-profiles');
  const floatsEl = document.getElementById('ev-floats');
  if (profEl && data.n_eval_profiles) profEl.textContent = data.n_eval_profiles;
  if (floatsEl && data.n_eval_floats) floatsEl.textContent = data.n_eval_floats;

  const climRmse = data.baselines["Climatology"]?.thermocline_rmse || 2.29;
  const ridgeRmse = data.baselines["Climatology + Ridge"]?.thermocline_rmse || 2.1952;
  const v1Rmse = data.baselines["v1 OceanEmbedNet (Re-evaluated)"]?.thermocline_rmse || 1.5903;
  const treesRmse = data.baselines["Gradient Boosted Trees (HistGBDT)"]?.thermocline_rmse || 1.4602;

  const mapping = [
    { id: 'bar-climatology', val: climRmse },
    { id: 'bar-climatology-ridge', val: ridgeRmse },
    { id: 'bar-v1-network', val: v1Rmse },
    { id: 'bar-gradient-trees', val: treesRmse }
  ];

  mapping.forEach(item => {
    const el = document.getElementById(item.id);
    if (!el) return;
    const targetVal = item.val;
    const targetPct = Math.round((targetVal / climRmse) * 100);
    el.dataset.v = targetVal.toFixed(2);
    el.dataset.w = targetPct;

    const n = el.querySelector('b');
    const barFill = el.querySelector('i');

    if (window.gsap && window.ScrollTrigger) {
      const o = { v: 0 };
      ScrollTrigger.create({
        trigger: el,
        start: 'top 88%',
        once: true,
        onEnter: function() {
          gsap.fromTo(barFill, { width: 0 }, {
            width: targetPct + '%',
            duration: reduce ? 0 : 1.2,
            ease: 'power3.out'
          });
          gsap.to(o, {
            v: targetVal,
            duration: reduce ? 0 : 1.4,
            ease: 'power2.out',
            onUpdate: function() {
              if (n) n.textContent = o.v.toFixed(2);
            }
          });
        }
      });
    } else {
      if (barFill) barFill.style.width = targetPct + '%';
      if (n) n.textContent = targetVal.toFixed(2);
    }
  });

  if (window.ScrollTrigger) {
    ScrollTrigger.refresh();
  }
}
