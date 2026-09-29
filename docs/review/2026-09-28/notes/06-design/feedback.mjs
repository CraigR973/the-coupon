// Part 2.3 — the pick-feedback states, driven for real against the lens 06 stack.
//   feedback-confirmed      Carol taps a free selection -> 201 -> success toast
//   feedback-conflict       Alice's card is loaded, then Bob claims the same selection over the
//                           API, then Alice taps it -> 409 SELECTION_TAKEN -> warning + action
//   feedback-price-moved    Hana's card is loaded, then the fake provider's price is moved
//                           (POST /__review/move-price), then Hana taps -> 409 PRICE_MOVED:<new>
//   feedback-queued-offline Ivan's card is loaded, the context goes offline, Ivan taps ->
//                           NetworkError(mayHaveLanded=false) -> info toast + outstanding notice
// No request is mocked. Each capture records the toast's text, type, action label and its
// rectangle against the tab bar, then the PNG's sha256.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, api, sha256, contrast, WEB, API, NOTES, SHOTS } from './lib.mjs';
const rgb = (c) => (c || '').match(/[\d.]+/g)?.slice(0, 3).map(Number);
const ratio = (a, b) => (rgb(a) && rgb(b) ? Number(contrast(rgb(a), rgb(b)).toFixed(2)) : null);

const only = process.env.ONLY ? process.env.ONLY.split(',') : null;
const combos = (process.env.COMBOS || '390:light,390:dark,1280:light,1280:dark').split(',').map((c) => {
  const [w, t] = c.split(':');
  return { width: Number(w), theme: t };
});
const out = [];
const log = (s) => { console.log(s); out.push({ log: s }); };
const browser = await chromium.launch();
const slate = (await api('/api/v1/leagues/the-coupon/gameweek/current', { persona: 'Carol' })).json;
const sel = {};
for (const f of slate.fixtures) for (const s of f.selections) sel[`${f.home}|${s.market}|${s.outcome}`] = { ...s, fixture_id: f.fixture_id, competition: f.competition };
const S = {
  sl2Draw: sel['Forfar Athletic|MATCH_ODDS|DRAW'],
  sl2Yes: sel['Forfar Athletic|BOTH_TEAMS_TO_SCORE|YES'],
  eplDraw: sel['Arsenal|MATCH_ODDS|DRAW'],
  brechin: sel['Forfar Athletic|MATCH_ODDS|AWAY'],
  chelsea: sel['Arsenal|MATCH_ODDS|AWAY'],
  forfar: sel['Forfar Athletic|MATCH_ODDS|HOME'],
  eplYes: sel['Arsenal|BOTH_TEAMS_TO_SCORE|YES'],
};
const testid = (s) => `selection-${s.fixture_id}-${s.market}-${s.outcome}`;
const pickAs = (persona, s, odds = s.odds) =>
  api('/api/v1/leagues/the-coupon/picks', { persona, method: 'POST', body: { fixture_id: s.fixture_id, market: s.market, outcome: s.outcome, odds } });
async function movePrice(price) {
  const r = await fetch(`${API}/__review/move-price?market_id=1.100000001&selection_id=1002&price=${price}`, { method: 'POST' });
  return `${r.status} ${await r.text()}`;
}

async function measure(page) {
  return page.evaluate(() => {
    const t = document.querySelector('[data-sonner-toast]');
    const bar = document.querySelector('nav[aria-label="Primary"]');
    const tr = t?.getBoundingClientRect();
    const br = bar && getComputedStyle(bar).display !== 'none' ? bar.getBoundingClientRect() : null;
    const barTop = br && br.height > 0 ? br.top : null;
    const btn = t?.querySelector('[data-button]');
    const icon = t?.querySelector('[data-icon]');
    const cs = t ? getComputedStyle(t) : null;
    return {
      toast: t
        ? {
            title: t.querySelector('[data-title]')?.textContent.trim(),
            type: t.getAttribute('data-type'),
            action: btn?.textContent.trim() ?? null,
            rect: [Math.round(tr.left), Math.round(tr.top), Math.round(tr.width), Math.round(tr.height)],
            bg: cs.backgroundColor, border: cs.borderColor, color: cs.color,
            titleColor: getComputedStyle(t.querySelector('[data-title]')).color,
            iconColor: icon ? getComputedStyle(icon).color : null,
            actionBg: btn ? getComputedStyle(btn).backgroundColor : null,
            actionColor: btn ? getComputedStyle(btn).color : null,
          }
        : null,
      tabBarTop: barTop == null ? null : Math.round(barTop),
      gapToTabBar: t && barTop != null ? Math.round(barTop - tr.bottom) : null,
      outstanding: document.querySelector('[data-testid="outstanding-pick-notice"]')?.textContent.trim().slice(0, 200) ?? null,
      offlineBanner: [...document.querySelectorAll('[role="status"],[role="alert"]')].map((e) => e.textContent.trim()).filter((x) => /offline/i.test(x)).slice(0, 2),
    };
  });
}

