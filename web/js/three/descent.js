// Scroll-driven descent: progress through a tall section maps to a depth from 0 to 1000 m,
// stepping through the 15 standard depths. Drives the side gauge, the page tint (--depth-t)
// and the background scene. Uses GSAP ScrollTrigger when present, a scroll listener otherwise.

export const DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000];

/** Progress 0–1 → depth (m), linear in depth *index* so every standard level gets equal scroll. */
export function progressToDepth(p) {
  const f = Math.min(1, Math.max(0, p)) * (DEPTHS.length - 1);
  const i = Math.floor(f);
  if (i >= DEPTHS.length - 1) return DEPTHS.at(-1);
  return DEPTHS[i] + (DEPTHS[i + 1] - DEPTHS[i]) * (f - i);
}

export function depthToProgress(d) {
  for (let i = 1; i < DEPTHS.length; i++) {
    if (d <= DEPTHS[i]) return (i - 1 + (d - DEPTHS[i - 1]) / (DEPTHS[i] - DEPTHS[i - 1])) / (DEPTHS.length - 1);
  }
  return 1;
}

/**
 * @param {HTMLElement} section  the tall scroll section
 * @param {(p:number, depth:number) => void} onProgress
 * @param {{stages: HTMLElement[], onStage: (i:number) => void, reduced: boolean}} opts
 */
export function initDescent(section, onProgress, { stages = [], onStage = () => {}, reduced = false } = {}) {
  const ST = window.ScrollTrigger;
  const gsap = window.gsap;
  const kills = [];
  let lastStage = -1;

  const update = (p) => {
    onProgress(p, progressToDepth(p));
    const idx = Math.min(stages.length - 1, Math.floor(p * stages.length * 0.999));
    if (idx !== lastStage) {
      lastStage = idx;
      onStage(idx);
    }
  };

  if (ST && gsap) {
    gsap.registerPlugin(ST);
    const st = ST.create({ trigger: section, start: 'top 60%', end: 'bottom bottom', scrub: reduced ? false : 0.6, onUpdate: (self) => update(self.progress) });
    kills.push(() => st.kill());
    if (!reduced) {
      for (const s of stages) {
        const tw = gsap.fromTo(s, { opacity: 0.25, y: 40 }, {
          opacity: 1, y: 0, ease: 'power2.out',
          scrollTrigger: { trigger: s, start: 'top 85%', end: 'top 45%', scrub: true },
        });
        kills.push(() => { tw.scrollTrigger?.kill(); tw.kill(); });
      }
    }
    update(st.progress);
  } else {
    const onScroll = () => {
      const r = section.getBoundingClientRect();
      const vh = window.innerHeight * 0.6;
      update(Math.min(1, Math.max(0, (vh - r.top) / r.height)));
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    kills.push(() => window.removeEventListener('scroll', onScroll));
    onScroll();
  }

  return () => kills.forEach((k) => k());
}
