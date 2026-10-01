import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type Browser, type Locator, type Page, type Route } from '@playwright/test';

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
      nodes: violation.nodes.map((node) => ({
        targets: node.target,
        failureSummary: node.failureSummary,
        checks: [...node.any, ...node.all, ...node.none].map((check) => ({
          message: check.message,
          data: check.data,
        })),
      })),
    }));
  });
  expect(violations).toEqual([]);
}

async function expectDesktopColumns(left: Locator, right: Locator): Promise<void> {
  const [leftBox, rightBox] = await Promise.all([left.boundingBox(), right.boundingBox()]);
  expect(leftBox).not.toBeNull();
  expect(rightBox).not.toBeNull();
  expect(leftBox!.x).toBeLessThan(rightBox!.x);
  expect(Math.abs(leftBox!.y - rightBox!.y)).toBeLessThanOrEqual(12);
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
  // Batch 139 deliberately opens the first ordered competition, so a member sees a
  // fixture and price immediately rather than a screen of closed headings. Keep the
  // browser flow tied to that contract: the seeded slate has one card in that first
  // group and none in the still-collapsed second group.
  const firstCompetition = page.getByTestId('competition-10932509');
  await expect(firstCompetition.locator('[data-testid^="pick-card-"]')).toHaveCount(1);
  await expect(page.locator('[data-testid^="pick-card-"]')).toHaveCount(1);
  return page;
}

