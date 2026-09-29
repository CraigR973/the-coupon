// Is the tab-bar indicator misplacement a reduced-motion capture artefact? Measure it with
// motion on and off, on four routes, after a 1.5 s settle, plus the Football tab's label/icon.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, NOTES } from './lib.mjs';
const b = await chromium.launch();
const lines = [];
for (const reducedMotion of ['no-preference', 'reduce']) {
  for (const path of ['/', '/leagues/the-coupon/predictions', '/football', '/leagues/the-coupon/leaderboard']) {
    const ctx = await newContext(b, { width: 390, theme: 'dark', persona: 'Alice', reducedMotion });
    const page = await ctx.newPage();
    await page.goto(`http://127.0.0.1:4360${path}`);
    await settle(page);
    await page.waitForTimeout(1500);
    const m = await page.evaluate(() => {
      const nav = document.querySelector('nav[aria-label="Primary"]');
      const ind = nav.querySelector('[data-testid="tabbar-indicator"]').getBoundingClientRect();
      const active = [...nav.querySelectorAll('a, button')].find((a) => a.getAttribute('aria-current') === 'page' || a.className.includes('text-primary'));
      const ar = active?.getBoundingClientRect();
      const fb = [...nav.querySelectorAll('a')].find((a) => /Football/.test(a.textContent));
      const fbIcon = fb?.querySelector('svg')?.getBoundingClientRect();
      const fbLabel = fb ? [...fb.querySelectorAll('span')].map((s) => s.getBoundingClientRect()).find((r) => r.height > 0) : null;
      return {
        active: active?.textContent.trim(), activeX: ar ? [Math.round(ar.left), Math.round(ar.right)] : null,
        indicatorX: [Math.round(ind.left), Math.round(ind.right)],
        offset: ar ? Math.round((ind.left + ind.right) / 2 - (ar.left + ar.right) / 2) : null,
        footballIcon: fbIcon ? `${Math.round(fbIcon.width)}x${Math.round(fbIcon.height)}` : null,
        footballLabelLines: fbLabel ? Math.round(fbLabel.height / 16) : null,
      };
    });
    lines.push(`${reducedMotion} ${path}: active=${m.active} tab x=${JSON.stringify(m.activeX)} indicator x=${JSON.stringify(m.indicatorX)} centre offset=${m.offset}px; football icon ${m.footballIcon}, label ~${m.footballLabelLines} line(s)`);
    await ctx.close();
  }
}
await b.close();
writeFileSync(`${NOTES}/tabbar-probe.txt`, lines.join('\n') + '\n');
console.log(lines.join('\n'));
