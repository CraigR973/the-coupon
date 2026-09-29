// Load-independent web facts in real Chromium against the prod bundle on :4340 / API :8140.
//   node browser.mjs [idleSeconds]   -> browser.json beside this file
// Cold /login (service worker blocked), sign-in once (storage state reused), home, the
// round screen and standings: requests, raw and gzip bytes, API calls; idle requests;
// React commits per idle 5 s via a stub DevTools hook (works on production React).
import { chromium } from '/Users/craigrobinson/the-coupon/apps/web/node_modules/@playwright/test/index.mjs';
import { writeFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const WEB = 'http://127.0.0.1:4340';
const API = ':8140';
const idle = Number(process.argv[2] || 60);
const out = {};
const state = process.env.STATE;
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });

const HOOK = `
  window.__commits = 0; window.__rendered = 0;
  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true, renderers: new Map(), isDisabled: false,
    inject(r) { const id = this.renderers.size + 1; this.renderers.set(id, r); return id; },
    onScheduleFiberRoot() {}, onCommitFiberUnmount() {}, onPostCommitFiberRoot() {},
    onCommitFiberRoot(id, root) {
      // A component rendered in this commit iff its fiber was cloned for this render (not
      // the same object as in the previous commit's tree) AND it carries PerformedWork.
      // Fibers in a skipped subtree are reused objects with stale flags, so they are excluded.
      window.__commits += 1;
      const prev = window.__prevFibers || new WeakSet(); const next = new WeakSet();
      const stack = [root.current]; let n = 0;
      while (stack.length) { const f = stack.pop(); if (!f) continue; next.add(f);
        if ((f.flags & 1) && typeof f.type === 'function' && !prev.has(f)) n += 1;
        if (f.child) stack.push(f.child); if (f.sibling) stack.push(f.sibling); }
      window.__prevFibers = next;
      window.__rendered += n;
    },
  };`;

function tracker(page) {
  const rows = [];
  page.on('response', async (res) => {
    try {
      const body = await res.body();
      rows.push({ url: res.url(), status: res.status(), raw: body.length, gz: gzipSync(body).length });
    } catch { rows.push({ url: res.url(), status: res.status(), raw: 0, gz: 0 }); }
  });
  return rows;
}
const summarise = (rows) => {
  const api = rows.filter((r) => r.url.includes(API));
  const kb = (n) => Math.round(n / 102.4) / 10;
  return {
    requests: rows.length, raw_kib: kb(rows.reduce((a, r) => a + r.raw, 0)),
    gzip_kib: kb(rows.reduce((a, r) => a + r.gz, 0)),
    api_calls: api.length, api_raw_kib: kb(api.reduce((a, r) => a + r.raw, 0)),
    api_paths: api.map((r) => new URL(r.url).pathname + new URL(r.url).search),
    fonts: rows.filter((r) => r.url.endsWith('.woff2')).map((r) => r.url.split('/').pop()),
  };
};

// 1. Cold /login, no service worker, empty cache.
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, serviceWorkers: 'block' });
  const page = await ctx.newPage();
  const rows = tracker(page);
  await page.goto(`${WEB}/login`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  out.cold_login = summarise(rows);
  // Sign in once and keep the storage state.
  await page.locator('input').first().fill('Alice');
  const pins = page.locator('input[inputmode="numeric"], input[type="password"]');
  for (let i = 0; i < 4; i += 1) await pins.nth(i).fill('1234'[i]);
  rows.length = 0;
  await page.keyboard.press('Enter');
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  out.login_to_home = { ...summarise(rows), landed: new URL(page.url()).pathname };
  await ctx.storageState({ path: state });
  await ctx.close();
}

// 2. Each screen, warm sign-in, service worker still blocked so counts are the page's own.
for (const [name, path] of [['home', '/'], ['current_round', '/leagues/the-coupon/predictions'],
  ['standings', '/leagues/the-coupon/leaderboard']]) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block', storageState: state });
  await ctx.addInitScript(HOOK);
  const page = await ctx.newPage();
  const rows = tracker(page);
  await page.goto(`${WEB}${path}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  const loaded = summarise(rows);
  // Idle: React commits per 5 s (three samples), then requests over `idle` seconds.
  const samples = [];
  for (let i = 0; i < 3; i += 1) {
    const before = await page.evaluate(() => [window.__commits, window.__rendered]);
    await page.waitForTimeout(5000);
    const after = await page.evaluate(() => [window.__commits, window.__rendered]);
    samples.push({ commits: after[0] - before[0], components_rendered: after[1] - before[1] });
  }
  rows.length = 0;
  await page.waitForTimeout(idle * 1000);
  out[name] = { path, landed: new URL(page.url()).pathname, ...loaded, idle_5s: samples,
    idle_requests: rows.length, idle_seconds: idle };
  await ctx.close();
}

// 3. What the service worker precaches after a first visit.
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, storageState: state });
  const page = await ctx.newPage();
  const swRows = [];
  ctx.on('request', (r) => { if (r.serviceWorker()) swRows.push(r.url()); });
  await page.goto(`${WEB}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(8000);
  const cached = await page.evaluate(async () => {
    const names = await caches.keys(); const out = {};
    for (const n of names) out[n] = (await (await caches.open(n)).keys()).length;
    return out;
  });
  out.service_worker = { requests_from_sw: swRows.length, caches: cached,
    admin_chunks_fetched: swRows.filter((u) => /Admin|LeagueMembersPage|LeagueSettingsPage|LeagueAuditLog/.test(u)).length };
  await ctx.close();
}
await browser.close();
writeFileSync(join(here, 'browser.json'), JSON.stringify(out, null, 1));
for (const [k, v] of Object.entries(out)) {
  console.log(k, JSON.stringify({ ...v, api_paths: v.api_paths ? v.api_paths.length : undefined }));
}
