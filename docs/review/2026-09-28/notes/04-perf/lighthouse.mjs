// Lighthouse mobile (default simulated throttling), median of 3, against the prod bundle
// on :4340 signed in as Alice (storage state from browser.mjs). Only runs a measurement
// while the 1-minute load average is under 4 (waits up to WAIT_MIN minutes per run).
//   node lighthouse.mjs  (env: STATE, LH = <scratch>/tools/lighthouse, WAIT_MIN)
import { chromium } from '/Users/craigrobinson/the-coupon/apps/web/node_modules/@playwright/test/index.mjs';
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { loadavg, tmpdir } from 'node:os';
import { execSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(process.env.LH, 'node_modules', 'x.js'));
const lighthouse = (await import(require.resolve('lighthouse'))).default;
const lhVersion = JSON.parse(readFileSync(join(process.env.LH, 'node_modules/lighthouse/package.json'))).version;
const WEB = 'http://127.0.0.1:4340';
const state = JSON.parse(readFileSync(process.env.STATE, 'utf8'));
const waitMin = Number(process.env.WAIT_MIN || 20);
const PORT = 9333;

const ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'lh-')), {
  headless: true, args: [`--remote-debugging-port=${PORT}`],
});
const keeper = await ctx.newPage();
async function signIn() {
  await keeper.goto(`${WEB}/offline`);
  await keeper.evaluate((items) => { for (const { name, value } of items) localStorage.setItem(name, value); },
    state.origins[0].localStorage);
}
await signIn();

async function quiet() {
  const t0 = Date.now();
  while (loadavg()[0] >= 4) {
    if (Date.now() - t0 > waitMin * 60000) return true; // lead, 30 Sep: take it anyway, load recorded
    await new Promise((r) => setTimeout(r, 15000));
  }
  return true;
}
const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
const pages = [['home', '/'], ['current_round', '/leagues/the-coupon/predictions'],
  ['standings', '/leagues/the-coupon/leaderboard'], ['login', '/login']];
const out = { lighthouse: lhVersion, chromium: ctx.browser()?.version?.() ?? 'playwright chromium-1223', pages: {} };
for (const [name, path] of pages) {
  const runs = [];
  for (let i = 0; i < 3; i += 1) {
    if (!(await quiet())) { runs.push({ skipped: 'load stayed >= 4', uptime: execSync('uptime').toString().trim() }); continue; }
    if (name !== 'login') await signIn();
    const uptime = execSync('uptime').toString().trim();
    const result = await lighthouse(`${WEB}${path}`, {
      port: PORT, output: 'json', logLevel: 'error', onlyCategories: ['performance'],
      disableStorageReset: name !== 'login',
    });
    const a = result.lhr.audits;
    const breakdown = (a['mainthread-work-breakdown']?.details?.items || [])
      .map((x) => [x.group, Math.round(x.duration)]).slice(0, 4);
    runs.push({
      uptime, final_url: result.lhr.finalDisplayedUrl,
      score: Math.round(result.lhr.categories.performance.score * 100),
      tbt_ms: Math.round(a['total-blocking-time'].numericValue),
      lcp_ms: Math.round(a['largest-contentful-paint'].numericValue),
      fcp_ms: Math.round(a['first-contentful-paint'].numericValue),
      si_ms: Math.round(a['speed-index'].numericValue),
      cls: Math.round(a['cumulative-layout-shift'].numericValue * 1000) / 1000,
      mainthread: breakdown,
    });
  }
  const ok = runs.filter((r) => r.score !== undefined);
  out.pages[name] = { path, runs, median_score: ok.length ? median(ok.map((r) => r.score)) : null,
    median_tbt_ms: ok.length ? median(ok.map((r) => r.tbt_ms)) : null,
    median_lcp_ms: ok.length ? median(ok.map((r) => r.lcp_ms)) : null };
  writeFileSync(join(here, 'lighthouse.json'), JSON.stringify(out, null, 1));
  console.log(name, JSON.stringify({ median_score: out.pages[name].median_score,
    median_tbt_ms: out.pages[name].median_tbt_ms, median_lcp_ms: out.pages[name].median_lcp_ms,
    finals: runs.map((r) => r.final_url || r.skipped), uptimes: runs.map((r) => r.uptime?.split('averages: ')[1]) }));
}
await ctx.close();
