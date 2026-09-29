// Part 2.3 — PICKS_BUSY driven for real: exhaust the-coupon's shared pick budget
// (PICK_SUBMIT_SHARED_LIMIT = 50/hour;100/day, in-memory) with real submissions by Jo, Kai
// and Lee (each alternating between two free selections; PICK_SUBMIT_LIMIT is 10/hour per
// member), stop at the first 429 PICKS_BUSY, then let Ivan tap a free selection in the
// browser at 390/1280 x light/dark and capture what he is shown. Nothing is mocked.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, api, sha256, contrast, WEB, API, NOTES, SHOTS } from './lib.mjs';

const rgb = (c) => (c || '').match(/[\d.]+/g)?.slice(0, 3).map(Number);
const ratio = (a, b) => (rgb(a) && rgb(b) ? Number(contrast(rgb(a), rgb(b)).toFixed(2)) : null);
const lines = [];
const log = (s) => { console.log(s); lines.push(s); };
const slate = async () => (await api('/api/v1/leagues/the-coupon/gameweek/current', { persona: 'Ivan' })).json;
const all = (s) => s.fixtures.flatMap((f) => f.selections.map((x) => ({ ...x, fixture_id: f.fixture_id, home: f.home, competition: f.competition })));
const pickAs = (persona, s) =>
  api('/api/v1/leagues/the-coupon/picks', { persona, method: 'POST', body: { fixture_id: s.fixture_id, market: s.market, outcome: s.outcome, odds: s.odds } });

let s = all(await slate());
const free = s.filter((x) => !x.taken_by_player_id);
log(`free at start: ${free.map((x) => `${x.home}/${x.runner_name}`).join(', ')}`);
const pairs = { Jo: [free[0], free[1]], Kai: [free[2], free[3]], Lee: [free[4], free[5]] };
let busyAt = null;
let n = 0;
outer: for (let round = 0; round < 10; round += 1) {
  for (const who of ['Jo', 'Kai', 'Lee']) {
    const target = pairs[who][round % 2];
    const r = await pickAs(who, target);
    n += 1;
    log(`#${n} ${who} -> ${target.home}/${target.runner_name}: ${r.status} ${typeof r.json === 'object' ? JSON.stringify(r.json.detail ?? r.json.runner_name ?? '') : String(r.json).slice(0, 80)}`);
    if (r.status === 429 && r.json && r.json.detail === 'PICKS_BUSY') { busyAt = n; break outer; }
  }
}
log(`PICKS_BUSY first returned at submission #${busyAt} of this script`);

s = all(await slate());
const target = s.find((x) => !x.taken_by_player_id && !x.mine);
log(`Ivan will tap ${target.home}/${target.runner_name}`);
const testid = `selection-${target.fixture_id}-${target.market}-${target.outcome}`;
const browser = await chromium.launch();
const out = [];
for (const [width, theme] of [[390, 'light'], [390, 'dark'], [1280, 'light'], [1280, 'dark']]) {
  const ctx = await newContext(browser, { width, theme, persona: 'Ivan' });
  const page = await ctx.newPage();
  const responses = [];
  page.on('response', async (r) => {
    if (r.url() === `${API}/api/v1/leagues/the-coupon/picks` && r.request().method() === 'POST') responses.push(`${r.status()} ${(await r.text().catch(() => '')).slice(0, 80)}`);
  });
  await page.goto(`${WEB}/leagues/the-coupon/predictions`);
  await settle(page);
  const btn = page.locator(`[data-testid="${testid}"]`);
  if (!(await btn.isVisible())) await page.locator('button[aria-expanded="false"]', { hasText: target.competition }).first().click();
  await btn.scrollIntoViewIfNeeded();
  await btn.click();
  await page.waitForSelector('[data-sonner-toast]', { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(900);
  const m = await page.evaluate(() => {
    const t = document.querySelector('[data-sonner-toast]');
    if (!t) return null;
    const tr = t.getBoundingClientRect();
    const bar = document.querySelector('nav[aria-label="Primary"]');
    const br = bar && getComputedStyle(bar).display !== 'none' ? bar.getBoundingClientRect() : null;
    return {
      title: t.querySelector('[data-title]')?.textContent.trim(), type: t.getAttribute('data-type'),
      action: t.querySelector('[data-button]')?.textContent.trim() ?? null,
      bg: getComputedStyle(t).backgroundColor, titleColor: getComputedStyle(t.querySelector('[data-title]')).color,
      gapToTabBar: br && br.height > 0 ? Math.round(br.top - tr.bottom) : null,
    };
  });
  const name = `current-round--feedback-busy--${width}--${theme}.png`;
  await page.screenshot({ path: `${SHOTS}/${name}` });
  const rec = { width, theme, file: name, sha256: sha256(`${SHOTS}/${name}`), responses, toast: m, titleContrast: m ? ratio(m.titleColor, m.bg) : null };
  out.push(rec);
  log(`${name}: http=${JSON.stringify(responses)} toast=${JSON.stringify(m?.title)} type=${m?.type} action=${m?.action} contrast=${rec.titleContrast} gap=${m?.gapToTabBar}`);
  await ctx.close();
}
await browser.close();
writeFileSync(`${NOTES}/busy-results.json`, JSON.stringify({ busyAt, out }, null, 1));
writeFileSync(`${NOTES}/busy-run.txt`, lines.join('\n') + '\n');
