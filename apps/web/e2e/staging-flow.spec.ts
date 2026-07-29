import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type Browser, type Page } from '@playwright/test';

const API = requiredUrl('COUPON_E2E_API_URL');
const ARTIFACT_DIR = process.env.COUPON_E2E_ARTIFACT_DIR ?? 'test-results/staging/evidence';
const PIN = required('COUPON_E2E_PIN');
const ADMIN = required('COUPON_E2E_ADMIN_NAME');
const ALICE = required('COUPON_E2E_ALICE_NAME');
const BOB = required('COUPON_E2E_BOB_NAME');
const LOCKOUT_MEMBER = required('COUPON_E2E_LOCKOUT_NAME');

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function requiredUrl(name: string): string {
  const value = required(name);
  if (!value.startsWith('https://')) {
    throw new Error(`${name} must be an explicit HTTPS staging origin`);
  }
  return value.replace(/\/$/, '');
}

async function login(browser: Browser, displayName: string): Promise<Page> {
  const context = await browser.newContext({ serviceWorkers: 'allow' });
  const page = await context.newPage();
  await page.goto('/login');
  await page.getByLabel('Display name').fill(displayName);
  for (const [index, digit] of [...PIN].entries()) {
    await page.getByLabel(`PIN digit ${index + 1}`).fill(digit);
  }
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL('/');
  return page;
}

test.beforeAll(() => {
  mkdirSync(ARTIFACT_DIR, { recursive: true });
});

test('@lockout-set durable lockout survives the proxy limiter', async ({ request }) => {
  const wrongPin = String((Number(PIN) + 1) % 10_000).padStart(4, '0');
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const response = await request.post(`${API}/api/v1/auth/login`, {
      headers: { 'X-Forwarded-For': `192.0.2.${attempt + 10}` },
      data: { display_name: LOCKOUT_MEMBER, pin: wrongPin },
    });
    expect(response.status()).toBe(401);
  }
});

test('@lockout-confirm durable lockout remains after an API restart', async ({ request }) => {
  const locked = await request.post(`${API}/api/v1/auth/login`, {
    data: { display_name: LOCKOUT_MEMBER, pin: PIN },
  });
  expect(locked.status()).toBe(423);
});

test('@open deep links, membership, picks, and PWA update check', async ({
  browser,
  page,
  request,
}) => {
  await page.goto('/settings');
  await expect(page).toHaveURL('/login');
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await page.goto('/forgot-pin');
  await expect(page.getByRole('heading', { name: 'Reset PIN' })).toBeVisible();

  const admin = await login(browser, ADMIN);
  await admin.goto('/leagues/the-coupon/admin/members');
  await expect(admin.getByRole('heading', { name: 'Members' })).toBeVisible();
  await expect(admin.getByText('Admin', { exact: true }).last()).toBeVisible();
  const membershipEvidence = await admin.evaluate(async (api) => {
    const token = localStorage.getItem('coupon_access');
    const headers = { Authorization: `Bearer ${token}` };
    const membersResponse = await fetch(`${api}/api/v1/leagues/the-coupon/members`, {
      headers,
    });
    const members = (await membersResponse.json()) as Array<{
      id: string;
      role: string;
    }>;
    const target = members.find((member) => member.role === 'player');
    if (!target) return { count: members.length, promote: 0, demote: 0, idsPresent: false };
    const promote = await fetch(
      `${api}/api/v1/leagues/the-coupon/members/${target.id}/promote`,
      { method: 'POST', headers },
    );
    const demote = await fetch(
      `${api}/api/v1/leagues/the-coupon/members/${target.id}/demote`,
      { method: 'POST', headers },
    );
    return {
      count: members.length,
      promote: promote.status,
      demote: demote.status,
      idsPresent: members.every((member) => Boolean(member.id)),
    };
  }, API);
  expect(membershipEvidence).toEqual({
    count: 15,
    promote: 204,
    demote: 204,
    idsPresent: true,
  });
  await admin.screenshot({
    path: join(ARTIFACT_DIR, 'members-admin.png'),
    fullPage: true,
  });

  const registration = await admin.evaluate(async () => {
    const ready = await navigator.serviceWorker.ready;
    await ready.update();
    return {
      scope: ready.scope,
      scriptURL: ready.active?.scriptURL ?? '',
    };
  });
  expect(registration.scope).toContain('/');
  expect(registration.scriptURL).toContain('/sw.js');

  const sw = await request.get(`${requiredUrl('COUPON_E2E_WEB_URL')}/sw.js`);
  expect(sw.status()).toBe(200);
  expect(sw.headers()['cache-control']).toContain('max-age=0');

  const alice = await login(browser, ALICE);
  await alice.goto('/predictions');
  await expect(alice.getByRole('heading', { name: "This week's coupon" })).toBeVisible();
  await expect(alice.locator('[data-testid^="pick-card-"]')).toHaveCount(2);
  const arsenal = alice.getByRole('button', { name: /Arsenal/i });
  if ((await arsenal.getAttribute('aria-pressed')) !== 'true') {
    await arsenal.click();
  }
  await expect(alice.getByTestId('my-pick-summary')).toContainText('Arsenal');

  const bob = await login(browser, BOB);
  await bob.goto('/predictions');
  await expect(bob.locator('[data-testid^="pick-card-"]')).toHaveCount(2);
  await expect(
    bob.getByRole('button', { name: /Arsenal.*taken by Staging/i }),
  ).toBeDisabled();
  const forfar = bob.getByRole('button', { name: /Forfar Athletic/i });
  if ((await forfar.getAttribute('aria-pressed')) !== 'true') {
    await forfar.click();
  }
  await expect(bob.getByTestId('my-pick-summary')).toContainText('Forfar Athletic');
  await bob.screenshot({
    path: join(ARTIFACT_DIR, 'picks-open.png'),
    fullPage: true,
  });
});

test('@locked locked gameweek blocks further picks', async ({ browser }) => {
  const alice = await login(browser, ALICE);
  await alice.goto('/predictions');
  await expect(alice.getByTestId('lock-banner')).toContainText('Picks are locked');
  await alice.screenshot({
    path: join(ARTIFACT_DIR, 'picks-locked.png'),
    fullPage: true,
  });
});

test('@settled settlement retry updates standings and combined coupon', async ({ browser }) => {
  const alice = await login(browser, ALICE);
  await alice.goto('/leagues/the-coupon/leaderboard');
  await expect(alice.getByTestId('standings')).toContainText(BOB);
  await expect(alice.getByTestId('standings')).toContainText('24');
  await expect(alice.getByTestId('standings')).toContainText(ALICE);
  await expect(alice.getByTestId('standings')).toContainText('19');
  await alice.screenshot({
    path: join(ARTIFACT_DIR, 'standings-settled.png'),
    fullPage: true,
  });

  await alice.goto('/predictions/coupon');
  await expect(alice.getByText('2-fold accumulator')).toBeVisible();
  await expect(alice.getByText('4.56')).toBeVisible();
  await expect(alice.getByText('All legs won 🎉')).toBeVisible();
  await expect(alice.getByTestId('acca-leg-0')).toContainText('Won');
  await expect(alice.getByTestId('acca-leg-1')).toContainText('Won');
  await alice.screenshot({
    path: join(ARTIFACT_DIR, 'combined-coupon-settled.png'),
    fullPage: true,
  });
});
