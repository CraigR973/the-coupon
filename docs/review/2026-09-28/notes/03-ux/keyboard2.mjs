// Follow-up to keyboard.mjs: the three dialogs its generic selectors could not reach.
// Each: reach the trigger by Tab, open from the keyboard, confirm focus moved into the
// dialog, Tab 12× for containment, Escape, record where focus went.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, WEB, NOTES } from './lib.mjs';

const browser = await chromium.launch();
const log = [];
const active = (page) => page.evaluate(() => {
  const e = document.activeElement;
  return { tag: e?.tagName, text: (e?.getAttribute('aria-label') || e?.innerText || '').trim().slice(0, 40), inDialog: !!e?.closest('[role="dialog"],[role="alertdialog"]'), inMenu: !!e?.closest('[role="menu"]'), fv: !!e?.matches(':focus-visible') };
});
async function tabUntil(page, pred, max = 90) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab');
    const a = await active(page);
    if (pred(a)) return a;
  }
  throw new Error('not reached');
}
async function dialogCase(label, { persona, path, reach, viaMenu = null }) {
  const ctx = await newContext(browser, { width: 1280, theme: 'dark', persona });
  const page = await ctx.newPage();
  const rec = { label };
  try {
    await page.goto(`${WEB}${path}`);
    await settle(page);
    rec.trigger = await tabUntil(page, reach);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(400);
    if (viaMenu) {
      for (let i = 0; i < 10; i++) {
        const a = await active(page);
        if (viaMenu.test(a.text)) break;
        await page.keyboard.press('ArrowDown');
        await page.waitForTimeout(80);
      }
      rec.menuItem = await active(page);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(500);
    }
    rec.afterOpen = await active(page);
    rec.dialogOpen = await page.evaluate(() => !!document.querySelector('[role="dialog"],[role="alertdialog"]'));
    let esc = 0;
    for (let i = 0; i < 12; i++) { await page.keyboard.press('Tab'); if (!(await active(page)).inDialog) esc++; }
    rec.tabEscapes = esc;
    await page.keyboard.press('Escape');
    await page.waitForTimeout(600);
    rec.afterEscape = { ...(await active(page)), closed: await page.evaluate(() => !document.querySelector('[role="dialog"],[role="alertdialog"]')) };
    await page.keyboard.press('Tab');
    rec.nextTab = await active(page);
  } catch (e) { rec.error = String(e).slice(0, 160); }
  log.push(JSON.stringify(rec));
  await ctx.close();
}
await dialogCase('Leave league via League actions menu (Alice, league admin)', { persona: 'Alice', path: '/leagues/the-coupon/leaderboard',
  reach: (a) => a.text === 'League actions', viaMenu: /leave/i });
await dialogCase('Delete league via League actions menu (Alice)', { persona: 'Alice', path: '/leagues/the-coupon/leaderboard',
  reach: (a) => a.text === 'League actions', viaMenu: /delete/i });
await dialogCase('Leave button on standings (Carol, member)', { persona: 'Carol', path: '/leagues/the-coupon/leaderboard',
  reach: (a) => a.tag === 'BUTTON' && /^leave/i.test(a.text) });
await dialogCase('Delete player (site admin players)', { persona: 'Alice', path: '/admin/players',
  reach: (a) => a.tag === 'BUTTON' && /^delete$/i.test(a.text) });
await dialogCase('Leave league (members page)', { persona: 'Alice', path: '/leagues/the-coupon/admin/members',
  reach: (a) => a.tag === 'BUTTON' && /leave league/i.test(a.text) });
writeFileSync(`${NOTES}/keyboard2.txt`, log.join('\n') + '\n');
console.log(log.join('\n'));
await browser.close();
