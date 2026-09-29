// Lens 05 drive, phase 2: the production bundle in real Chromium against the port-8150 stack.
//
// No second port is bound: the page lives at http://127.0.0.1:8150 (the API's own origin)
// and Playwright fulfils every non-API request from the bundle built into the scratchpad
// with VITE_API_URL=http://127.0.0.1:8150. API calls go to the real server. Service
// workers are blocked so nothing bypasses the route.
//
//   . ~/.nvm/nvm.sh && nvm use 24 --silent && node browser.mjs
import { chromium } from '/Users/craigrobinson/the-coupon/apps/web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';
import path from 'node:path';

const SCR =
  '/private/tmp/claude-501/-Users-craigrobinson-the-coupon/3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad';
const BUNDLE = `${SCR}/web-features`;
const ORIGIN = 'http://127.0.0.1:8150';
const SHOTS = '/Users/craigrobinson/the-coupon/docs/review/2026-09-28/screenshots';
const TYPES = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.json': 'application/json', '.webmanifest': 'application/manifest+json',
  '.woff2': 'font/woff2', '.ico': 'image/x-icon', '.txt': 'text/plain' };
const log = (label, value) => console.log(`## ${label}\n${typeof value === 'string' ? value : JSON.stringify(value, null, 1)}`);
const shots = [];
const PH = (process.env.PHASES ?? 'b07,a11,a12').split(',');

async function newPage(browser, width = 1280, height = 800) {
  const context = await browser.newContext({ viewport: { width, height }, serviceWorkers: 'block',
    acceptDownloads: true, colorScheme: 'light' });
  await context.route(`${ORIGIN}/**`, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/__e2e')) return route.continue();
    let file = path.join(BUNDLE, decodeURIComponent(url.pathname));
    if (!file.startsWith(BUNDLE) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      file = path.join(BUNDLE, 'index.html');
    }
    return route.fulfill({ status: 200, body: fs.readFileSync(file),
      headers: { 'Access-Control-Allow-Origin': ORIGIN },
      contentType: TYPES[path.extname(file)] ?? 'application/octet-stream' });
  });
  const page = await context.newPage();
  const api = [];
  page.on('response', (r) => { if (r.url().includes('/api/v1/')) api.push(`${r.request().method()} ${new URL(r.url()).pathname} ${r.status()}`); });
  return { context, page, api };
}

async function typePin(page, label, pin) {
  for (let i = 0; i < pin.length; i++) {
    await page.getByLabel(`${label} digit ${i + 1}`, { exact: true }).fill(pin[i]);
  }
}

async function signIn(page, name) {
  await page.goto(`${ORIGIN}/login`);
  await page.locator('#display-name').fill(name);
  await typePin(page, 'PIN', '1234');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 });
}

async function shot(page, name, what) {
  const file = `${SHOTS}/${name}`;
  await page.screenshot({ path: file, fullPage: false });
  shots.push([name, what]);
}

const browser = await chromium.launch();
try {
  // ── FEAT-B07: a member finds "Your data" in Settings, downloads, deletes ─────────
  if (PH.includes('b07')) {
    const { context, page, api } = await newPage(browser);
    await signIn(page, 'Carol');
    await page.goto(`${ORIGIN}/settings`);
    const section = page.getByRole('heading', { name: 'Your data' });
    await section.scrollIntoViewIfNeeded();
    await shot(page, 'settings--your-data-unstyled--1280--light.png', 'Settings scrolled to Your data (Carol, before deletion)');
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }),
      page.getByRole('button', { name: 'Download my data' }).click(),
    ]);
    const saved = `${SCR}/carol-export.json`;
    await download.saveAs(saved);
    const data = JSON.parse(fs.readFileSync(saved, 'utf8'));
    log('B07 download via the UI', { filename: download.suggestedFilename(), keys: Object.keys(data),
      picks: data.picks?.length, profile_name: data.profile?.display_name });
    await page.getByRole('button', { name: 'Delete my account' }).click();
    await typePin(page, 'Confirm PIN', '1234');
    await shot(page, 'settings--delete-confirm-unstyled--1280--light.png', 'Delete my account: confirm panel with PIN entered');
    await page.getByRole('button', { name: 'Delete my account permanently' }).click();
    await page.waitForURL((u) => u.pathname.startsWith('/login'), { timeout: 20000 });
    const toast = await page.getByText('Your account has been deleted.').isVisible().catch(() => false);
    await shot(page, 'login--after-account-deleted-unstyled--1280--light.png', 'Landing on /login after self-service deletion');
    log('B07 delete via the UI', { landed_on: new URL(page.url()).pathname, toast_visible: toast,
      api: api.filter((l) => l.includes('/me/')) });
    await context.close();
  }

  // ── FEAT-B07 re-capture (styled) as Bob, opening the confirm panel but never submitting ──
  if (PH.includes('bob')) {
    const { context, page } = await newPage(browser);
    await signIn(page, 'Bob');
    await page.goto(`${ORIGIN}/settings`);
    await page.getByRole('heading', { name: 'Your data' }).scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
    await shot(page, 'settings--your-data-unstyled--1280--light.png', 'Settings scrolled to Your data (Bob)');
    await page.getByRole('button', { name: 'Delete my account' }).click();
    await typePin(page, 'Confirm PIN', '1234');
    await shot(page, 'settings--delete-confirm-unstyled--1280--light.png', 'Delete my account: confirm panel with PIN entered, not submitted (Bob)');
    await context.close();
  }

  // ── FEAT-A11: Dave (a renamed profile id, never told) sees the dialog once ───────
  if (PH.includes('a11')) {
    const { context, page, api } = await newPage(browser);
    await signIn(page, 'Dave');
    const dialog = page.getByTestId('rename-notice');
    await dialog.waitFor({ timeout: 15000 });
    await shot(page, 'home--rename-notice-unstyled--1280--light.png', 'In-app rename notice dialog shown to an untold renamed member');
    const text = await dialog.innerText();
    await page.getByRole('button', { name: 'Got it' }).click();
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForTimeout(3000);
    const again = await page.getByTestId('rename-notice').isVisible().catch(() => false);
    log('A11 dialog', { text, shown_again_after_reload: again,
      api: api.filter((l) => l.includes('rename-notice')) });
    await context.close();
  }

  // ── FEAT-A12: the register screen with sign-ups closed ────────────────────────
  if (PH.includes('a12')) {
    const { context, page, api } = await newPage(browser);
    await page.goto(`${ORIGIN}/register`);
    await page.locator('#display-name').waitFor();
    await shot(page, 'register--signups-closed-before-submit-unstyled--1280--light.png', 'Register form with sign-ups closed: full form, no notice');
    await page.locator('#display-name').fill('Newcomer');
    await typePin(page, 'Choose a PIN', '4826');
    await typePin(page, 'Confirm PIN', '4826');
    await page.getByRole('button', { name: /create account/i }).click();
    const alert = page.locator('p[role="alert"]');
    await alert.waitFor({ timeout: 15000 });
    await shot(page, 'register--signups-closed-after-submit-unstyled--1280--light.png', 'Register refused only after the form is filled in');
    log('A12 register with sign-ups closed', { alert: await alert.innerText(),
      api: api.filter((l) => l.includes('/auth/')) });
    await context.close();
  }
} finally {
  await browser.close();
  log('screenshots', shots);
}
