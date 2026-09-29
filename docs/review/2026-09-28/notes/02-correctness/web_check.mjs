// Lens 02 member-facing check in real Chromium against the prod bundle on 4320 (API 8120).
// Signs in once as Alice (display name + four PIN boxes), then reads home, L1 results and the
// settled round's coupon as text, and drives a lost claim race on L1's open round.
//   . ~/.nvm/nvm.sh && nvm use 24 --silent && node web_check.mjs
import { chromium } from '/Users/craigrobinson/the-coupon/apps/web/node_modules/@playwright/test/index.mjs';

const WEB = 'http://127.0.0.1:4320';
const SHOTS = '/Users/craigrobinson/the-coupon/docs/review/2026-09-28/screenshots';
const log = (...a) => console.log(...a);

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
await page.goto(`${WEB}/login`);
await page.waitForLoadState('networkidle');
const name = page.locator('input').first();
await name.fill('Alice');
const pins = page.locator('input[inputmode="numeric"], input[type="password"]');
const n = await pins.count();
for (let i = 0; i < Math.min(n, 4); i++) await pins.nth(i).fill('1234'[i]);
await page.keyboard.press('Enter');
await page.waitForTimeout(2500);
log('after login url:', page.url());

async function text(path, label) {
  await page.goto(`${WEB}${path}`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1200);
  const t = (await page.locator('main').innerText().catch(() => page.locator('body').innerText())).replace(/\n+/g, ' | ');
  log(`\n[${label}] ${path}\n${t.slice(0, 1600)}`);
  return t;
}

if (process.env.SKIP_HOME !== '1') {
  await text('/', 'home');
  await page.screenshot({ path: `${SHOTS}/home--last-result-void--1280--light.png`, fullPage: true });
}
await text('/leagues/l1-defaults/predictions/results', 'results');
await page.screenshot({ path: `${SHOTS}/results--void-leg-price--1280--light.png`, fullPage: true });
const link = page.getByText('Gameweek 1', { exact: true }).first();
if (await link.count()) {
  await link.click();
  await page.waitForTimeout(1500);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1200);
  log(`\n[settled coupon via results link] ${page.url()}\n` + (await page.locator('main').innerText()).replace(/\n+/g, ' | ').slice(0, 1600));
  await page.screenshot({ path: `${SHOTS}/coupon--settled-void-legs--1280--light.png`, fullPage: true });
}
await browser.close();
