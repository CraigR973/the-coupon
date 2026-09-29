// Keyboard-only pass (lens 03). Two parts, all keys counted, results to keyboard.json/.txt.
//
// A. The walk: fresh signed-out context at 1280×800 → /login → sign in as Carol (real
//    POST, one login) → reach the coupon → claim the first free selection. Only
//    keyboard events; every stop records whether the focused element matches
//    :focus-visible and what box-shadow/outline it draws. Navigation keys and typed
//    characters are counted separately.
// B. Overlays: for each dialog / sheet / menu, open it from the keyboard, check focus
//    moved inside, Tab 12 times to test containment (modal) , Escape, and check it closed
//    and focus returned to the trigger.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, WEB, NOTES } from './lib.mjs';

const out = { walk: [], overlays: [] };
const log = [];
const browser = await chromium.launch();

async function focusInfo(page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return { tag: 'BODY' };
    const cs = getComputedStyle(el);
    return {
      tag: el.tagName,
      role: el.getAttribute('role'),
      name: (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder') || '').replace(/\s+/g, ' ').trim().slice(0, 50),
      testid: el.getAttribute('data-testid'),
      fv: el.matches(':focus-visible'),
      ring: cs.boxShadow !== 'none' ? 'shadow' : cs.outlineStyle !== 'none' && cs.outlineWidth !== '0px' ? 'outline' : 'none',
      disabled: el.disabled === true,
    };
  });
}

// ---------- A. the walk ----------
{
  const ctx = await newContext(browser, { width: 1280, theme: 'dark', persona: null });
  const page = await ctx.newPage();
  let nav = 0;
  let typed = 0;
  const press = async (k) => {
    await page.keyboard.press(k);
    nav++;
    await page.waitForTimeout(90);
    const f = await focusInfo(page);
    out.walk.push({ key: k, url: new URL(page.url()).pathname, ...f });
    return f;
  };
  const type = async (t) => {
    for (const ch of t) {
      await page.keyboard.type(ch);
      typed++;
      await page.waitForTimeout(40);
    }
    out.walk.push({ typed: t, url: new URL(page.url()).pathname, ...(await focusInfo(page)) });
  };
  const tabTo = async (pred, max = 40) => {
    for (let i = 0; i < max; i++) {
      const f = await press('Tab');
      if (pred(f)) return f;
    }
    throw new Error('tabTo gave up');
  };
  await page.goto(`${WEB}/login`);
  await settle(page);
  await tabTo((f) => f.tag === 'INPUT');
  await type('Carol');
  await tabTo((f) => f.tag === 'INPUT');
  await type('1234');
  let f = await focusInfo(page);
  out.walk.push({ note: 'after PIN', ...f });
  // submit: Enter from the PIN field
  await press('Enter');
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 10000 }).catch(() => {});
  await settle(page);
  out.walk.push({ note: 'signed in at', url: new URL(page.url()).pathname });
  // navigate to the coupon: the first link/button whose name says coupon/pick
  await tabTo((x) => /coupon|pick|make your/i.test(x.name) && (x.tag === 'A' || x.tag === 'BUTTON'), 60);
  await press('Enter');
  await settle(page);
  out.walk.push({ note: 'on', url: new URL(page.url()).pathname });
  // claim: first enabled selection button
  await tabTo((x) => x.testid && x.testid.startsWith('selection-') && !x.disabled, 80);
  await press('Enter');
  await page.waitForTimeout(2500);
  const claimed = await page.evaluate(() => {
    const b = document.querySelector('[data-testid^="selection-"][aria-pressed="true"]');
    return b ? b.getAttribute('data-testid') : null;
  });
  const toast = await page.evaluate(() => [...document.querySelectorAll('[data-sonner-toast]')].map((t) => t.textContent.trim()));
  out.walkSummary = { navKeys: nav, typedChars: typed, total: nav + typed, claimed, toast,
    stopsWithoutVisibleFocus: out.walk.filter((w) => w.key === 'Tab' && (!w.fv || w.ring === 'none')).map((w) => `${w.url} ${w.tag} "${w.name}" fv=${w.fv} ring=${w.ring}`) };
  log.push(`WALK: ${nav} navigation keys + ${typed} typed = ${nav + typed}; claimed=${claimed}; toast=${JSON.stringify(toast)}`);
  await page.screenshot({ path: `${NOTES}/keyboard-walk-end.png` });
  await ctx.close();
}

