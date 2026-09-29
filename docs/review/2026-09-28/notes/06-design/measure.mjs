// Geometry + type census of the core screens, for Part 1 (DES-01/02/08/09) and the
// chrome-before-content finding. Writes measure-<PHASE>.json and a readable .txt.
//   first-content y: the top of the first element that is the screen's reason to exist
//   type census: rendered font sizes of visible text nodes (leaf elements with text)
//   tracked labels: visible elements with uppercase transform and letter-spacing >= 0.1em
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, NOTES } from './lib.mjs';

const PHASE = process.env.PHASE || 'open';
const persona = process.env.PERSONA || 'Alice';
const screens = [
  { name: 'home', path: '/', first: '[data-testid^="league-card"], a[href*="/leagues/"] h3, article' },
  { name: 'current-round', path: '/leagues/the-coupon/predictions', first: 'button[data-testid^="selection-"], [data-testid="settled-leg"], [data-testid^="coupon-leg"]' },
  { name: 'standings', path: '/leagues/the-coupon/leaderboard', first: '[data-testid^="standings-row"], [data-testid^="leaderboard-row"], ol li, table tbody tr' },
  { name: 'results', path: '/leagues/the-coupon/predictions/results', first: 'a[href*="/predictions/"][href*="gameweek"], [data-testid^="result-row"], main ul li, main ol li' },
];
const browser = await chromium.launch();
const out = [];
for (const width of [390, 1280]) {
  for (const s of screens) {
    const ctx = await newContext(browser, { width, theme: 'dark', persona });
    const page = await ctx.newPage();
    await page.goto(`http://127.0.0.1:4360${s.path}`);
    await settle(page);
    const m = await page.evaluate((firstSel) => {
      const vis = (el) => {
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) > 0;
      };
      const all = [...document.querySelectorAll('main *, header *, nav *')].filter(vis);
      const leaves = all.filter((el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));
      const sizes = {};
      const small = [];
      for (const el of leaves) {
        const fs = parseFloat(getComputedStyle(el).fontSize);
        sizes[fs] = (sizes[fs] || 0) + 1;
        if (fs < 12) small.push({ fs, text: el.textContent.trim().slice(0, 40) });
      }
      const tracked = leaves.filter((el) => {
        const cs = getComputedStyle(el);
        const ls = parseFloat(cs.letterSpacing) / parseFloat(cs.fontSize);
        return cs.textTransform === 'uppercase' && ls >= 0.1;
      });
      const first = [...document.querySelectorAll(firstSel)].find(vis);
      const main = document.querySelector('main');
      const mr = main?.getBoundingClientRect();
      const bar = document.querySelector('nav[aria-label="Primary"]');
      const br = bar && vis(bar) ? bar.getBoundingClientRect() : null;
      return {
        firstContentTop: first ? Math.round(first.getBoundingClientRect().top + scrollY) : null,
        firstContentText: first ? first.textContent.trim().slice(0, 50) : null,
        viewportH: innerHeight,
        usableBottom: br ? Math.round(br.top) : innerHeight,
        docH: document.documentElement.scrollHeight,
        mainWidth: mr ? Math.round(mr.width) : null,
        mainLeft: mr ? Math.round(mr.left) : null,
        fontSizes: sizes,
        distinctSizes: Object.keys(sizes).length,
        under12: small.length,
        under12Sample: small.slice(0, 6),
        trackedLabels: tracked.length,
        trackedSample: tracked.slice(0, 12).map((e) => e.textContent.trim().slice(0, 30)),
        fontFamilies: [...new Set(leaves.map((e) => getComputedStyle(e).fontFamily.split(',')[0].replace(/"/g, '')))],
      };
    }, s.first);
    const rec = { phase: PHASE, persona, screen: s.name, width, ...m };
    rec.firstContentAboveFold = rec.firstContentTop != null ? rec.firstContentTop < rec.usableBottom : null;
    out.push(rec);
    await ctx.close();
  }
}
await browser.close();
writeFileSync(`${NOTES}/measure-${PHASE}.json`, JSON.stringify(out, null, 1));
const txt = out.map((r) => `${r.screen}@${r.width}: first content y=${r.firstContentTop} (“${r.firstContentText}”) usable bottom=${r.usableBottom} above fold=${r.firstContentAboveFold}; doc ${r.docH}px; main ${r.mainWidth}px @${r.mainLeft}; sizes ${r.distinctSizes} ${JSON.stringify(r.fontSizes)}; <12px ${r.under12}; tracked labels ${r.trackedLabels}; fonts ${r.fontFamilies.join('/')}`).join('\n');
writeFileSync(`${NOTES}/measure-${PHASE}.txt`, txt + '\n');
console.log(txt);
