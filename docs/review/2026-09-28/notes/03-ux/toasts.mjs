// Toasts against the tab bar (Batch 149) + the four pick-feedback states + UX-17 live regions.
// At 390 and 1280 × light and dark, on the-coupon's OPEN round:
//   confirm      real POST by Carol (free selection) -> success toast
//   conflict     real: page loaded, then Bob takes the same selection over the API, then the
//                member taps it -> 409 SELECTION_TAKEN (Alice taps; Bob re-picks each time)
//   pricemoved   POST fulfilled 409 {"detail":"PRICE_MOVED:9.99"} (the API's exact shape; mocked)
//   busy         POST fulfilled 429 {"detail":"PICKS_BUSY"} (mocked)
//   error        POST fulfilled 500 (mocked) -> error toast
// For each: screenshot (corpus), toast rect vs tab-bar rect, which live region carries the text.
// Also once at 390 with a simulated 34px safe-area inset (--safe-bottom overridden on :root,
// which is what env(safe-area-inset-bottom) feeds) to check the toast still clears the bar.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, api, WEB, API, NOTES, SHOTS } from './lib.mjs';

const out = [];
const lines = [];
const browser = await chromium.launch();
const slate = (await api('/api/v1/leagues/the-coupon/gameweek/current', { persona: 'Carol' })).json;
const sels = slate.fixtures.flatMap((f) => f.selections.map((s) => ({ ...s, fixture_id: f.fixture_id })));
const testid = (s) => `selection-${s.fixture_id}-${s.market}-${s.outcome}`;
const bobPick = (s) => api('/api/v1/leagues/the-coupon/picks', { persona: 'Bob', method: 'POST', body: { fixture_id: s.fixture_id, market: s.market, outcome: s.outcome, odds: s.odds } });

// Bob holds one selection throughout the confirm/mocked runs, so "taken by" rows exist.
const bobHold = sels[0];
lines.push(`bob holds ${bobHold.runner_name}: ${JSON.stringify((await bobPick(bobHold)).status)}`);

async function measure(page) {
  return page.evaluate(() => {
    const t = document.querySelector('[data-sonner-toast]');
    const bar = document.querySelector('nav[aria-label="Primary"]');
    const tr = t?.getBoundingClientRect();
    const br = bar && getComputedStyle(bar).display !== 'none' ? bar.getBoundingClientRect() : null;
    const barTop = br && br.height > 0 ? br.top : null;
    return {
      toast: t ? { text: t.textContent.trim().slice(0, 120), type: t.getAttribute('data-type'), top: Math.round(tr.top), bottom: Math.round(tr.bottom), left: Math.round(tr.left), right: Math.round(tr.right) } : null,
      tabBarTop: barTop == null ? null : Math.round(barTop),
      gap: t && barTop != null ? Math.round(barTop - tr.bottom) : null,
      viewportBottomGap: t ? Math.round(innerHeight - tr.bottom) : null,
      alertRegion: document.querySelector('[data-testid="toast-alerts"]')?.textContent.trim().slice(0, 120) ?? null,
      statusRegion: document.querySelector('[data-testid="toast-status"]')?.textContent.trim().slice(0, 120) ?? null,
      sonnerLive: document.querySelector('section[aria-live], [data-sonner-toaster]')?.closest('section')?.getAttribute('aria-live') ?? null,
    };
  });
}

async function run({ state, width, theme, persona, target, mock = null, beforeTap = null, safe = false }) {
  const ctx = await newContext(browser, { width, theme, persona });
  const page = await ctx.newPage();
  if (mock) await page.route((u) => u.href === `${API}/api/v1/leagues/the-coupon/picks`, (r) => (r.request().method() === 'POST' ? r.fulfill(mock) : r.continue()));
  await page.goto(`${WEB}/leagues/the-coupon/predictions`);
  await settle(page);
  if (safe) await page.addStyleTag({ content: ':root{--safe-bottom:34px !important}' });
  if (beforeTap) await beforeTap();
  const btn = page.locator(`[data-testid="${testid(target)}"]`);
  await btn.scrollIntoViewIfNeeded();
  await btn.click();
  await page.waitForSelector('[data-sonner-toast]', { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(700);
  const m = await measure(page);
  const name = `current-round--${state}${safe ? '-safearea34' : ''}--${width}--${theme}.png`;
  await page.screenshot({ path: `${SHOTS}/${name}` });
  out.push({ state, width, theme, persona, safe, file: name, ...m });
  lines.push(`${name}: toast=${JSON.stringify(m.toast?.text)} type=${m.toast?.type} gapToTabBar=${m.gap} bottomGap=${m.viewportBottomGap} alert="${m.alertRegion ?? ''}" status="${m.statusRegion ?? ''}"`);
  await ctx.close();
}

const free = sels.filter((s) => s !== bobHold);
for (const width of [390, 1280]) {
  for (const theme of ['light', 'dark']) {
    // confirm: Carol alternates between two free selections so each tap is a real change
    await run({ state: 'pick-confirm', width, theme, persona: 'Carol', target: free[(width + (theme === 'dark' ? 1 : 0)) % 2] });
    // conflict: Alice's page is loaded, then Bob grabs the selection she is about to tap
    const victim = free[2 + (theme === 'dark' ? 1 : 0)] ?? free[2];
    await run({ state: 'pick-conflict', width, theme, persona: 'Alice', target: victim,
      beforeTap: async () => lines.push(`  bob grabs ${victim.runner_name}: ${(await bobPick(victim)).status}`) });
    await run({ state: 'pick-pricemoved', width, theme, persona: 'Alice', target: free[4] ?? free[0],
      mock: { status: 409, contentType: 'application/json', body: '{"detail":"PRICE_MOVED:9.99"}' } });
    await run({ state: 'pick-busy', width, theme, persona: 'Alice', target: free[4] ?? free[0],
      mock: { status: 429, contentType: 'application/json', body: '{"detail":"PICKS_BUSY"}' } });
    await run({ state: 'toast-error', width, theme, persona: 'Alice', target: free[4] ?? free[0],
      mock: { status: 500, contentType: 'application/json', body: '{"detail":"Internal Server Error"}' } });
  }
}
await run({ state: 'toast-error', width: 390, theme: 'dark', persona: 'Alice', target: free[4] ?? free[0], safe: true,
  mock: { status: 500, contentType: 'application/json', body: '{"detail":"Internal Server Error"}' } });
// Bob back onto his original selection so later captures show a stable "taken by Bob"
lines.push(`bob back to ${bobHold.runner_name}: ${(await bobPick(bobHold)).status}`);
writeFileSync(`${NOTES}/toasts.json`, JSON.stringify(out, null, 1));
writeFileSync(`${NOTES}/toasts.txt`, lines.join('\n') + '\n');
console.log(lines.join('\n'));
await browser.close();
