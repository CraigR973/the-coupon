import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type Browser, type Page } from '@playwright/test';

const API = process.env.COUPON_E2E_API_URL ?? 'http://127.0.0.1:8000';
const ARTIFACT_DIR =
  process.env.COUPON_E2E_ARTIFACT_DIR ??
  '/Users/craigrobinson/the-coupon/artifacts/batch-6';

async function login(browser: Browser, displayName: string): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('/login');
  await page.getByLabel('Display name').fill(displayName);
  for (const [index, digit] of [...'1234'].entries()) {
    await page.getByLabel(`PIN digit ${index + 1}`).fill(digit);
  }
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL('/');
  await page.goto('/predictions');
  await expect(page.getByRole('heading', { name: "This week's coupon" })).toBeVisible();
  await expect(page.locator('[data-testid^="pick-card-"]')).toHaveCount(2);
  return page;
}

test('members claim unique picks, then lock and settle the combined coupon', async ({
  browser,
  request,
}) => {
  mkdirSync(ARTIFACT_DIR, { recursive: true });

  const seeded = await request.post(`${API}/__e2e/seed`);
  expect(seeded.ok(), await seeded.text()).toBeTruthy();

  const alice = await login(browser, 'Alice');
  await alice.getByRole('button', { name: /Arsenal.*1\.90.*win 19 pts/i }).click();
  await expect(alice.getByTestId('my-pick-summary')).toContainText('Arsenal');

  const bob = await login(browser, 'Bob');
  await bob.getByRole('button', { name: /Forfar Athletic.*2\.40.*win 24 pts/i }).click();
  await expect(bob.getByTestId('my-pick-summary')).toContainText('Forfar Athletic');

  const carol = await login(browser, 'Carol');
  const takenArsenal = carol.getByRole('button', { name: /Arsenal.*taken by Alice/i });
  await expect(takenArsenal).toBeDisabled();

  const blocked = await carol.evaluate(async (api) => {
    const token = localStorage.getItem('coupon_access');
    const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
    const slateResponse = await fetch(
      `${api}/api/v1/leagues/the-coupon/gameweek/current`,
      { headers },
    );
    const slate = (await slateResponse.json()) as {
      fixtures: Array<{ fixture_id: string; home: string }>;
    };
    const fixture = slate.fixtures.find((item) => item.home === 'Arsenal');
    if (!fixture) return { status: 500, detail: 'FIXTURE_NOT_FOUND' };
    const response = await fetch(`${api}/api/v1/leagues/the-coupon/picks`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        fixture_id: fixture.fixture_id,
        market: 'MATCH_ODDS',
        outcome: 'HOME',
      }),
    });
    return { status: response.status, detail: (await response.json()).detail };
  }, API);
  expect(blocked).toEqual({ status: 409, detail: 'SELECTION_TAKEN' });

  const locked = await request.post(`${API}/__e2e/lock`);
  expect(locked.ok(), await locked.text()).toBeTruthy();
  await carol.reload();
  await expect(carol.getByTestId('lock-banner')).toContainText('Picks are locked');

  const settled = await request.post(`${API}/__e2e/settle`);
  expect(settled.ok(), await settled.text()).toBeTruthy();
  expect(await settled.json()).toMatchObject({ status: 'settled', resolved: 2 });

  await alice.goto('/leagues/the-coupon/leaderboard');
  await expect(alice.getByTestId('standings')).toContainText('Bob');
  await expect(alice.getByTestId('standings')).toContainText('24');
  await expect(alice.getByTestId('standings')).toContainText('Alice');
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