// ---------- B. overlays ----------
async function overlay({ label, path, persona = 'Alice', width = 390, trigger, open = 'Enter', pre = null }) {
  const ctx = await newContext(browser, { width, theme: 'dark', persona });
  const page = await ctx.newPage();
  const rec = { label, path, width };
  try {
    await page.goto(`${WEB}${path}`);
    await settle(page);
    if (pre) await pre(page);
    // reach the trigger by Tab so :focus-visible modality is keyboard
    let found = false;
    for (let i = 0; i < 80; i++) {
      await page.keyboard.press('Tab');
      if (await page.evaluate((sel) => document.activeElement?.matches(sel), trigger)) { found = true; break; }
    }
    if (!found) throw new Error('trigger not reached by Tab: ' + trigger);
    rec.tabsToTrigger = true;
    await page.keyboard.press(open);
    await page.waitForTimeout(500);
    rec.afterOpen = await page.evaluate(() => {
      const el = document.activeElement;
      const box = el?.closest('[role="dialog"],[role="menu"],[role="alertdialog"]');
      return { inside: !!box, containerRole: box?.getAttribute('role') ?? null, tag: el?.tagName,
        name: (el?.getAttribute('aria-label') || el?.textContent || '').trim().slice(0, 40),
        modal: box?.getAttribute('aria-modal') ?? null };
    });
    if (rec.afterOpen.containerRole === 'dialog' || rec.afterOpen.containerRole === 'alertdialog') {
      let escaped = 0;
      for (let i = 0; i < 12; i++) {
        await page.keyboard.press('Tab');
        const inside = await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"],[role="alertdialog"]'));
        if (!inside) escaped++;
      }
      rec.tabEscapes = escaped;
    }
    await page.keyboard.press('Escape');
    await page.waitForTimeout(600);
    rec.afterEscape = await page.evaluate((sel) => {
      const el = document.activeElement;
      return { closed: !document.querySelector('[role="dialog"],[role="menu"],[role="alertdialog"]'),
        onTrigger: !!el?.matches(sel), tag: el?.tagName,
        name: (el?.getAttribute('aria-label') || el?.textContent || '').trim().slice(0, 40),
        fv: !!el?.matches(':focus-visible') };
    }, trigger);
  } catch (e) {
    rec.error = String(e).slice(0, 200);
  }
  out.overlays.push(rec);
  log.push(`${label} @${width}: ${JSON.stringify(rec)}`);
  await ctx.close();
}

await overlay({ label: 'More sheet (bottom nav)', path: '/', trigger: 'button[aria-haspopup="dialog"]' });
await overlay({ label: 'Account menu', path: '/', width: 1280, trigger: 'button[aria-label^="Account menu"]' });
await overlay({ label: 'Account menu', path: '/', width: 390, trigger: 'button[aria-label^="Account menu"]' });
await overlay({ label: 'League actions menu', path: '/leagues/the-coupon/leaderboard', width: 1280, trigger: 'button[aria-label="League actions"]' });
// League actions → "Leave league" dialog: open the menu, arrow to the item, Enter, then Escape
{
  const ctx = await newContext(browser, { width: 1280, theme: 'dark', persona: 'Carol' });
  const page = await ctx.newPage();
  const rec = { label: 'Leave-league dialog (from League actions menu)', path: '/leagues/the-coupon/leaderboard', width: 1280 };
  try {
    await page.goto(`${WEB}/leagues/the-coupon/leaderboard`);
    await settle(page);
    for (let i = 0; i < 80; i++) {
      await page.keyboard.press('Tab');
      if (await page.evaluate(() => document.activeElement?.matches('button[aria-label="League actions"]'))) break;
    }
    await page.keyboard.press('Enter');
    await page.waitForTimeout(400);
    // find the leave item by arrowing
    for (let i = 0; i < 8; i++) {
      const t = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? '');
      if (/leave/i.test(t)) break;
      await page.keyboard.press('ArrowDown');
      await page.waitForTimeout(80);
    }
    rec.item = await page.evaluate(() => document.activeElement?.textContent?.trim());
    await page.keyboard.press('Enter');
    await page.waitForTimeout(600);
    rec.afterOpen = await page.evaluate(() => ({ dialog: !!document.querySelector('[role="dialog"]'),
      inside: !!document.activeElement?.closest('[role="dialog"]'), tag: document.activeElement?.tagName }));
    await page.keyboard.press('Escape');
    await page.waitForTimeout(600);
    rec.afterEscape = await page.evaluate(() => ({ closed: !document.querySelector('[role="dialog"]'),
      tag: document.activeElement?.tagName,
      name: (document.activeElement?.getAttribute('aria-label') || document.activeElement?.textContent || '').trim().slice(0, 40) }));
  } catch (e) { rec.error = String(e).slice(0, 200); }
  out.overlays.push(rec);
  log.push(`${rec.label}: ${JSON.stringify(rec)}`);
  await ctx.close();
}
await overlay({ label: 'Leave-league dialog (members page)', path: '/leagues/the-coupon/admin/members', persona: 'Alice', width: 1280, trigger: 'button:is(.text-error)' });
await overlay({ label: 'Delete-player dialog (admin players)', path: '/admin/players', width: 1280, trigger: 'button[aria-label^="Delete"], button:has(svg.lucide-trash-2), button:has(svg.lucide-trash)' });

writeFileSync(`${NOTES}/keyboard.json`, JSON.stringify(out, null, 1));
writeFileSync(`${NOTES}/keyboard.txt`, log.join('\n') + '\n');
console.log(log.join('\n'));
await browser.close();
