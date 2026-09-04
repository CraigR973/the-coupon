import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type Browser, type Page } from '@playwright/test';

const API = process.env.COUPON_E2E_API_URL ?? 'http://127.0.0.1:8000';
const ARTIFACT_DIR =
  process.env.COUPON_E2E_ARTIFACT_DIR ??
  '/Users/craigrobinson/the-coupon/artifacts/batch-6';
const AXE_PATH = createRequire(import.meta.url).resolve('axe-core');

declare global {
  interface Window {
    axe: typeof import('axe-core');
  }
}

async function setTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((value) => localStorage.setItem('coupon_theme', value), theme);
  await page.reload();
  await expect(page.locator(`html.${theme}`)).toHaveCount(1);
}

async function expectNoColourContrastViolations(page: Page): Promise<void> {
  await page.addScriptTag({ path: AXE_PATH });
  const violations = await page.evaluate(async () => {
    const results = await window.axe.run(document.documentElement, {
      runOnly: { type: 'rule', values: ['color-contrast'] },
    });
    return results.violations.map((violation) => ({
      id: violation.id,
      targets: violation.nodes.flatMap((node) => node.target),
    }));
  });
  expect(violations).toEqual([]);
}

async function expectNoAxeViolations(page: Page): Promise<void> {
  await page.addScriptTag({ path: AXE_PATH });
  const violations = await page.evaluate(async () => {
    const results = await window.axe.run(document.documentElement);
    return results.violations.map((violation) => ({
      id: violation.id,
      targets: violation.nodes.flatMap((node) => node.target),
    }));
  });
  expect(violations).toEqual([]);
}

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
  // or Bob has taken carries a fixture-level marker, and the round's progress counts
  // Carol as the one member still to pick. Batch 105 moved those counts out of the
  // roster disclosure and into the status card, and the list they headed is now the
  // coupon section — no disclosure, because with a pick still to make it sits below
  // the fixtures rather than pushing them down.
  await expect(carol.getByTestId('competition-10932509')).toBeVisible();
  await expect(carol.getByTestId('competition-10932510')).toBeVisible();
  await expect(carol.getByTestId('round-progress')).toContainText('2 of 3 picked');
  await expect(carol.getByTestId('round-progress')).toContainText('1 to go');
  await expect(carol.getByTestId('round-status')).toContainText('Pick required');
  await expect(carol.getByTestId('coupon-section')).toContainText('Yet to pick');
  await carol.screenshot({
    path: join(ARTIFACT_DIR, 'batch-105-current-round-open.png'),
    fullPage: true,
  });

  // The two destinations, and only two: the combined coupon is a section of this one.
  const sections = carol.getByLabel('Coupon sections');
  await expect(sections.getByRole('link', { name: 'Current round' })).toBeVisible();
  await expect(sections.getByRole('link', { name: 'Season' })).toBeVisible();
  await expect(sections.getByRole('link', { name: /combined coupon/i })).toHaveCount(0);

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
  await expect(carol.getByTestId('round-clock')).toContainText('Picks are locked');
  // Carol never picked, so this round is not a complete coupon and must not read as one.
  await expect(carol.getByTestId('round-status')).toContainText('Incomplete coupon');
  await expect(carol.getByTestId('coupon-section')).toContainText('1 of 3 never picked');

  const settled = await request.post(`${API}/__e2e/settle`);
  expect(settled.ok(), await settled.text()).toBeTruthy();
  expect(await settled.json()).toMatchObject({ status: 'settled', resolved: 2 });

  await alice.goto('/leagues/the-coupon/leaderboard');
  await expect(alice.getByTestId('standings')).toContainText('Bob');
  await expect(alice.getByTestId('standings')).toContainText('24');
  await expect(alice.getByTestId('standings')).toContainText('Alice');
  await expect(alice.getByTestId('standings')).toContainText('19');
  await alice.setViewportSize({ width: 390, height: 844 });
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expect(alice.getByTestId('standings')).toContainText('Bob');
    await expect(alice.getByRole('button', { name: 'Copy standings' })).toBeVisible();
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-98-standings-${theme}-390x844.png`),
    });
    await expectNoAxeViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-92-standings-${theme}-390x844.png`),
    });
  }

  // Batch 105: the combined coupon's own address is a redirect into the round that
  // carries it. A link minted before the merge has to land on the copy section, at the
  // week it named — this is the assertion that saved links and notification taps still
  // reach what they were pointing at.
  await alice.goto('/leagues/the-coupon/predictions/coupon');
  await expect(alice).toHaveURL('/leagues/the-coupon/predictions#coupon');
  await expect(alice.getByTestId('coupon-section')).toBeVisible();
  await expect(alice.getByText('2 of 2 landed')).toBeVisible();
  await expect(alice.getByText('4.56')).toBeVisible();
  await expect(alice.getByText('All legs won 🎉')).toBeVisible();
  await expect(alice.getByTestId('acca-leg-0')).toContainText('Won');
  await expect(alice.getByTestId('acca-leg-1')).toContainText('Won');
  // Carol never picked, so she is in the list and not in the fold.
  await expect(alice.getByTestId('acca-leg-2')).toContainText('Yet to pick');
  await expect(alice.getByRole('button', { name: 'Copy result' })).toBeVisible();
  // The section the fragment names is what the keyboard is on, so the first Tab from
  // here moves inside the coupon rather than back at the top of the page.
  await expect(alice.locator('#coupon')).toBeFocused();
  await alice.screenshot({
    path: join(ARTIFACT_DIR, 'batch-105-coupon-section-settled.png'),
    fullPage: true,
  });

  // The same deep link with a week on it, which is the shape Season's rows and Batch
  // 107's notification both mint.
  const settledWeek = await alice.evaluate(async (api) => {
    const token = localStorage.getItem('coupon_access');
    const response = await fetch(`${api}/api/v1/leagues/the-coupon/coupon`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return ((await response.json()) as { gameweek_id: string }).gameweek_id;
  }, API);
  await alice.goto(`/leagues/the-coupon/predictions/coupon?gw=${settledWeek}`);
  await expect(alice).toHaveURL(
    `/leagues/the-coupon/predictions?gw=${settledWeek}#coupon`,
  );
  await expect(alice.getByTestId('coupon-section')).toContainText('Result');

  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expect(alice.getByRole('button', { name: 'Copy result' })).toBeVisible();
    await expectNoAxeViolations(alice);
    // Nothing on the merged surface may push the page sideways at 390px — the row
    // rebuild is the reason long team and player names no longer can.
    const overflow = await alice.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-105-round-settled-${theme}-390x844.png`),
    });
  }

  // Batch 26: home and My profile answer for every league the member plays, not
  // for whichever one happens to be bound.
  await alice.goto('/');
  const seededCard = alice.getByTestId('home-card-the-coupon');
  await expect(seededCard).toContainText('Arsenal');
  await expect(seededCard).toContainText('#2'); // Bob's 24 beat Alice's 19
  await expect(seededCard).toContainText('of 3');
  await expect(seededCard).toContainText('19 pts');
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expect(alice.getByTestId('home-hero')).toContainText('Hi Alice');
    await expect(alice.getByTestId('home-season-summary')).toContainText('19');
    await expectNoAxeViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-97-home-${theme}-390x844.png`),
    });
  }

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
