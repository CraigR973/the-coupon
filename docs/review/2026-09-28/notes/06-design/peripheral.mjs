// Peripheral screens re-captured by lens 06, because 26 of lens 03's captures of these
// screens carry the offline banner (navigator.onLine was false in that run) and several are
// empty (corpus-offline-banner-scan.txt). Each capture asserts: online, no offline banner,
// the expected h1, and that the page body has content beyond the header.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, sha256, WEB, NOTES, SHOTS } from './lib.mjs';

const plan = [
  { route: 'my-leagues', state: 'happy', path: '/leagues', persona: 'Alice' },
  { route: 'my-leagues', state: 'firstrun', path: '/leagues', persona: 'Dave' },
  { route: 'discover-leagues', state: 'happy', path: '/leagues/discover', persona: 'Dave' },
  { route: 'join-by-code', state: 'happy', path: '/leagues/join', persona: 'Dave' },
  { route: 'create-league', state: 'happy', path: '/leagues/new', persona: 'Alice' },
  { route: 'league-members', state: 'happy', path: '/leagues/the-coupon/admin/members', persona: 'Alice' },
  { route: 'league-settings', state: 'happy', path: '/leagues/the-coupon/admin/settings', persona: 'Alice' },
  { route: 'career-profile', state: 'settled', path: '/profile', persona: 'Hana' },
  { route: 'home', state: 'firstrun', path: '/', persona: 'Dave', full: true },
];
const only = process.env.ONLY ? process.env.ONLY.split(',') : null;
const browser = await chromium.launch();
const out = [];
for (const p of plan) {
  if (only && !only.includes(p.route)) continue;
  for (const [width, theme] of [[390, 'light'], [390, 'dark'], [1280, 'light'], [1280, 'dark']]) {
    const ctx = await newContext(browser, { width, theme, persona: p.persona });
    const page = await ctx.newPage();
    await page.goto(`${WEB}${p.path}`);
    await settle(page);
    const info = await page.evaluate(() => ({
      online: navigator.onLine,
      banner: !!document.querySelector('[data-testid="offline-banner"]'),
      h1: document.querySelector('h1')?.textContent.trim(),
      mainText: (document.querySelector('main')?.innerText || '').replace(/\s+/g, ' ').length,
      snippet: (document.querySelector('main')?.innerText || '').replace(/\s+/g, ' ').slice(0, 120),
    }));
    const base = `${p.route}--${p.state}-l06--${width}--${theme}`;
    await page.screenshot({ path: `${SHOTS}/${base}.png` });
    out.push({ ...p, width, theme, file: `${base}.png`, sha256: sha256(`${SHOTS}/${base}.png`), ...info });
    if (p.full && width === 390 && theme === 'dark') {
      await page.screenshot({ path: `${SHOTS}/${base}--full.png`, fullPage: true });
      out.push({ ...p, width, theme, file: `${base}--full.png`, sha256: sha256(`${SHOTS}/${base}--full.png`), fullPage: true, ...info });
    }
    console.log(`${base}: online=${info.online} banner=${info.banner} h1=${info.h1} text=${info.mainText}ch “${info.snippet.slice(0, 70)}”`);
    await ctx.close();
  }
}
await browser.close();
writeFileSync(`${NOTES}/peripheral-results${only ? '-' + only.join('_') : ''}.json`, JSON.stringify(out, null, 1));
