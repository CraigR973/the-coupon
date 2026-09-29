// UX-14 re-drive: focus indicator contrast measured from rendered pixels.
//
// For each page × width × theme, Tab through up to MAX stops. At every stop the
// focused element's box (+8px) is captured focused, then blurred and captured again
// at the same scroll position. Every pixel that changed is scored as the WCAG
// contrast ratio between its focused and unfocused colour (the "change of contrast"
// SC 2.4.13 measures, and the 3:1 SC 1.4.11 asks of a visual indicator against what
// it sits on). A stop PASSES when at least one element-perimeter's worth of pixels
// (2·(w+h)) changed by ≥3:1 — i.e. there is at least a 1-CSS-px ring at 3:1.
// deviceScaleFactor 1, reduced motion on (so transitions do not smear the capture).
//
//   node focus.mjs [--pages login,home,...] [--max 40]
import { writeFileSync, appendFileSync } from 'node:fs';
import { chromium, newContext, settle, sessions, WEB, NOTES, ensureDir } from './lib.mjs';

const argv = process.argv.slice(2);
const arg = (k, d) => {
  const i = argv.indexOf(`--${k}`);
  return i >= 0 ? argv[i + 1] : d;
};
const MAX = Number(arg('max', '40'));
const bob = sessions().Bob.player.id;
const PAGES = {
  login: { path: '/login', persona: null },
  home: { path: '/', persona: 'Alice' },
  round: { path: '/leagues/the-coupon/predictions', persona: 'Carol' },
  standings: { path: '/leagues/the-coupon/leaderboard', persona: 'Alice' },
  settings: { path: '/settings', persona: 'Alice' },
  'league-settings': { path: '/leagues/the-coupon/admin/settings', persona: 'Alice' },
  'admin-players': { path: '/admin/players', persona: 'Alice' },
  football: { path: '/football', persona: 'Alice' },
  player: { path: `/leagues/the-coupon/players/${bob}`, persona: 'Alice' },
};
const want = arg('pages', Object.keys(PAGES).join(',')).split(',');
const outDir = `${NOTES}/focus`;
ensureDir(outDir);
const tsv = `${outDir}/focus-summary.tsv`;
writeFileSync(tsv, 'page\twidth\ttheme\tstop\telement\tw×h\tchanged\tpx≥3\tperimeter\tp90\tmax\tverdict\n');

const browser = await chromium.launch();
const scorer = await (await browser.newContext()).newPage();
await scorer.setContent('<canvas id=c></canvas>');

async function score(focusedB64, blurredB64) {
  return scorer.evaluate(async ([a, b]) => {
    const load = (s) =>
      new Promise((res) => {
        const i = new Image();
        i.onload = () => res(i);
        i.src = 'data:image/png;base64,' + s;
      });
    const [ia, ib] = await Promise.all([load(a), load(b)]);
    const c = document.getElementById('c');
    c.width = ia.width;
    c.height = ia.height;
    const x = c.getContext('2d', { willReadFrequently: true });
    x.drawImage(ia, 0, 0);
    const da = x.getImageData(0, 0, c.width, c.height).data;
    x.clearRect(0, 0, c.width, c.height);
    x.drawImage(ib, 0, 0);
    const db = x.getImageData(0, 0, c.width, c.height).data;
    const lin = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    };
    const L = (d, i) => 0.2126 * lin(d[i]) + 0.7152 * lin(d[i + 1]) + 0.0722 * lin(d[i + 2]);
    const ratios = [];
    for (let i = 0; i < da.length; i += 4) {
      const diff = Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2]);
      if (diff < 24) continue;
      const [p, q] = [L(da, i), L(db, i)].sort((m, n) => n - m);
      ratios.push((p + 0.05) / (q + 0.05));
    }
    ratios.sort((m, n) => m - n);
    const pct = (f) => (ratios.length ? ratios[Math.min(ratios.length - 1, Math.floor(f * ratios.length))] : 0);
    return { changed: ratios.length, ge3: ratios.filter((r) => r >= 3).length, p90: pct(0.9), max: pct(1) };
  }, [focusedB64, blurredB64]);
}

