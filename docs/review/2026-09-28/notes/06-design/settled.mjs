// Phase C captures: the genuinely settled round (settle_design.py) from three members' seats.
// Each capture's state is confirmed from the page text (not the file name): the round's
// status word, void/Former copy, and the coupon figure.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, api, sha256, WEB, NOTES, SHOTS } from './lib.mjs';

const round = (await api('/api/v1/leagues/the-coupon/gameweek/current', { persona: 'Alice' })).json;
console.log(`round status via API: ${round.status}, number ${round.number}, season_week ${round.season_week}`);
const plan = [
  { route: 'current-round', state: 'settled-winner', path: '/leagues/the-coupon/predictions', persona: 'Alice', full: true },
  { route: 'current-round', state: 'settled-void-leg', path: '/leagues/the-coupon/predictions', persona: 'Ivan', full: false },
  { route: 'coupon', state: 'settled-void', path: '/leagues/the-coupon/predictions/coupon', persona: 'Alice', full: true },
  { route: 'results', state: 'settled', path: '/leagues/the-coupon/predictions/results', persona: 'Alice', full: false },
  { route: 'standings', state: 'settled-8-members', path: '/leagues/the-coupon/leaderboard', persona: 'Alice', full: true },
  { route: 'home', state: 'after-settle-loser', path: '/', persona: 'Bob', full: false },
];
const browser = await chromium.launch();
const out = [];
for (const p of plan) {
  for (const [width, theme] of [[390, 'light'], [390, 'dark'], [1280, 'light'], [1280, 'dark']]) {
    const ctx = await newContext(browser, { width, theme, persona: p.persona });
    const page = await ctx.newPage();
    await page.goto(`${WEB}${p.path}`);
    await settle(page);
    const info = await page.evaluate(() => {
      const t = document.querySelector('main')?.innerText ?? '';
      return {
        h1: document.querySelector('h1')?.textContent.trim(),
        settledWord: /settled/i.test(t), voidWord: (t.match(/void/gi) || []).length,
        former: (t.match(/Former( member)?/g) || []),
        snippet: t.replace(/\s+/g, ' ').slice(0, 160),
      };
    });
    const base = `${p.route}--${p.state}--${width}--${theme}`;
    await page.screenshot({ path: `${SHOTS}/${base}.png` });
    const rec = { ...p, width, theme, file: `${base}.png`, sha256: sha256(`${SHOTS}/${base}.png`), ...info };
    out.push(rec);
    if (p.full && ((width === 390 && theme === 'dark') || (width === 1280 && theme === 'light'))) {
      await page.screenshot({ path: `${SHOTS}/${base}--full.png`, fullPage: true });
      out.push({ ...rec, file: `${base}--full.png`, sha256: sha256(`${SHOTS}/${base}--full.png`), fullPage: true });
    }
    console.log(`${base}: h1=${info.h1} settled=${info.settledWord} void×${info.voidWord} former=${JSON.stringify(info.former)}`);
    await ctx.close();
  }
}
await browser.close();
writeFileSync(`${NOTES}/settled-results.json`, JSON.stringify({ round: { status: round.status, number: round.number }, out }, null, 1));
