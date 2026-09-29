// SC 2.4.11 Focus Not Obscured (Minimum): is the focused control hidden behind the fixed
// bottom tab bar or the sticky header when a keyboard user Tabs down (and Shift+Tabs back up)?
// For each stop, five points (centre + four inset corners) are hit-tested with
// elementFromPoint; a stop is "fully obscured" when none of them lands on the focused
// element and at least one lands on the tab bar / header.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, WEB, NOTES } from './lib.mjs';

const routes = [
  ['/leagues/the-coupon/predictions', 'Carol'], ['/', 'Alice'], ['/leagues/the-coupon/leaderboard', 'Alice'],
  ['/settings', 'Alice'], ['/leagues/the-coupon/admin/settings', 'Alice'], ['/football', 'Alice'],
];
const lines = [];
const out = [];
const browser = await chromium.launch();
for (const width of [390, 1280]) {
  for (const [route, persona] of routes) {
    const ctx = await newContext(browser, { width, theme: 'dark', persona });
    const page = await ctx.newPage();
    await page.goto(`${WEB}${route}`);
    await settle(page);
    const res = { route, width, down: [], up: [] };
    for (const [dir, key, n] of [['down', 'Tab', 70], ['up', 'Shift+Tab', 70]]) {
      const seen = new Set();
      for (let i = 0; i < n; i++) {
        await page.keyboard.press(key);
        await page.waitForTimeout(60);
        const r = await page.evaluate(() => {
          const el = document.activeElement;
          if (!el || el === document.body) return null;
          const b = el.getBoundingClientRect();
          if (b.width === 0 || b.height === 0) return null;
          const pts = [[0.5, 0.5], [0.15, 0.15], [0.85, 0.15], [0.15, 0.85], [0.85, 0.85]].map(([fx, fy]) => [b.x + b.width * fx, b.y + b.height * fy]);
          const chrome = (t) => t && t.closest('nav[aria-label="Primary"], header');
          let onEl = 0, onChrome = 0;
          for (const [x, y] of pts) {
            if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
            const t = document.elementFromPoint(x, y);
            if (t && (el === t || el.contains(t))) onEl++;
            else if (chrome(t) && !chrome(el)) onChrome++;
          }
          const name = (el.getAttribute('aria-label') || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40);
          return { key: name + Math.round(b.y + scrollY), name, onEl, onChrome, inChrome: !!chrome(el) };
        });
        if (!r) continue;
        if (seen.has(r.key)) break;
        seen.add(r.key);
        if (!r.inChrome) res[dir].push(r);
      }
    }
    const full = (list) => list.filter((r) => r.onEl === 0 && r.onChrome > 0);
    const part = (list) => list.filter((r) => r.onEl > 0 && r.onChrome > 0);
    const f = full(res.down), fu = full(res.up);
    lines.push(`${width} ${route}: Tab ${res.down.length} stops, fully hidden ${f.length} [${f.map((r) => r.name).join(' | ')}], partly ${part(res.down).length}; Shift+Tab ${res.up.length} stops, fully hidden ${fu.length} [${fu.map((r) => r.name).join(' | ')}], partly ${part(res.up).length}`);
    out.push(res);
    await ctx.close();
  }
}
writeFileSync(`${NOTES}/obscured.json`, JSON.stringify(out, null, 1));
writeFileSync(`${NOTES}/obscured.txt`, lines.join('\n') + '\n');
console.log(lines.join('\n'));
await browser.close();