const results = [];
for (const name of want) {
  const pg = PAGES[name];
  for (const width of [390, 1280]) {
    for (const theme of ['light', 'dark']) {
      const ctx = await newContext(browser, { width, theme, persona: pg.persona });
      const page = await ctx.newPage();
      await page.goto(`${WEB}${pg.path}`);
      await settle(page);
      await page.mouse.move(0, 0);
      const seen = new Set();
      for (let stop = 1; stop <= MAX; stop++) {
        await page.keyboard.press('Tab');
        await page.waitForTimeout(120);
        const info = await page.evaluate(() => {
          const el = document.activeElement;
          if (!el || el === document.body) return null;
          el.setAttribute('data-ux-focus', '1');
          const r = el.getBoundingClientRect();
          const label = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder') || '')
            .replace(/\s+/g, ' ').trim().slice(0, 40);
          return {
            key: el.tagName + '|' + label + '|' + Math.round(r.x) + ',' + Math.round(r.y + window.scrollY),
            desc: `${el.tagName.toLowerCase()}${el.getAttribute('role') ? '[' + el.getAttribute('role') + ']' : ''} "${label}"`,
            x: r.x, y: r.y, w: r.width, h: r.height,
            fv: el.matches(':focus-visible'),
            vw: window.innerWidth, vh: window.innerHeight,
          };
        });
        if (!info) continue;
        if (seen.has(info.key)) break; // wrapped round
        seen.add(info.key);
        if (info.w < 2 || info.h < 2 || info.y < 0 || info.y + info.h > info.vh) {
          results.push({ name, width, theme, stop, desc: info.desc, skipped: 'offscreen' });
          await page.evaluate(() => document.querySelector('[data-ux-focus]')?.removeAttribute('data-ux-focus'));
          continue;
        }
        const pad = 8;
        const clip = {
          x: Math.max(0, info.x - pad), y: Math.max(0, info.y - pad),
          width: Math.min(info.vw - Math.max(0, info.x - pad), info.w + 2 * pad),
          height: Math.min(info.vh - Math.max(0, info.y - pad), info.h + 2 * pad),
        };
        const focused = (await page.screenshot({ clip })).toString('base64');
        await page.evaluate(() => document.activeElement.blur());
        await page.waitForTimeout(120);
        const blurred = (await page.screenshot({ clip })).toString('base64');
        await page.evaluate(() => {
          const el = document.querySelector('[data-ux-focus]');
          el.removeAttribute('data-ux-focus');
          el.focus();
        });
        await page.waitForTimeout(60);
        const s = await score(focused, blurred);
        const perimeter = Math.round(2 * (info.w + info.h));
        const verdict = s.ge3 >= perimeter ? 'PASS' : s.changed === 0 ? 'NONE' : 'FAIL';
        const row = { name, width, theme, stop, desc: info.desc, fv: info.fv, wh: `${Math.round(info.w)}×${Math.round(info.h)}`, ...s, perimeter, verdict };
        results.push(row);
        appendFileSync(tsv, `${name}\t${width}\t${theme}\t${stop}\t${info.desc}\t${row.wh}\t${s.changed}\t${s.ge3}\t${perimeter}\t${s.p90.toFixed(2)}\t${s.max.toFixed(2)}\t${verdict}\n`);
        if (verdict !== 'PASS') await page.screenshot({ path: `${outDir}/${name}-${width}-${theme}-stop${stop}.png`, clip: { ...clip } }).catch(() => {});
      }
      await ctx.close();
      console.log(name, width, theme, 'done');
    }
  }
}
writeFileSync(`${outDir}/focus-results.json`, JSON.stringify(results, null, 1));
const tally = {};
for (const r of results) tally[r.verdict ?? 'skipped'] = (tally[r.verdict ?? 'skipped'] ?? 0) + 1;
console.log(JSON.stringify(tally));
await browser.close();