async function run({ state, width, theme, persona, target, beforeTap = null, offline = false }) {
  if (only && !only.includes(state)) return;
  const ctx = await newContext(browser, { width, theme, persona });
  const page = await ctx.newPage();
  const responses = [];
  page.on('response', async (r) => {
    if (r.url() === `${API}/api/v1/leagues/the-coupon/picks` && r.request().method() === 'POST') {
      responses.push(`${r.status()} ${(await r.text().catch(() => '')).slice(0, 120)}`);
    }
  });
  await page.goto(`${WEB}/leagues/the-coupon/predictions`);
  await settle(page);
  if (beforeTap) log(`  before tap: ${await beforeTap()}`);
  if (offline) { await ctx.setOffline(true); await page.waitForTimeout(400); }
  const btn = page.locator(`[data-testid="${testid(target)}"]`);
  if (!(await btn.isVisible())) {
    // Only the first competition opens by default (Batch 139); open the target's group.
    await page.locator('button[aria-expanded="false"]', { hasText: target.competition }).first().click();
    await page.waitForTimeout(300);
  }
  await btn.scrollIntoViewIfNeeded();
  await btn.click();
  await page.waitForSelector('[data-sonner-toast]', { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(900);
  const m = await measure(page);
  const name = `current-round--${state}--${width}--${theme}.png`;
  await page.screenshot({ path: `${SHOTS}/${name}` });
  const rec = { state, width, theme, persona, target: target.runner_name, file: name, sha256: sha256(`${SHOTS}/${name}`), responses, ...m };
  out.push(rec);
  log(`${name}: http=${JSON.stringify(responses)} toast=${JSON.stringify(m.toast?.title)} type=${m.toast?.type} action=${JSON.stringify(m.toast?.action)} gap=${m.gapToTabBar} outstanding=${JSON.stringify(m.outstanding)}`);
  if (m.toast) rec.titleContrast = ratio(m.toast.titleColor, m.toast.bg);
  if (offline) {
    // Still nothing after a longer wait? Then reconnect and see what the paused intent does.
    await page.waitForTimeout(4000);
    const later = await measure(page);
    rec.after5s = { toast: later.toast?.title ?? null, outstanding: later.outstanding };
    await ctx.setOffline(false);
    await page.waitForSelector('[data-sonner-toast]', { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(1200);
    const back = await measure(page);
    const name2 = `current-round--feedback-queued-reconnected--${width}--${theme}.png`;
    await page.screenshot({ path: `${SHOTS}/${name2}` });
    rec.reconnected = { file: name2, sha256: sha256(`${SHOTS}/${name2}`), responses: [...responses], toast: back.toast?.title ?? null, type: back.toast?.type ?? null };
    log(`  offline +5s: ${JSON.stringify(rec.after5s)}; reconnected: ${JSON.stringify(rec.reconnected)}`);
  }
  if (m.toast) log(`  toast colours: bg=${m.toast.bg} title=${m.toast.titleColor} -> ${rec.titleContrast}:1; action bg=${m.toast.actionBg} fg=${m.toast.actionColor}`);
  await ctx.close();
  return rec;
}

log(`reset price: ${await movePrice(4.3)}`);
let i = 0;
for (const { width, theme } of combos) {
  i += 1;
  await run({ state: 'feedback-confirmed', width, theme, persona: 'Carol', target: i % 2 ? S.sl2Yes : S.sl2Draw });
  const victim = i % 2 ? S.brechin : S.eplDraw;
  await run({ state: 'feedback-conflict', width, theme, persona: 'Alice', target: victim,
    beforeTap: async () => `bob claims ${victim.runner_name}: ${(await pickAs('Bob', victim)).status}` });
  const moved = (4.3 + 0.1 * (i + 2)).toFixed(2);
  await run({ state: 'feedback-price-moved', width, theme, persona: 'Hana', target: S.chelsea,
    beforeTap: async () => `move Chelsea 4.30 -> ${moved}: ${await movePrice(moved)}` });
  log(`reset price: ${await movePrice(4.3)}`);
  await run({ state: 'feedback-queued-offline', width, theme, persona: 'Ivan', target: i % 2 ? S.eplYes : S.forfar, offline: true });
}
writeFileSync(`${NOTES}/${process.env.OUT || "feedback-results.json"}`, JSON.stringify(out, null, 1));
await browser.close();
