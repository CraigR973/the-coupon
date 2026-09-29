// The offline pick queue, driven with Chromium's offline emulation, on sunday-club's round
// (reopened in place for this: `UPDATE gameweeks SET status='open', locks_at_utc = now()+2 days`
// on the scratch DB — see progress.md). Alice holds Arsenal (fixture scope), so each run taps the
// other free selection in that fixture. Also measures the UX-19 targets.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, api, WEB, NOTES, SHOTS } from './lib.mjs';

const lines = [];
const browser = await chromium.launch();
for (const [width, theme] of [[390, 'light'], [390, 'dark'], [1280, 'light'], [1280, 'dark']]) {
  const slate = (await api('/api/v1/leagues/sunday-club/gameweek/current', { persona: 'Alice' })).json;
  const f = slate.fixtures.find((x) => x.home === 'Arsenal');
  const target = f.selections.find((s) => s.market === 'MATCH_ODDS' && !s.mine && !s.taken_by_player_id);
  const ctx = await newContext(browser, { width, theme, persona: 'Alice' });
  const page = await ctx.newPage();
  try {
    await page.goto(`${WEB}/leagues/sunday-club/predictions`);
    await settle(page);
    await ctx.setOffline(true);
    await page.evaluate(() => window.dispatchEvent(new Event('offline')));
    await page.waitForTimeout(500);
    const btn = page.locator(`[data-testid="selection-${f.fixture_id}-MATCH_ODDS-${target.outcome}"]`);
    await btn.scrollIntoViewIfNeeded();
    await btn.click();
    await page.waitForTimeout(1200);
    const q = await page.evaluate(() => ({
      toast: [...document.querySelectorAll('[data-sonner-toast]')].map((t) => t.textContent.trim()).join(' / '),
      marker: /waiting to send/i.test(document.body.innerText),
      banner: /offline/i.test(document.querySelector('main')?.previousElementSibling?.textContent ?? document.body.innerText),
      status: document.querySelector('[data-testid="toast-status"]')?.textContent.trim(),
      alert: document.querySelector('[data-testid="toast-alerts"]')?.textContent.trim(),
    }));
    const name = `current-round--offline-queued--${width}--${theme}.png`;
    await page.screenshot({ path: `${SHOTS}/${name}` });
    await ctx.setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await page.waitForTimeout(3000);
    const after = await page.evaluate(() => ({
      toast: [...document.querySelectorAll('[data-sonner-toast]')].map((t) => t.textContent.trim()).join(' / '),
      marker: /waiting to send/i.test(document.body.innerText),
    }));
    const mine = (await api(`/api/v1/leagues/sunday-club/gameweeks/${slate.gameweek_id}/pick`, { persona: 'Alice' })).json;
    lines.push(`${name}: tapped ${target.runner_name} offline -> toast "${q.toast}", marker=${q.marker}, status="${q.status ?? ''}", alert="${q.alert ?? ''}" | back online -> toast "${after.toast}", marker=${after.marker}, API pick now ${mine?.runner_name}`);
  } catch (e) {
    lines.push(`FAILED ${width} ${theme}: ${String(e).slice(0, 160)}`);
  }
  await ctx.close();
}
// UX-19 targets, measured
for (const [path, re] of [['/login', /forgot pin/i], ['/settings', /about/i]]) {
  const ctx = await newContext(browser, { width: 390, theme: 'dark', persona: path === '/login' ? null : 'Alice' });
  const page = await ctx.newPage();
  await page.goto(`${WEB}${path}`);
  await settle(page);
  const m = await page.evaluate((src) => {
    const r = new RegExp(src, 'i');
    return [...document.querySelectorAll('a,button')].filter((e) => r.test(e.textContent)).map((e) => {
      const b = e.getBoundingClientRect();
      return `"${e.textContent.trim().slice(0, 30)}" ${Math.round(b.width)}×${Math.round(b.height)}`;
    });
  }, re.source);
  lines.push(`UX-19 ${path}: ${m.join('; ')}`);
  await ctx.close();
}
writeFileSync(`${NOTES}/offline.txt`, lines.join('\n') + '\n');
console.log(lines.join('\n'));
await browser.close();