test('members claim unique picks, then lock and settle the combined coupon', async ({
  browser,
  request,
}) => {
  // This is the retained full product journey: three members, two themes, live axe
  // scans and responsive screenshots against the production bundle. Its individual waits
  // keep the normal short failure signal; the journey itself needs headroom on a
  // loaded local machine.
  test.setTimeout(120_000);
  mkdirSync(ARTIFACT_DIR, { recursive: true });

  const seeded = await request.post(`${API}/__e2e/seed`);
  expect(seeded.ok(), await seeded.text()).toBeTruthy();

  const alice = await login(browser, 'Alice');
  await alice.getByRole('button', { name: /Arsenal.*1\.90.*win 19 pts/i }).click();
  await expect(alice.getByTestId('my-pick-summary')).toContainText('Arsenal');

  const bob = await login(browser, 'Bob');
  await bob.getByTestId('competition-10932510').getByRole('button').click();
  await bob.getByRole('button', { name: /Forfar Athletic.*2\.40.*win 24 pts/i }).click();
  await expect(bob.getByTestId('my-pick-summary')).toContainText('Forfar Athletic');

  const carol = await login(browser, 'Carol');
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
    await alice.getByRole('button', { name: 'Copy standings' }).click();
    const toast = alice.locator('[data-sonner-toast]').last();
    await expect(toast).toBeVisible();
    const [toastBox, tabBarBox] = await Promise.all([
      toast.boundingBox(),
      alice.getByRole('navigation', { name: 'Primary' }).boundingBox(),
    ]);
    expect(toastBox).not.toBeNull();
    expect(tabBarBox).not.toBeNull();
    await expect
      .poll(async () => {
        const settledBox = await toast.boundingBox();
        return settledBox ? settledBox.y + settledBox.height : Number.POSITIVE_INFINITY;
      })
      .toBeLessThanOrEqual(tabBarBox!.y);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-149-toast-clear-${theme}-390x844.png`),
    });
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
    const seasonWeek = alice.getByText('Gameweek 1b');
    await seasonWeek.scrollIntoViewIfNeeded();
    await expect(seasonWeek).toBeInViewport();
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
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-113-season-week-${theme}-390x844.png`),
    });
  }

  // Batch 140. Desktop is a supported way to play: the round's two working surfaces sit
  // together, and the season lists use the width rather than leaving phone-sized rows in
  // an empty frame. The mobile checks above deliberately run first and remain stacked.
  await alice.setViewportSize({ width: 1280, height: 800 });
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expectDesktopColumns(
      alice.getByTestId('coupon-section'),
      alice.getByTestId('slate-section'),
    );
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-140-round-${theme}-1280x800.png`),
    });
  }

  await alice.goto('/leagues/the-coupon/leaderboard');
  const standings = alice.getByTestId('standings');
  await expect(standings).toContainText('Bob');
  await expect(standings.locator('> li')).toHaveCount(3);
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expectDesktopColumns(standings.locator('> li').first(), standings.locator('> li').nth(1));
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-140-standings-${theme}-1280x800.png`),
    });
  }

  await alice.goto('/leagues/the-coupon/predictions/results');
  const results = alice.getByTestId('results-list');
  await expect(results).toContainText('Bob');
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    const columns = await results.evaluate(
      (node) => getComputedStyle(node).gridTemplateColumns.trim().split(/\s+/).length,
    );
    expect(columns).toBe(2);
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-140-season-${theme}-1280x800.png`),
    });
  }

  // Batch 168. A 1280px display at 200% browser zoom produces a 640px CSS viewport.
  // The desktop bar must still be the compact 56px chrome there, without duplicating
  // its destinations in the mobile tab bar.
  await alice.setViewportSize({ width: 640, height: 450 });
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expect(alice.getByRole('navigation', { name: 'Main navigation' })).toBeVisible();
    await expect(alice.locator('nav[aria-label="Primary"]')).toBeHidden();
    const header = await alice.locator('header').boundingBox();
    expect(header).not.toBeNull();
    // The 56px desktop bar carries its one-pixel safe-area/border allowance in the
    // production bundle, so its rendered box is 57px rather than the mobile bar's 142px.
    expect(header!.height).toBeLessThanOrEqual(57);
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-168-zoom-${theme}-640x450.png`),
    });
  }

  await alice.goto('/settings');
  const aboutLink = alice.getByRole('link', { name: 'About & scoring rules' });
  await expect(aboutLink).toBeVisible();
  const aboutBox = await aboutLink.boundingBox();
  expect(aboutBox).not.toBeNull();
  expect(aboutBox!.height).toBeGreaterThanOrEqual(24);

  const loginContext = await browser.newContext();
  const loginPage = await loginContext.newPage();
  await loginPage.goto('/login');
  const forgotPin = loginPage.getByRole('link', { name: 'Forgot PIN?' });
  await expect(forgotPin).toBeVisible();
  const forgotPinBox = await forgotPin.boundingBox();
  expect(forgotPinBox).not.toBeNull();
  expect(forgotPinBox!.height).toBeGreaterThanOrEqual(24);
  await loginContext.close();

  await alice.setViewportSize({ width: 390, height: 844 });

  // Batch 26: home and My profile answer for every league the member plays, not
  // for whichever one happens to be bound.
  await alice.goto('/');
  const seededCard = alice.getByTestId('home-card-the-coupon');
  await expect(seededCard).toContainText('Arsenal');
  await expect(seededCard).toContainText('#2'); // Bob's 24 beat Alice's 19
  await expect(seededCard).toContainText('of 3');
  await expect(seededCard).toContainText('19 pts');

  // Batch 106. The round has settled, so this card is between rounds and its primary
  // part may not carry last round's pick or price — those belong under `Last result`.
  await expect(seededCard.getByText('Between rounds')).toBeVisible();
  const seededPrimary = seededCard.locator('button').first();
  await expect(seededPrimary).not.toContainText('Arsenal');
  await expect(seededPrimary).not.toContainText('1.90');
  await expect(seededCard.getByTestId('last-result')).toContainText('Arsenal');
  await expect(seededCard.getByTestId('last-result')).toContainText('Last result');

  // The hero's blurred corner layers are clipped to the hero's own radius, so nothing
  // coloured protrudes past its top-right or bottom-left corner.
  const glowClip = await alice.getByTestId('home-hero-glows').evaluate((node) => {
    const style = getComputedStyle(node);
    const hero = node.parentElement!.getBoundingClientRect();
    const box = node.getBoundingClientRect();
    return {
      clipPath: style.clipPath,
      overflow: style.overflow,
      backgroundImage: style.backgroundImage,
      filter: style.filter,
      children: node.childElementCount,
      radius: style.borderTopRightRadius,
      withinHero:
        box.left >= hero.left - 0.5 &&
        box.right <= hero.right + 0.5 &&
        box.top >= hero.top - 0.5 &&
        box.bottom <= hero.bottom + 0.5,
    };
  });
  expect(glowClip.overflow).toBe('hidden');
  // The `var()` resolves rather than falling back to `none`, and it carries the hero's
  // own radius — this is the assertion that the corner clip is real and not inherited.
  expect(glowClip.clipPath).toContain('inset');
  expect(glowClip.radius).toBe('28px');
  expect(glowClip.withinHero).toBe(true);
  // Backgrounds, not filtered children: nothing here has a rendering context that could
  // paint past the rounded corners on WebKit.
  expect(glowClip.children).toBe(0);
  expect(glowClip.filter).toBe('none');
  expect(glowClip.backgroundImage).toContain('radial-gradient');

  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expect(alice.getByTestId('home-hero')).toContainText('Hi Alice');
    await expect(alice.getByTestId('home-season-summary')).toContainText('19');
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-97-home-${theme}-390x844.png`),
    });
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-106-home-single-${theme}-390x844.png`),
    });
  }

  // Batch 151: the shared statistic component must stay legible and accessible on the
  // desktop surface as well as the phone hero. The review's 1280 captures are the before
  // evidence; these are the matching after captures from the production bundle.
  await alice.setViewportSize({ width: 1280, height: 800 });
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expect(alice.getByTestId('home-season-summary')).toContainText('19');
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-151-home-${theme}-1280x800.png`),
    });
  }
  await alice.setViewportSize({ width: 390, height: 844 });

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
  // Two leagues, two states, from each league's own summary rather than a shared week.
  await expect(newCard.getByText('Between rounds')).toBeVisible();
  await expect(alice.getByTestId('home-card-the-coupon').getByText('Between rounds')).toBeVisible();
  await alice.screenshot({ path: join(ARTIFACT_DIR, 'home-multi-league.png'), fullPage: true });
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expect(alice.getByTestId('home-league-cards').locator('> li')).toHaveCount(2);
    await expectNoAxeViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-106-home-multi-${theme}-390x844.png`),
    });
  }

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
  // Batch 157 removed averaged rank: league sizes make it a misleading figure.
  // The profile keeps only the meaningful per-league ranks and says why.
  await expect(alice.getByText(/Rank does not average across them/)).toBeVisible();
  await expect(alice.getByTestId('career-league-work-league')).toBeVisible();
  await alice.screenshot({ path: join(ARTIFACT_DIR, 'career-profile.png'), fullPage: true });

  // The per-league record is still its own page, reached from the breakdown.
  await alice.getByTestId('career-league-the-coupon').click();
  await expect(alice.getByTestId('profile-stats')).toContainText('19');
  await expect(alice.getByTestId('profile-history')).toContainText('Arsenal');

  // Batch 150. Registration creates an account but deliberately joins no league. That
  // makes it the production-shaped route into the first-run home state rather than an
  // e2e-only fixture with a different membership contract.
  const firstRunContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const firstRun = await firstRunContext.newPage();
  await firstRun.goto('/register');
  await firstRun.getByLabel('Display name').fill('Nora');
  for (const [index, digit] of [...'4826'].entries()) {
    await firstRun.getByLabel(`Choose a PIN digit ${index + 1}`).fill(digit);
    await firstRun.getByLabel(`Confirm PIN digit ${index + 1}`).fill(digit);
  }
  await firstRun.getByRole('button', { name: 'Create account' }).click();
  await expect(firstRun).toHaveURL('/');
  const firstLeague = firstRun.getByTestId('home-first-league');
  await expect(firstLeague).toBeVisible();
  const discovery = firstRun.getByRole('link', { name: 'Find a league' });
  await expect(discovery).toHaveAttribute('href', '/leagues/discover');
  const discoveryBox = await discovery.boundingBox();
  expect(discoveryBox).not.toBeNull();
  expect(discoveryBox!.height).toBeGreaterThanOrEqual(44);
  const firstLeagueBox = await firstLeague.boundingBox();
  expect(firstLeagueBox).not.toBeNull();
  expect(firstLeagueBox!.y + firstLeagueBox!.height).toBeGreaterThanOrEqual(844);
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(firstRun, theme);
    await expect(firstRun.getByRole('link', { name: 'Find a league' })).toBeVisible();
    await expectNoAxeViolations(firstRun);
    await firstRun.screenshot({
      path: join(ARTIFACT_DIR, `batch-150-first-run-${theme}-390x844.png`),
    });
  }

  // Batch 149. Loading retains the destination's card shape, while a failed request is
  // visibly different from the successful no-league state and can be retried in place.
  let releaseSummary!: () => void;
  const summaryHeld = new Promise<void>((resolve) => {
    releaseSummary = resolve;
  });
  const holdSummary = async (route: Route) => {
    await summaryHeld;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"total_points":0,"picks_played":0,"picks_won":0,"win_rate_pct":null,"leagues_count":0,"per_league":[]}',
    }).catch(() => undefined);
  };
  await firstRun.route('**/api/v1/me/cross-league-summary', holdSummary);
  await firstRun.reload();
  await expect(firstRun.getByTestId('home-league-loading-card').first()).toBeVisible();
  await firstRun.screenshot({
    path: join(ARTIFACT_DIR, 'batch-149-home-loading-light-390x844.png'),
  });
  releaseSummary();
  await firstRun.unroute('**/api/v1/me/cross-league-summary', holdSummary);
  await expect(firstRun.getByTestId('home-first-league')).toBeVisible();

  const failSummary = (route: Route) =>
    route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Unavailable"}' });
  await firstRun.route('**/api/v1/me/cross-league-summary', failSummary);
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(firstRun, theme);
    await expect(firstRun.getByTestId('query-error-state')).toBeVisible();
    await expect(firstRun.getByRole('button', { name: 'Try again' })).toBeVisible();
    await expectNoAxeViolations(firstRun);
    await firstRun.screenshot({
      path: join(ARTIFACT_DIR, `batch-149-home-error-${theme}-390x844.png`),
    });
  }
  await firstRun.unroute('**/api/v1/me/cross-league-summary', failSummary);
  await firstRun.getByRole('button', { name: 'Try again' }).click();
  await expect(firstRun.getByTestId('home-first-league')).toBeVisible();
  await firstRunContext.close();
});
