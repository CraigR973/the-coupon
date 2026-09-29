// SEC-19 re-drive: CSP violations with the bundle loaded.
//   . ~/.nvm/nvm.sh && nvm use 24 --silent && node csp_check.mjs > csp-check.txt
// 1. Production /login (public, unauthenticated, read-only GET) with its real headers.
// 2. The local production bundle on :4310, with production's exact CSP injected on every
//    document response (connect-src pointed at the local API instead of Railway), signed in
//    as Bob, across the main routes.
import { chromium } from '/Users/craigrobinson/the-coupon/apps/web/node_modules/@playwright/test/index.mjs';

const PROD_CSP =
  "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self' 'sha256-Td895dO8wmyTVvdQFkeGpQIFPVrJm4buJgVlEFGlNmo='; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://*.supabase.co; font-src 'self'; connect-src 'self' https://api-production-109b1.up.railway.app https://api-production-0641.up.railway.app; worker-src 'self'; manifest-src 'self'";
const LOCAL_CSP = PROD_CSP.replace(
  /connect-src [^;]+/,
  "connect-src 'self' http://127.0.0.1:8110",
);

const listen = `
  window.__csp = [];
  document.addEventListener('securitypolicyviolation', (e) => {
    window.__csp.push(e.violatedDirective + ' ' + e.blockedURI + ' ' + (e.sourceFile||'') + ':' + e.lineNumber);
  });`;

// Fulfilled documents lose their loopback address-space context, so Chromium's Local
// Network Access check blocks the bundle's calls to the local API; turn it off locally.
const b = await chromium.launch({ args: ['--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessRespectPreflightResults,BlockInsecurePrivateNetworkRequests'] });

// 1 — production, public page only
if (!process.env.SKIP_PROD) {
  const ctx = await b.newContext({ viewport: { width: 1280, height: 800 } });
  await ctx.addInitScript(listen);
  const p = await ctx.newPage();
  const errs = [];
  p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
  const r = await p.goto('https://the-coupon-production.vercel.app/login', { waitUntil: 'networkidle' });
  await p.waitForTimeout(2000);
  console.log('PROD /login status', r.status(), 'csp header present:', !!r.headers()['content-security-policy']);
  console.log('PROD /login violations:', JSON.stringify(await p.evaluate(() => window.__csp)));
  console.log('PROD /login console errors:', JSON.stringify(errs));
  await ctx.close();
}

// 2 — local bundle with production's CSP injected, signed in
// serviceWorkers: 'block' — otherwise the service worker answers every navigation after the
// first from its precache, which Playwright's route never sees, and the CSP is not injected.
{
  const ctx = await b.newContext({ viewport: { width: 1280, height: 800 }, serviceWorkers: 'block' });
  await ctx.addInitScript(listen);
  await ctx.route('http://127.0.0.1:4310/**', async (route) => {
    const req = route.request();
    if (req.resourceType() !== 'document') return route.continue();
    const resp = await route.fetch();
    const headers = { ...resp.headers(), 'content-security-policy': LOCAL_CSP };
    await route.fulfill({ response: resp, headers });
  });
  const p = await ctx.newPage();
  const errs = [];
  p.on('console', (m) => { if (m.type() === 'error' || /Content Security Policy/i.test(m.text())) errs.push(m.text()); });
  await p.goto('http://127.0.0.1:4310/login', { waitUntil: 'networkidle' });
  await p.locator('input').first().fill('Gary');
  const pins = p.locator('input[inputmode="numeric"], input[type="password"]');
  for (let i = 0; i < 4; i++) await pins.nth(i).fill('1234'[i]);
  await p.keyboard.press('Enter');
  await p.waitForTimeout(3000);
  console.log('LOCAL after login url:', p.url());
  const seen = {};
  const all = {};
  for (const path of ['/', '/leagues/the-coupon', '/leagues/the-coupon/predictions', '/leagues/the-coupon/predictions/coupon', '/leagues/the-coupon/leaderboard', '/leagues/the-coupon/members', '/football', '/settings', '/profile', '/leagues/league-b/admin/settings', '/leagues/league-b/admin/audit-log']) {
    await p.goto('http://127.0.0.1:4310' + path, { waitUntil: 'networkidle' });
    await p.waitForTimeout(1500);
    all[path] = await p.evaluate(() => window.__csp);
    seen[path] = p.url();
  }
  console.log('LOCAL violations by route:', JSON.stringify(all));
  console.log('LOCAL final urls:', JSON.stringify(seen));
  // Positive control: the listener must see a violation when one happens.
  await p.evaluate(() => fetch('https://example.com/csp-probe').catch(() => 0));
  await p.waitForTimeout(500);
  console.log('LOCAL positive control (fetch to example.com):', JSON.stringify(await p.evaluate(() => window.__csp)));
  // SEC-10: the post-login redirect guard, driven through the real login page.
  await p.evaluate(() => localStorage.clear());
  for (const next of ['/leagues/the-coupon/leaderboard', '//evil.example/x', '/\\evil.example', 'https://evil.example/']) {
    await p.goto('http://127.0.0.1:4310/login?next=' + encodeURIComponent(next), { waitUntil: 'networkidle' });
    await p.locator('input').first().fill('Hank');
    const boxes = p.locator('input[inputmode="numeric"], input[type="password"]');
    for (let i = 0; i < 4; i++) await boxes.nth(i).fill('7294'[i]);
    await p.keyboard.press('Enter');
    await p.waitForTimeout(2500);
    console.log('SEC-10 next=' + next + ' -> landed on ' + p.url());
    await p.evaluate(() => localStorage.clear());
  }
  console.log('LOCAL console errors:', JSON.stringify(errs.slice(0, 20)));
  await ctx.close();
}
await b.close();
