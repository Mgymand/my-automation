/* 背景の光の粒（軽量パーティクル）。prefers-reduced-motion では静止。 */
(() => {
  const c = document.getElementById('stars'); if (!c) return;
  const ctx = c.getContext('2d'); let w, h, pts = [], raf;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const COLORS = ['233,196,106', '255,107,154', '94,234,212', '167,139,250', '255,255,255'];
  function resize() { w = c.width = innerWidth * devicePixelRatio; h = c.height = innerHeight * devicePixelRatio; init(); }
  function init() {
    const n = Math.min(140, Math.floor((innerWidth * innerHeight) / 14000));
    pts = Array.from({ length: n }, () => ({ x: Math.random() * w, y: Math.random() * h, r: (Math.random() * 1.6 + .4) * devicePixelRatio, s: Math.random() * .25 + .05, a: Math.random() * Math.PI * 2, c: COLORS[Math.floor(Math.random() * COLORS.length)], tw: Math.random() * 2 + 1 }));
  }
  let t = 0;
  function frame() {
    t += .016; ctx.clearRect(0, 0, w, h);
    for (const p of pts) {
      p.y -= p.s * devicePixelRatio; p.x += Math.sin(t * .6 + p.a) * .15 * devicePixelRatio;
      if (p.y < -10) { p.y = h + 10; p.x = Math.random() * w; }
      const al = .35 + .35 * Math.sin(t * p.tw + p.a);
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${p.c},${al})`; ctx.shadowColor = `rgba(${p.c},.9)`; ctx.shadowBlur = 8 * devicePixelRatio; ctx.fill();
    }
    if (!reduce) raf = requestAnimationFrame(frame);
  }
  addEventListener('resize', resize); resize(); frame();
  document.addEventListener('visibilitychange', () => { if (document.hidden) cancelAnimationFrame(raf); else if (!reduce) frame(); });
})();
