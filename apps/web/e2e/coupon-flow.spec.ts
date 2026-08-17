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
  await page.goto('/leagues/the-coupon/predictions');
  await expect(page.getByRole('heading', { name: "This week's coupon" })).toBeVisible();
  await expect(page.getByTestId('competition-10932509')).toBeVisible();
  await expect(page.getByTestId('competition-10932510')).toBeVisible();
  await expect(page.locator('[data-testid^="pick-card-"]')).toHaveCount(0);
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
  await alice.getByTestId('competition-10932509').getByRole('button').click();
  await alice.getByRole('button', { name: /Arsenal.*1\.90.*win 19 pts/i }).click();
  await expect(alice.getByTestId('my-pick-summary')).toContainText('Arsenal');

  const bob = await login(browser, 'Bob');
  await bob.getByTestId('competition-10932510').getByRole('button').click();
  await bob.getByRole('button', { name: /Forfar Athletic.*2\.40.*win 24 pts/i }).click();
  await expect(bob.getByTestId('my-pick-summary')).toContainText('Forfar Athletic');

  const carol = await login(browser, 'Carol');
  await carol.getByTestId('competition-10932509').getByRole('button').click();
  const takenArsenal = carol.getByRole('button', { name: /Arsenal.*taken by Alice/i });
  await expect(takenArsenal).toBeDisabled();

  // Batch 9 presentation: the slate is grouped by competition, each fixture Alice
  // or Bob has taken carries a fixture-level marker, and the roster counts Carol
  // as the one member still to pick.
  await expect(carol.getByTestId('competition-10932509')).toBeVisible();
  await expect(carol.getByTestId('competition-10932510')).toBeVisible();
  await expect(carol.getByTestId('member-roster')).toContainText('2 of 3 picked');
  await expect(carol.getByTestId('member-roster')).toContainText('1 to go');
  await carol.getByTestId('member-roster').getByRole('button').click();
  await expect(carol.getByTestId('member-roster')).toContainText('Yet to pick');
  await carol.screenshot({
    path: join(ARTIFACT_DIR, 'coupon-grouped-with-roster.png'),
    fullPage: true,
  });

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

  await alice.goto('/leagues/the-coupon/predictions/coupon');
  await expect(alice.getByText('2-fold accumulator')).toBeVisible();
  await expect(alice.getByText('4.56')).toBeVisible();
  await expect(alice.getByText('All legs won 🎉')).toBeVisible();
  await expect(alice.getByTestId('acca-leg-0')).toContainText('Won');
  await expect(alice.getByTestId('acca-leg-1')).toContainText('Won');
  await alice.screenshot({
    path: join(ARTIFACT_DIR, 'combined-coupon-settled.png'),
    fullPage: true,
  });

  // Batch 26: home and My profile answer for every league the member plays, not
  // for whichever one happens to be bound.
  await alice.goto('/');
  const seededCard = alice.getByTestId('home-card-the-coupon');
  await expect(seededCard).toContainText('Arsenal');
  await expect(seededCard).toContainText('#2'); // Bob's 24 beat Alice's 19
  await expect(seededCard).toContainText('of 3');
  await expect(seededCard).toContainText('19 pts');

  const created = await alice.evaluate(async (api) => {
    const token = localStorage.getItem('coupon_access');
    const response = await fetch(`${api}/api/v1/leagues`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Work League', privacy: 'private' }),
    });
    return response.status;
  }, API);
  expect(created).toBe(201);

  await alice.goto('/');
  await expect(alice.getByTestId('home-league-cards').locator('> li')).toHaveCount(2);
  const newCard = alice.getByTestId('home-card-work-league');
  await expect(newCard).toContainText('No coupon published yet');
  await expect(newCard).toContainText('of 1');
  await alice.screenshot({ path: join(ARTIFACT_DIR, 'home-multi-league.png'), fullPage: true });

  // One tap opens that league's coupon at that league's own address (Batch 30):
  // the new league has no round, so the pick screen shows its empty state rather
  // than the seeded league's settled card.
  await newCard.getByRole('button').click();
  await expect(alice).toHaveURL('/leagues/work-league/predictions');
  await expect(alice.getByText('No coupon this week yet')).toBeVisible();

  // The paths this batch replaced still land, through the league now bound.
  await alice.goto('/predictions');
  await expect(alice).toHaveURL('/leagues/work-league/predictions');

  await alice.goto('/profile');
  await expect(alice.getByTestId('career-stats')).toContainText('19'); // points, both leagues
  const careerLeagues = alice.getByTestId('career-leagues').locator('> li');
  await expect(careerLeagues).toHaveCount(2);
  await expect(careerLeagues.first()).toContainText('#2 of 3');
  // Rank only averages over leagues big enough to rank against — the new
  // one-member league is excluded and the page says so.
  await expect(alice.getByText(/Averaged over 1 of your 2 leagues/)).toBeVisible();
  await expect(alice.getByTestId('career-league-work-league')).toBeVisible();
  await alice.screenshot({ path: join(ARTIFACT_DIR, 'career-profile.png'), fullPage: true });

  // The per-league record is still its own page, reached from the breakdown.
  await alice.getByTestId('career-league-the-coupon').click();
  await expect(alice.getByTestId('profile-stats')).toContainText('19');
  await expect(alice.getByTestId('profile-history')).toContainText('Arsenal');
});
