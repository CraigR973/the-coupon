// PWA pass — the installed app on an iPhone-shaped viewport: display-mode standalone
// (navigator.standalone + matchMedia shim, which is what the app itself reads), real
// env(safe-area-inset-*) values via CDP Emulation.setSafeAreaInsetsOverride (top 59 =
// Dynamic Island, bottom 34 = home indicator), iOS UA, touch. Checks header, tab bar,
// toast and offline banner against the insets, and reads theme-color per theme.
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, sha256, WEB, NOTES, SHOTS } from './lib.mjs';

const INSETS = { top: 59, bottom: 34, left: 0, right: 0 };
const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const standalone = () => {
  Object.defineProperty(navigator, 'standalone', { get: () => true });
  const mm = window.matchMedia.bind(window);
  window.matchMedia = (q) => (/display-mode:\s*standalone/.test(q) ? { matches: true, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; } } : mm(q));
};
const browser = await chromium.launch();
const out = [];
async function shot(theme, name, path, act) {
  const ctx = await newContext(browser, { width: 393, height: 852, theme, persona: 'Alice', extraInit: standalone });
  await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: WEB });
  const page = await ctx.newPage();
  await page.setExtraHTTPHeaders({});
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Emulation.setSafeAreaInsetsOverride', { insets: INSETS });
  await cdp.send('Emulation.setUserAgentOverride', { userAgent: UA, platform: 'iPhone' });
  await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
  await page.goto(`${WEB}${path}`);
  await settle(page);
  if (act) await act(page, ctx);
  const m = await page.evaluate(() => {
    const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom), h: Math.round(b.height) }; };
    const header = document.querySelector('header');
    const headerRow = header?.querySelector('div');
    const bar = document.querySelector('nav[aria-label="Primary"]');
    const toast = document.querySelector('[data-sonner-toast]');
    const banner = [...document.querySelectorAll('div')].find((d) => /You're offline|You’re offline/.test(d.textContent) && d.children.length < 3 && d.className.includes('amber'));
    const meta = document.querySelector('meta[name="theme-color"]')?.getAttribute('content');
    return {
      standaloneSeen: matchMedia('(display-mode: standalone)').matches,
      installGate: /Add to Home Screen|Install/i.test(document.body.innerText.slice(0, 400)),
      header: r(header), headerPadTop: header ? getComputedStyle(header).paddingTop : null, headerRow: r(headerRow),
      tabBar: r(bar), tabBarPadBottom: bar ? getComputedStyle(bar).paddingBottom : null,
      toast: toast ? { ...r(toast), text: toast.textContent.trim().slice(0, 60) } : null,
      toastGap: toast && bar ? Math.round(bar.getBoundingClientRect().top - toast.getBoundingClientRect().bottom) : null,
      offlineBanner: banner ? { ...r(banner), sticky: getComputedStyle(banner).position } : null,
      themeColor: meta, headerBg: header ? getComputedStyle(header).backgroundColor : null,
      innerHeight,
    };
  });
  const file = `${name}--standalone-safearea--393--${theme}.png`;
  await page.screenshot({ path: `${SHOTS}/${file}` });
  const rec = { theme, name, path, file, sha256: sha256(`${SHOTS}/${file}`), ...m };
  out.push(rec);
  console.log(`${file}: ${JSON.stringify(m)}`);
  await ctx.close();
}
for (const theme of ['dark', 'light']) {
  await shot(theme, 'home', '/');
  await shot(theme, 'standings-toast', '/leagues/the-coupon/leaderboard', async (page) => {
    await page.getByRole('button', { name: /copy standings/i }).click();
    await page.waitForSelector('[data-sonner-toast]', { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(800);
  });
  await shot(theme, 'current-round-offline', '/leagues/the-coupon/predictions', async (page, ctx) => {
    await ctx.setOffline(true);
    await page.waitForTimeout(1200);
  });
  await shot(theme, 'current-round-offline-scrolled', '/leagues/the-coupon/predictions', async (page, ctx) => {
    await ctx.setOffline(true);
    await page.waitForTimeout(600);
    await page.mouse.wheel(0, 900);
    await page.waitForTimeout(600);
  });
}
await browser.close();
writeFileSync(`${NOTES}/pwa-results.json`, JSON.stringify({ insets: INSETS, out }, null, 1));
