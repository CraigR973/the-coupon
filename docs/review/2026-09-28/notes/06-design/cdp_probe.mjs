import { chromium } from './lib.mjs';
const b = await chromium.launch();
console.log('chromium', b.version());
const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
const page = await ctx.newPage();
await page.setContent('<div id=a style="padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)">x</div>');
const cdp = await ctx.newCDPSession(page);
for (const [m, p] of [
  ['Emulation.setSafeAreaInsetsOverride', { insets: { top: 47, bottom: 34, left: 0, right: 0 } }],
  ['Emulation.setEmulatedMedia', { features: [{ name: 'display-mode', value: 'standalone' }] }],
]) {
  try { await cdp.send(m, p); console.log(m, 'ok'); } catch (e) { console.log(m, 'ERR', e.message.slice(0, 120)); }
}
console.log(await page.evaluate(() => ({ pad: getComputedStyle(document.getElementById('a')).paddingTop + ' / ' + getComputedStyle(document.getElementById('a')).paddingBottom, standalone: matchMedia('(display-mode: standalone)').matches })));
await b.close();
