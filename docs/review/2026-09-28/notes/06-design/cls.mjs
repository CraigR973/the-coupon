// DES-05: does content still jump when skeletons resolve? Hold every API GET for 1.2 s,
// record cumulative layout shift (PerformanceObserver 'layout-shift') through load + 2.5 s.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, API, NOTES } from './lib.mjs';
const b = await chromium.launch();
const lines = [];
for (const path of ['/', '/leagues/the-coupon/predictions', '/leagues/the-coupon/leaderboard', '/leagues/the-coupon/predictions/results', '/football', '/profile']) {
  for (const width of [390, 1280]) {
    const ctx = await newContext(b, { width, theme: 'dark', persona: 'Alice', reducedMotion: 'reduce' });
    await ctx.addInitScript(() => {
      window.__cls = 0; window.__shifts = [];
      new PerformanceObserver((l) => { for (const e of l.getEntries()) { if (!e.hadRecentInput) { window.__cls += e.value; window.__shifts.push(Math.round(e.value * 1000) / 1000); } } }).observe({ type: 'layout-shift', buffered: true });
    });
    const page = await ctx.newPage();
    await page.route((u) => u.href.startsWith(API) && u.pathname.startsWith('/api/'), async (r) => { await new Promise((res) => setTimeout(res, 1200)); await r.continue(); });
    await page.goto(`http://127.0.0.1:4360${path}`);
    await page.waitForTimeout(4000);
    const m = await page.evaluate(() => ({ cls: Math.round(window.__cls * 1000) / 1000, shifts: window.__shifts.slice(0, 8) }));
    lines.push(`${path} @${width}: CLS ${m.cls} (shifts ${JSON.stringify(m.shifts)})`);
    await ctx.close();
  }
}
await b.close();
writeFileSync(`${NOTES}/cls.txt`, '# every API GET held 1.2 s; CLS through load + 4 s; reduced motion\n' + lines.join('\n') + '\n');
console.log(lines.join('\n'));
