// Verify why an offline tap gives no feedback: count POSTs while offline, wait 8s for any toast.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, api, WEB, NOTES } from './lib.mjs';
const b = await chromium.launch();
const slate = (await api('/api/v1/leagues/sunday-club/gameweek/current', { persona: 'Alice' })).json;
const f = slate.fixtures.find((x) => x.home === 'Arsenal');
const t = f.selections.find((s) => s.market === 'MATCH_ODDS' && !s.mine && !s.taken_by_player_id);
const ctx = await newContext(b, { width: 390, theme: 'dark', persona: 'Alice' });
const p = await ctx.newPage();
const posts = [];
p.on('request', (r) => { if (r.method() === 'POST' && r.url().includes('/picks')) posts.push({ at: Date.now(), failed: false }); });
p.on('requestfailed', (r) => { if (r.url().includes('/picks')) posts.push({ failed: r.failure()?.errorText }); });
await p.goto(`${WEB}/leagues/sunday-club/predictions`); await settle(p);
await ctx.setOffline(true);
const t0 = Date.now();
await p.locator(`[data-testid="selection-${f.fixture_id}-MATCH_ODDS-${t.outcome}"]`).click();
await p.waitForTimeout(8000);
const offline = await p.evaluate(() => ({
  onLine: navigator.onLine,
  toasts: [...document.querySelectorAll('[data-sonner-toast]')].map((x) => x.textContent.trim()),
  spinner: !!document.querySelector('[data-testid^="selection-"] .animate-spin'),
  enabledSelections: [...document.querySelectorAll('[data-testid^="selection-"]')].filter((x) => !x.disabled).length,
  notice: /waiting to send|send now|not sent/i.test(document.body.innerText),
}));
const postsWhileOffline = posts.length;
await ctx.setOffline(false);
await p.waitForTimeout(3000);
const after = await p.evaluate(() => [...document.querySelectorAll('[data-sonner-toast]')].map((x) => x.textContent.trim()));
const line = `tapped ${t.runner_name} offline; after 8s: ${JSON.stringify(offline)}; POSTs attempted while offline: ${postsWhileOffline}; after reconnect: POSTs ${posts.length}, toasts ${JSON.stringify(after)}`;
writeFileSync(`${NOTES}/offline-verify.txt`, line + '\n');
console.log(line);
await b.close();
