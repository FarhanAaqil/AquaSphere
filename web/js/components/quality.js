/**
 * AquaSphere Runtime Quality Tier Controller (Playbook §8)
 * Auto-selects quality tier based on device capabilities and monitors FPS.
 */

export class QualityController {
  constructor() {
    this.tier = this.detectInitialTier();
    this.fps = 60;
    this.frames = 0;
    this.lastTime = performance.now();
    this.dpr = this.getTierDpr();
    this.settings = this.getTierSettings();
  }

  detectInitialTier() {
    // Check hardware concurrency, memory and mobile status
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    const cores = navigator.hardwareConcurrency || 4;
    const memory = navigator.deviceMemory || 4; // GB

    if (isMobile) {
      return (cores >= 6 && memory >= 4) ? 'medium' : 'low';
    }

    if (cores >= 8 && memory >= 8) {
      return 'high';
    } else if (cores >= 4 && memory >= 4) {
      return 'medium';
    }

    return 'low';
  }

  getTierDpr() {
    const maxDpr = window.devicePixelRatio || 1;
    switch (this.tier) {
      case 'high':
        return Math.min(maxDpr, 2.0);
      case 'medium':
        return Math.min(maxDpr, 1.5);
      case 'low':
      default:
        return 1.0;
    }
  }

  getTierSettings() {
    switch (this.tier) {
      case 'high':
        return {
          particleCount: 16000,
          surfaceSegments: 160,
          enablePostFx: true,
          shadows: true,
        };
      case 'medium':
        return {
          particleCount: 6000,
          surfaceSegments: 96,
          enablePostFx: false,
          shadows: false,
        };
      case 'low':
      default:
        return {
          particleCount: 1500,
          surfaceSegments: 48,
          enablePostFx: false,
          shadows: false,
        };
    }
  }

  // Runtime monitor called every frame; downgrades if sustained FPS drops below 24
  update() {
    this.frames++;
    const now = performance.now();
    if (now >= this.lastTime + 1000) {
      this.fps = Math.round((this.frames * 1000) / (now - this.lastTime));
      this.frames = 0;
      this.lastTime = now;

      // Downgrade protection (never upgrade mid-session per Playbook §8.1)
      if (this.fps < 24 && this.tier === 'high') {
        this.tier = 'medium';
        this.dpr = this.getTierDpr();
        this.settings = this.getTierSettings();
        console.warn('AquaSphere Quality: Downgraded to medium tier due to FPS dip (' + this.fps + ' fps)');
      } else if (this.fps < 20 && this.tier === 'medium') {
        this.tier = 'low';
        this.dpr = this.getTierDpr();
        this.settings = this.getTierSettings();
        console.warn('AquaSphere Quality: Downgraded to low tier due to FPS dip (' + this.fps + ' fps)');
      }
    }
  }
}
