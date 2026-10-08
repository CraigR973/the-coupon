import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type Browser, type Locator, type Page, type Route } from '@playwright/test';
import type {
  Coupon,
  CouponLeg,
  FixtureSlate,
  GameweekResult,
  GameweekSlate,
  PlayerProfile,
  SelectionOption,
} from '../src/lib/types';

const API = process.env.COUPON_E2E_API_URL ?? 'http://127.0.0.1:8000';
const ARTIFACT_DIR =
  process.env.COUPON_E2E_ARTIFACT_DIR ??
  '/Users/craigrobinson/the-coupon/artifacts/batch-6';
const AXE_PATH = createRequire(import.meta.url).resolve('axe-core');

declare global {
  interface Window {
    axe: typeof import('axe-core');
    couponLayoutShift?: number;
  }
}

async function setTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((value) => localStorage.setItem('coupon_theme', value), theme);
  await page.reload();
  await expect(page.locator(`html.${theme}`)).toHaveCount(1);
  const transition = page.locator('.animate-page-enter');
  if (await transition.count()) {
    await transition.evaluate(async (node) => {
      await Promise.all(node.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
    });
  }
}

/**
 * Wait until nothing on the page is mid-animation before measuring it. Every route fades
 * in over 220ms (`animate-page-enter`), and after a reload the lazily loaded layout can
 * mount after `setTheme` has already looked for that fade and found none. axe then reads
 * colours through a part-transparent page and the faintest text, the muted captions,
 * drops below AA: CI run 37118741876 failed exactly so on 3 Oct and passed on re-run.
 * Infinite animations (spinners, skeleton pulses) never finish, so only finite ones are
 * awaited, and the loop catches one that starts as another ends.
 */
async function waitForSettledPage(page: Page): Promise<void> {
  const unsettled = await page.evaluate(async () => {
    const running = () =>
      document.getAnimations().filter((animation) => {
        const end = animation.effect?.getComputedTiming().endTime;
        return animation.playState === 'running' && typeof end === 'number' && Number.isFinite(end);
      });
    for (let pass = 0; pass < 10; pass += 1) {
      const animations = running();
      if (animations.length === 0) return 0;
      await Promise.all(animations.map((animation) => animation.finished.catch(() => undefined)));
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }
    return running().length;
  });
  expect(unsettled, 'the page settles before it is measured').toBe(0);
}

async function expectNoColourContrastViolations(page: Page): Promise<void> {
  await waitForSettledPage(page);
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

/**
 * The bottom bar at phone width. Its line sits over the current tab, 12px in from each
 * edge, and every tab keeps a 12px label on one line above a full-size icon. Both went
 * wrong while this journey was taking these exact screenshots — the line drew from the
 * bar's centre, two tabs right, and the labels lost their size class and wrapped — so
 * the bar is measured here rather than only pictured.
 */
async function expectTabBarSettled(page: Page, current: string): Promise<void> {
  const bar = page.getByRole('navigation', { name: 'Primary' });
  const tab = bar.locator('[aria-current="page"]');
  await expect(tab).toHaveCount(1);
  await expect(tab).toContainText(current);
  const line = bar.getByTestId('tabbar-indicator').locator('span');
  // The line slides for 260ms after a route change, so wait for it to come to rest.
  await expect
    .poll(async () => {
      const [tabBox, lineBox] = await Promise.all([tab.boundingBox(), line.boundingBox()]);
      if (!tabBox || !lineBox) return Number.POSITIVE_INFINITY;
      return Math.max(
        Math.abs(lineBox.x - (tabBox.x + 12)),
        Math.abs(lineBox.width - (tabBox.width - 24)),
      );
    })
    .toBeLessThanOrEqual(1);
  const tabs = await bar.locator('li > a, li > button').evaluateAll((nodes) =>
    nodes.map((node) => {
      const label = node.querySelector('span')!;
      const style = getComputedStyle(label);
      return {
        label: label.textContent,
        fontSize: style.fontSize,
        lines: Math.round(label.getBoundingClientRect().height / parseFloat(style.lineHeight)),
        iconHeight: Math.round(node.querySelector('svg')!.getBoundingClientRect().height),
        iconWidth: Math.round(node.querySelector('svg')!.getBoundingClientRect().width),
      };
    }),
  );
  expect(tabs).toHaveLength(5);
  for (const item of tabs) {
    expect(item, `${item.label} tab`).toMatchObject({ fontSize: '12px', lines: 1, iconHeight: 20 });
    expect(item.iconWidth, `${item.label} icon is 20px square`).toBe(20);
  }
}

/** WCAG 2.2 SC 1.4.12's text-spacing override, as the reflow spec applies it. */
const TEXT_SPACING_OVERRIDE =
  '* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; } p { margin-bottom: 2em !important; }';

/**
 * Batch 170. The segmented tabs share the bottom bar's indicator hook, so an unanchored
 * indicator would draw their pill beside the chosen tab just as it drew the bar's line
 * two tabs right. Each tab is chosen in turn and the pill must sit exactly over it.
 */
async function expectSegmentedTabsSettled(page: Page): Promise<void> {
  const list = page.getByRole('tablist');
  const pill = list.getByTestId('tab-indicator');
  for (const name of ['Results', 'Tables']) {
    const tab = list.getByRole('tab', { name });
    await tab.click();
    await expect(tab).toHaveAttribute('aria-selected', 'true');
    await expect
      .poll(async () => {
        const [tabBox, pillBox] = await Promise.all([tab.boundingBox(), pill.boundingBox()]);
        if (!tabBox || !pillBox) return Number.POSITIVE_INFINITY;
        return Math.max(Math.abs(pillBox.x - tabBox.x), Math.abs(pillBox.width - tabBox.width));
      })
      .toBeLessThanOrEqual(1);
  }
}

/**
 * Batch 170. Each home figure is a third of the hero. Its label may wrap but must not be
 * cut, and the three figures stay level whichever labels take two lines.
 */
async function expectHomeFiguresLegible(page: Page): Promise<void> {
  const summary = page.getByTestId('home-season-summary');
  await expect(summary).toBeVisible();
  const figures = await summary.evaluate((list) =>
    Array.from(list.querySelectorAll('dt')).map((term) => ({
      label: term.textContent,
      overflow: term.scrollWidth - term.clientWidth,
      textOverflow: getComputedStyle(term).textOverflow,
      valueTop: Math.round(term.parentElement!.querySelector('dd')!.getBoundingClientRect().top),
    })),
  );
  expect(figures.map((figure) => figure.label)).toEqual(['Points', 'Picks won', 'Win rate']);
  for (const figure of figures) {
    expect(figure.overflow, `${figure.label} fits its card`).toBeLessThanOrEqual(0);
    expect(figure.textOverflow, `${figure.label} is never cut short`).not.toBe('ellipsis');
  }
  expect(new Set(figures.map((figure) => figure.valueTop)).size, 'the figures stay level').toBe(1);
}

/** Batch 170. The standings title is the league's own name, so it wraps rather than cuts. */
async function expectPageTitleWhole(page: Page): Promise<void> {
  const title = page.locator('main h1');
  await expect(title).toBeVisible();
  const fit = await title.evaluate((node) => ({
    overflow: node.scrollWidth - node.clientWidth,
    textOverflow: getComputedStyle(node).textOverflow,
  }));
  expect(fit.overflow, 'the league name fits its heading').toBeLessThanOrEqual(0);
  expect(fit.textOverflow, 'the league name is never cut short').not.toBe('ellipsis');
}

async function expectNoAxeViolations(page: Page): Promise<void> {
  await waitForSettledPage(page);
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

async function expectOneOrderedColumn(first: Locator, second: Locator): Promise<void> {
  await expect.poll(async () => {
    const [firstBox, secondBox] = await Promise.all([first.boundingBox(), second.boundingBox()]);
    if (!firstBox || !secondBox) return Number.POSITIVE_INFINITY;
    return Math.abs(firstBox.x - secondBox.x);
  }, { message: 'rows settle on one left edge' }).toBeLessThanOrEqual(1);
  const [firstBox, secondBox] = await Promise.all([first.boundingBox(), second.boundingBox()]);
  expect(firstBox).not.toBeNull();
  expect(secondBox).not.toBeNull();
  expect(secondBox!.y, 'the second row follows the first').toBeGreaterThanOrEqual(firstBox!.y + firstBox!.height);
}

async function expectFocusedElementUnobscured(page: Page): Promise<void> {
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
  const proof = await page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    if (!element || element === document.body) return null;
    const rect = element.getBoundingClientRect();
    const visibleRect = (candidate: Element | null) => {
      if (!(candidate instanceof HTMLElement)) return null;
      const style = getComputedStyle(candidate);
      if (style.display === 'none' || style.visibility === 'hidden') return null;
      const box = candidate.getBoundingClientRect();
      return box.width > 0 && box.height > 0 ? box : null;
    };
    const headerElement = document.querySelector('header');
    const tabBarElement = document.querySelector('nav[aria-label="Primary"]');
    const header = visibleRect(headerElement);
    const tabBar = visibleRect(tabBarElement);
    const topLimit = headerElement?.contains(element) ? 0 : (header?.bottom ?? 0);
    const bottomLimit = tabBarElement?.contains(element)
      ? window.innerHeight
      : (tabBar?.top ?? window.innerHeight);
    const insetX = Math.min(6, rect.width / 4);
    const insetY = Math.min(6, rect.height / 4);
    const points = [
      [rect.left + rect.width / 2, rect.top + insetY],
      [rect.right - insetX, rect.top + rect.height / 2],
      [rect.left + rect.width / 2, rect.top + rect.height / 2],
      [rect.left + rect.width / 2, rect.bottom - insetY],
      [rect.left + insetX, rect.top + rect.height / 2],
    ];
    const hitTargets = points.map(([x, y]) => {
      const hit = document.elementFromPoint(x, y);
      return {
        covered: hit !== element && (hit === null || !element.contains(hit)),
        target: hit?.getAttribute('aria-label') ?? hit?.textContent?.trim() ?? hit?.tagName ?? null,
      };
    });
    let clippingAncestor: HTMLElement | null = element.parentElement;
    while (clippingAncestor) {
      const overflowX = getComputedStyle(clippingAncestor).overflowX;
      if (overflowX === 'auto' || overflowX === 'scroll') break;
      clippingAncestor = clippingAncestor.parentElement;
    }
    const clippingRect = clippingAncestor?.getBoundingClientRect();
    return {
      label: element.getAttribute('aria-label') ?? element.textContent?.trim() ?? element.tagName,
      top: rect.top,
      bottom: rect.bottom,
      topLimit,
      bottomLimit,
      hitTested: hitTargets.every(({ covered }) => !covered),
      hitTargets,
      shadow: getComputedStyle(element).boxShadow,
      clippingRoom: clippingRect
        ? Math.min(rect.top - clippingRect.top, clippingRect.bottom - rect.bottom)
        : null,
    };
  });

  expect(proof).not.toBeNull();
  expect(proof!.top, `${proof!.label} clears the sticky header`).toBeGreaterThanOrEqual(
    proof!.topLimit - 0.5,
  );
  expect(proof!.bottom, `${proof!.label} clears the fixed tab bar`).toBeLessThanOrEqual(
    proof!.bottomLimit + 0.5,
  );
  expect(
    proof!.hitTested,
    `${proof!.label} is not covered (${JSON.stringify(proof!.hitTargets)})`,
  ).toBe(true);
  if (proof!.clippingRoom !== null) {
    expect(proof!.clippingRoom, `${proof!.label} has room for its focus shadow`).toBeGreaterThanOrEqual(
      5,
    );
  }
}

async function keyboardLoginAndClaim(
  browser: Browser,
  viewport: { width: number; height: number },
): Promise<number> {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  let keystrokes = 0;
  const tab = async () => {
    await page.keyboard.press('Tab');
    keystrokes += 1;
    await expectFocusedElementUnobscured(page);
  };
  const press = async (key: string) => {
    await page.keyboard.press(key);
    keystrokes += 1;
  };
  const type = async (value: string) => {
    await page.keyboard.type(value);
    keystrokes += value.length;
  };

  await page.goto('/login');
  await tab();
  await expect(page.getByLabel('Display name')).toBeFocused();
  await type('Carol');
  await tab();
  await expect(page.getByLabel('PIN digit 1')).toBeFocused();
  for (const [index, digit] of [...'1234'].entries()) {
    await type(digit);
    await expect(page.getByLabel(`PIN digit ${Math.min(index + 2, 4)}`)).toBeFocused();
  }
  await tab();
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeFocused();
  await press('Enter');
  await expect(page).toHaveURL('/');

  const couponDestination =
    viewport.width >= 640
      ? page.getByRole('link', { name: 'Coupon', exact: true })
      : page.getByTestId('home-card-the-coupon').locator('button').first();
  await expect(couponDestination).toBeVisible();
  for (
    let step = 0;
    step < 20 && !(await couponDestination.evaluate((node) => node === document.activeElement));
    step += 1
  ) {
    await tab();
  }
  await expect(couponDestination).toBeFocused();
  await press('Enter');
  await expect(page).toHaveURL('/leagues/the-coupon/predictions');

  const selection = page.getByTestId(/selection-.*-MATCH_ODDS-HOME/);
  await expect(selection).toBeVisible();
  await expect(selection).toHaveAccessibleName(/Arsenal.*1\.90.*win 19 pts/i);
  const scoring = page.getByRole('button', { name: /how scoring works/i });
  let sawScoringGuide = false;
  for (let step = 0; step < 30 && !(await selection.evaluate((node) => node === document.activeElement)); step += 1) {
    await tab();
    if (await scoring.evaluate((node) => node === document.activeElement)) {
      sawScoringGuide = true;
      const shadow = await scoring.evaluate((node) => getComputedStyle(node).boxShadow);
      expect(shadow).not.toBe('none');
    }
  }
  expect(sawScoringGuide).toBe(true);
  await expect(selection).toBeFocused();
  await press('Enter');
  await expect(selection).toHaveAttribute('aria-pressed', 'true');
  await expect(selection).toBeFocused();
  await page.screenshot({
    path: join(ARTIFACT_DIR, `batch-174-keyboard-${viewport.width}x${viewport.height}.png`),
    fullPage: true,
  });
  await context.close();
  return keystrokes;
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
  // keep the normal short failure signal; the journey itself needs headroom for the
  // Batch 173 phone/desktop, light/dark accessibility matrix on a loaded local machine.
  test.setTimeout(240_000);
  mkdirSync(ARTIFACT_DIR, { recursive: true });

  // Batch 174. Rehearse the complete keyboard path at both product widths before
  // resetting the disposable domain for the retained product journey. The review recorded
  // 32 desktop keystrokes against a round with Older gameweek and Copy text controls. This
  // canonical seed has neither, while explicitly focusing Sign in adds one: 31. The phone
  // header omits desktop links, so its equivalent walk is 28.
  for (const viewport of [
    { width: 390, height: 844, keystrokes: 28 },
    { width: 1280, height: 800, keystrokes: 31 },
  ]) {
    const keyboardSeed = await request.post(`${API}/__e2e/seed`);
    expect(keyboardSeed.ok(), await keyboardSeed.text()).toBeTruthy();
    expect(await keyboardLoginAndClaim(browser, viewport)).toBe(viewport.keystrokes);
  }

  // The phone install gate is the only navigable page while it covers sign-in: the
  // instructions own the main landmark and the route underneath is inert.
  const installContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    userAgent:
      'Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36',
  });
  const installPage = await installContext.newPage();
  await installPage.goto('/login');
  await expect(installPage.getByTestId('app-content')).toHaveAttribute('inert', '');
  await expect(
    installPage.getByRole('heading', { level: 1, name: /one saturday pick/i }),
  ).toBeVisible();
  await installPage.addScriptTag({ path: AXE_PATH });
  const installViolations = await installPage.evaluate(async () => {
    const results = await window.axe.run(document.documentElement, {
      runOnly: { type: 'rule', values: ['landmark-one-main', 'region'] },
    });
    return results.violations.map((violation) => violation.id);
  });
  expect(installViolations).toEqual([]);
  await installPage.keyboard.press('Tab');
  expect(
    await installPage.getByTestId('app-content').evaluate((node) => node.contains(document.activeElement)),
  ).toBe(false);
  await installContext.close();

  const seeded = await request.post(`${API}/__e2e/seed`);
  expect(seeded.ok(), await seeded.text()).toBeTruthy();

  const alice = await login(browser, 'Alice');
  let alicePickPosts = 0;
  alice.on('request', (outgoing) => {
    if (outgoing.method() === 'POST' && outgoing.url().endsWith('/api/v1/leagues/the-coupon/picks')) {
      alicePickPosts += 1;
    }
  });

  // Batch 172. The app is already open when the connection disappears. TanStack must
  // let the pick hook see that state immediately: it owns the safe queue because it can
  // tell "never left this device" from "may have landed". Nothing reaches the API while
  // offline; the browser's reconnect event flushes the held intent exactly once.
  await alice.context().setOffline(true);
  await alice.getByRole('button', { name: /Arsenal.*1\.90.*win 19 pts/i }).click();
  await expect(alice.locator('[data-sonner-toast]').last()).toContainText('Saved on this phone');
  await expect(alice.getByTestId('outstanding-pick-notice')).toHaveAttribute('data-state', 'queued');
  expect(alicePickPosts).toBe(0);
  await alice.screenshot({
    path: join(ARTIFACT_DIR, 'batch-172-offline-pick-queued.png'),
    fullPage: true,
  });
  await alice.context().setOffline(false);
  await expect(alice.getByTestId('my-pick-summary')).toContainText('Arsenal');
  expect(alicePickPosts).toBe(1);

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

  // Batch 175. Measure the open pick screen at phone width in both themes, before the
  // seed locks: the first visible price, the larger price type and the keyboard path
  // are the point of the hierarchy change.
  await carol.addInitScript(() => {
    window.couponLayoutShift = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as Array<PerformanceEntry & { value: number; hadRecentInput: boolean }>) {
        if (!entry.hadRecentInput) window.couponLayoutShift! += entry.value;
      }
    }).observe({ type: 'layout-shift', buffered: true });
  });
  await carol.setViewportSize({ width: 390, height: 844 });
  const roundMetrics: Array<{ theme: string; firstPriceY: number; layoutShift: number }> = [];
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(carol, theme);
    await waitForSettledPage(carol);
    const headerRowBox = await carol.locator('header > div').first().boundingBox();
    expect(headerRowBox).not.toBeNull();
    expect(headerRowBox!.height, 'the phone header row is 52px').toBe(52);
    const slate = carol.getByTestId('slate-section');
    const coupon = carol.getByTestId('coupon-section');
    const [slateBox, couponBox] = await Promise.all([slate.boundingBox(), coupon.boundingBox()]);
    expect(slateBox).not.toBeNull();
    expect(couponBox).not.toBeNull();
    expect(slateBox!.y, 'the slate is visually before the coupon on a phone').toBeLessThan(couponBox!.y);
    expect(
      await slate.evaluate((node, couponNode) => Boolean(node.compareDocumentPosition(couponNode) & Node.DOCUMENT_POSITION_FOLLOWING), await coupon.elementHandle()),
      'the slate is before the coupon in the DOM',
    ).toBe(true);

    const price = carol.getByTestId('selection-price').first();
    await expect(price).toBeVisible();
    const priceBox = await price.boundingBox();
    expect(priceBox).not.toBeNull();
    expect(priceBox!.y, 'first price from the top at 390px').toBeLessThanOrEqual(480);
    expect(await price.evaluate((node) => ({
      size: getComputedStyle(node).fontSize,
      lineHeight: getComputedStyle(node).lineHeight,
      weight: getComputedStyle(node).fontWeight,
    }))).toEqual({ size: '17px', lineHeight: '20px', weight: '600' });
    expect(await carol.getByTestId('selection-label').first().evaluate((node) => getComputedStyle(node).fontSize)).toBe('14px');
    const firstButton = price.locator('xpath=..');
    const buttonBox = await firstButton.boundingBox();
    expect(buttonBox).not.toBeNull();
    expect(buttonBox!.width).toBeGreaterThanOrEqual(44);
    expect(buttonBox!.height).toBeGreaterThanOrEqual(56);
    const undersizedTargets = await carol.locator('main a, main button').evaluateAll((nodes) =>
      nodes.flatMap((node) => {
        const box = node.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) return [];
        return box.width < 24 || box.height < 24
          ? [`${node.getAttribute('aria-label') ?? node.textContent?.trim()}: ${Math.round(box.width)}x${Math.round(box.height)}`]
          : [];
      }),
    );
    expect(undersizedTargets, 'round controls are at least 24px in both dimensions').toEqual([]);
    await carol.screenshot({ path: join(ARTIFACT_DIR, `batch-175-round-open-${theme}-390x844.png`) });

    await carol.getByRole('link', { name: 'Jump to coupon' }).focus();
    let sawSelection = false;
    let reachedCoupon = false;
    for (let tab = 0; tab < 60; tab += 1) {
      await carol.keyboard.press('Tab');
      const focused = await carol.evaluate(() => document.activeElement?.getAttribute('data-testid'));
      if (focused?.startsWith('selection-')) sawSelection = true;
      if (focused === 'coupon-toggle') {
        reachedCoupon = true;
        break;
      }
    }
    expect(sawSelection, 'keyboard reaches a selection before the coupon').toBe(true);
    expect(reachedCoupon, 'keyboard can reach the coupon').toBe(true);
    await expectNoAxeViolations(carol);
    const layoutShift = await carol.evaluate(() => window.couponLayoutShift ?? 0);
    expect(layoutShift, 'round layout shift is below the previous 0.247').toBeLessThan(0.247);
    roundMetrics.push({ theme, firstPriceY: Math.round(priceBox!.y), layoutShift });
  }
  await carol.route('**/api/v1/leagues/the-coupon/gameweeks', async (route) => {
    const response = await route.fetch();
    const gameweeks = (await response.json()) as Array<{ gameweek_id: string; starts_on: string }>;
    await route.fulfill({
      response,
      json: [
        ...gameweeks,
        { ...gameweeks[0], gameweek_id: 'older-layout-proof', starts_on: '2026-07-25' },
      ],
    });
  });
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(carol, theme);
    await expect(carol.getByTestId('gameweek-nav')).toBeVisible();
    const priceBox = await carol.getByTestId('selection-price').first().boundingBox();
    expect(priceBox).not.toBeNull();
    expect(priceBox!.y, 'first price with round history at 390px').toBeLessThanOrEqual(480);
    roundMetrics.push({ theme: `${theme}-with-history`, firstPriceY: Math.round(priceBox!.y), layoutShift: await carol.evaluate(() => window.couponLayoutShift ?? 0) });
    await carol.screenshot({ path: join(ARTIFACT_DIR, `batch-175-round-history-${theme}-390x844.png`) });
  }
  await carol.unroute('**/api/v1/leagues/the-coupon/gameweeks');
  await carol.reload();
  writeFileSync(join(ARTIFACT_DIR, 'batch-175-round-metrics.json'), JSON.stringify(roundMetrics, null, 2));

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
    await expectTabBarSettled(alice, 'Leagues');
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
    await alice.evaluate(() => window.scrollTo(0, 400));
    const chromeFill = await alice.locator('header').first().evaluate((header) => {
      const expected = document.createElement('span');
      expected.style.backgroundColor = 'var(--surface)';
      document.body.append(expected);
      const fill = getComputedStyle(expected).backgroundColor;
      expected.remove();
      return {
        expected: fill,
        header: getComputedStyle(header).backgroundColor,
        tabBar: getComputedStyle(document.querySelector('nav[aria-label="Primary"]')!).backgroundColor,
      };
    });
    expect(chromeFill.header).toBe(chromeFill.expected);
    expect(chromeFill.tabBar).toBe(chromeFill.expected);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-171-solid-chrome-${theme}-390x844.png`),
    });
    await alice.evaluate(() => window.scrollTo(0, 0));
  }

  // Batch 105: the combined coupon's own address is a redirect into the round that
  // carries it. A link minted before the merge has to land on the copy section, at the
  // week it named — this is the assertion that saved links and notification taps still
  // reach what they were pointing at.
  await alice.goto('/leagues/the-coupon/predictions/coupon');
  await expect(alice).toHaveURL('/leagues/the-coupon/predictions#coupon');
  await expect(alice.getByTestId('coupon-section')).toBeVisible();
  await expect(alice.getByTestId('coupon-result-headline')).toHaveText(
    'Coupon won · 2 of 2 landed',
  );
  await expect(alice.getByText('4.56')).toBeVisible();
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
    await expectTabBarSettled(alice, 'Coupon');
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
      alice.getByTestId('slate-section'),
      alice.getByRole('complementary', { name: 'Round status and coupon' }),
    );
    const [slateBox, couponBox] = await Promise.all([
      alice.getByTestId('slate-section').boundingBox(),
      alice.getByTestId('coupon-section').boundingBox(),
    ]);
    expect(slateBox).not.toBeNull();
    expect(couponBox).not.toBeNull();
    expect(slateBox!.x).toBeLessThan(couponBox!.x);
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-140-round-${theme}-1280x800.png`),
    });
  }

  // Batch 173. The production-shaped journey has three active members and two winning
  // legs. Route the two already-authenticated reads through a settled presentation
  // fixture so the browser also proves the states production history can carry but this
  // small seed cannot: a void leg, a departed member and an erased member. The app still
  // joins the slate to the coupon exactly as it does in production; only the response
  // bodies are widened for this visual contract.
  const visualSeed = (await alice.evaluate(async (api) => {
    const token = localStorage.getItem('coupon_access');
    const headers = { Authorization: `Bearer ${token}` };
    const [slateResponse, couponResponse] = await Promise.all([
      fetch(`${api}/api/v1/leagues/the-coupon/gameweek/current`, { headers }),
      fetch(`${api}/api/v1/leagues/the-coupon/coupon`, { headers }),
    ]);
    return {
      slate: await slateResponse.json(),
      coupon: await couponResponse.json(),
    };
  }, API)) as { slate: GameweekSlate; coupon: Coupon };

  const primaryFixture = visualSeed.slate.fixtures.find(
    (fixture) => fixture.selections.length >= 3,
  );
  const secondaryFixture = visualSeed.slate.fixtures.find(
    (fixture) => fixture.fixture_id !== primaryFixture?.fixture_id && fixture.selections.length > 0,
  );
  expect(primaryFixture).toBeDefined();
  expect(secondaryFixture).toBeDefined();
  const [homeSelection, drawSelection, awaySelection] = primaryFixture!.selections;
  const bobSelection = secondaryFixture!.selections.find((selection) =>
    ['DRAW', 'AWAY', 'NO'].includes(selection.outcome),
  );
  expect(bobSelection).toBeDefined();
  const aliceLeg = visualSeed.coupon.legs.find((leg) => leg.player_name === 'Alice');
  const bobLeg = visualSeed.coupon.legs.find((leg) => leg.player_name === 'Bob');
  expect(aliceLeg).toBeDefined();
  expect(bobLeg).toBeDefined();

  const visualLeg = (
    fixture: FixtureSlate,
    selection: SelectionOption,
    playerId: string,
    playerName: string,
    status: CouponLeg['status'],
    points: number | null,
  ): CouponLeg => ({
    player_id: playerId,
    player_name: playerName,
    fixture_id: fixture.fixture_id,
    home: fixture.home,
    away: fixture.away,
    competition: fixture.competition,
    market: selection.market,
    outcome: selection.outcome,
    runner_name: selection.runner_name,
    odds: selection.odds,
    status,
    points_awarded: points,
    home_goals: status === 'void' ? null : 2,
    away_goals: status === 'void' ? null : 1,
    score_is_final: true,
  });
  const visualLegs: CouponLeg[] = [
    visualLeg(
      primaryFixture!,
      homeSelection,
      aliceLeg!.player_id,
      'Alice',
      'won',
      Math.round(homeSelection.odds * 10),
    ),
    visualLeg(primaryFixture!, drawSelection, 'departed-player', 'Dana Departed', 'lost', 0),
    visualLeg(primaryFixture!, awaySelection, 'erased-player', 'Former member', 'void', 0),
    visualLeg(secondaryFixture!, bobSelection!, bobLeg!.player_id, 'Bob', 'lost', 0),
  ];
  const visualCombinedOdds = Number(
    visualLegs
      .filter((leg) => leg.status !== 'void')
      .reduce((product, leg) => product * leg.odds, 1)
      .toFixed(2),
  );
  const assignmentKey = (fixtureId: string, selection: SelectionOption) =>
    `${fixtureId}:${selection.market}:${selection.outcome}`;
  const visualAssignments = new Map(
    visualLegs.map((leg) => [
      `${leg.fixture_id}:${leg.market}:${leg.outcome}`,
      { playerId: leg.player_id, playerName: leg.player_name },
    ]),
  );

  let settledSlateHits = 0;
  let settledCouponHits = 0;
  const settledSlateRoute = async (route: Route) => {
    settledSlateHits += 1;
    const response = await route.fetch();
    const slate = (await response.json()) as GameweekSlate;
    await route.fulfill({
      response,
      json: {
        ...slate,
        fixtures: slate.fixtures.map((fixture) => {
          const assignedNames = new Set<string>();
          const selections = fixture.selections.map((selection) => {
            const assignment = visualAssignments.get(assignmentKey(fixture.fixture_id, selection));
            if (!assignment) {
              return {
                ...selection,
                taken_by_player_id: null,
                taken_by_name: null,
                mine: false,
              };
            }
            assignedNames.add(assignment.playerName);
            return {
              ...selection,
              taken_by_player_id: assignment.playerId,
              taken_by_name: assignment.playerName,
              mine: assignment.playerId === aliceLeg!.player_id,
            };
          });
          return {
            ...fixture,
            selections,
            taken_by_names: [...assignedNames],
            mine: selections.some((selection) => selection.mine),
          };
        }),
      },
    });
  };
  const settledCouponRoute = async (route: Route) => {
    settledCouponHits += 1;
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: {
        ...visualSeed.coupon,
        status: 'settled',
        leg_count: visualLegs.length,
        combined_odds: visualCombinedOdds,
        legs: visualLegs,
        all_won: false,
        void_leg_count: 1,
      } satisfies Coupon,
    });
  };
  const settledSlatePattern = /\/api\/v1\/leagues\/the-coupon\/gameweek\/current(?:\?.*)?$/;
  const settledCouponPattern = /\/api\/v1\/leagues\/the-coupon\/coupon(?:\?.*)?$/;
  const aliceContext = alice.context();
  await aliceContext.route(settledSlatePattern, settledSlateRoute);
  await aliceContext.route(settledCouponPattern, settledCouponRoute);
  await alice.reload();
  await expect.poll(() => settledSlateHits).toBeGreaterThan(0);
  await expect.poll(() => settledCouponHits).toBeGreaterThan(0);
  const resultHeadline = alice.getByTestId('coupon-result-headline');
  await expect(resultHeadline).toHaveText('Coupon lost · 1 of 4 landed');
  await expect(alice.getByTestId('coupon-toggle')).toContainText('4 picks');
  await expect(alice.getByTestId('coupon-toggle')).not.toContainText('4 of 3');
  await expect(alice.getByTestId('coupon-section')).toContainText('Dana Departed');
  await expect(alice.getByTestId('coupon-section')).toContainText('Former member');
  await expect(
    alice.getByTestId(
      `selection-${primaryFixture!.fixture_id}-${drawSelection.market}-${drawSelection.outcome}`,
    ),
  ).toContainText('Lost · Dana');
  const voidSelection = alice.getByTestId(
    `selection-${primaryFixture!.fixture_id}-${awaySelection.market}-${awaySelection.outcome}`,
  );
  await expect(voidSelection).toContainText('Void · Former member');
  await expect(voidSelection).not.toContainText(/\d+ pts/);

  for (const viewport of [
    { width: 390, height: 844 },
    { width: 1280, height: 800 },
  ]) {
    await alice.setViewportSize(viewport);
    for (const theme of ['dark', 'light'] as const) {
      await setTheme(alice, theme);
      await expect(resultHeadline).toHaveText('Coupon lost · 1 of 4 landed');
      await expectNoColourContrastViolations(alice);
      await expectNoAxeViolations(alice);
      await alice.screenshot({
        path: join(
          ARTIFACT_DIR,
          `batch-173-settled-${theme}-${viewport.width}x${viewport.height}.png`,
        ),
        fullPage: true,
      });
    }
  }

  let showVoidOnlyProfile = false;
  const voidOnlyProfileRoute = async (route: Route) => {
    const response = await route.fetch();
    const profile = (await response.json()) as PlayerProfile;
    await route.fulfill({
      response,
      json: {
        ...profile,
        total_points: 0,
        picks_played: showVoidOnlyProfile ? 1 : 2,
        picks_won: 0,
        win_rate_pct: showVoidOnlyProfile ? null : 0,
        picks_priced: showVoidOnlyProfile ? 0 : 1,
        cumulative_odds: showVoidOnlyProfile ? 0 : visualLegs[3].odds,
        average_odds: showVoidOnlyProfile ? null : visualLegs[3].odds,
        points_per_pick: 0,
        best_return: showVoidOnlyProfile ? null : 0,
        longshot_picks: showVoidOnlyProfile || visualLegs[3].odds < 3 ? 0 : 1,
        favourite_picks: showVoidOnlyProfile || visualLegs[3].odds >= 3 ? 0 : 1,
        longshot_odds: 3,
        history: [
          {
            gameweek_id: visualSeed.coupon.gameweek_id,
            starts_on: visualSeed.slate.starts_on,
            fixture_id: visualLegs[2].fixture_id,
            home: visualLegs[2].home,
            away: visualLegs[2].away,
            competition: visualLegs[2].competition,
            market: visualLegs[2].market,
            outcome: visualLegs[2].outcome,
            runner_name: visualLegs[2].runner_name,
            odds: visualLegs[2].odds,
            status: 'void',
            points_awarded: 0,
          },
          ...(!showVoidOnlyProfile
            ? [
                {
                  gameweek_id: 'batch-173-previous',
                  starts_on: '2026-08-01',
                  fixture_id: visualLegs[3].fixture_id,
                  home: visualLegs[3].home,
                  away: visualLegs[3].away,
                  competition: visualLegs[3].competition,
                  market: visualLegs[3].market,
                  outcome: visualLegs[3].outcome,
                  runner_name: visualLegs[3].runner_name,
                  odds: visualLegs[3].odds,
                  status: 'lost',
                  points_awarded: 0,
                } as const,
              ]
            : []),
        ],
      } satisfies PlayerProfile,
    });
  };
  const aliceProfilePattern = new RegExp(
    `/api/v1/leagues/the-coupon/players/${aliceLeg!.player_id}/profile(?:\\?.*)?$`,
  );
  await aliceContext.route(aliceProfilePattern, voidOnlyProfileRoute);
  await alice.goto(`/leagues/the-coupon/players/${aliceLeg!.player_id}`);
  const lostHistory = alice.getByTestId(`history-${visualLegs[3].fixture_id}`);
  await expect(lostHistory).toContainText('Lost');
  await expect(lostHistory).not.toHaveClass(/opacity-60/);
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 1280, height: 800 },
  ]) {
    await alice.setViewportSize(viewport);
    for (const theme of ['dark', 'light'] as const) {
      await setTheme(alice, theme);
      await expect(alice.getByTestId('profile-stats')).toContainText('0%');
      await expectNoColourContrastViolations(alice);
      await expectNoAxeViolations(alice);
      await alice.screenshot({
        path: join(
          ARTIFACT_DIR,
          `batch-173-profile-${theme}-${viewport.width}x${viewport.height}.png`,
        ),
        fullPage: true,
      });
    }
  }
  showVoidOnlyProfile = true;
  await alice.reload();
  await expect(alice.getByText('Only void picks so far — no win rate yet')).toBeVisible();
  await expectNoColourContrastViolations(alice);
  await aliceContext.unroute(aliceProfilePattern, voidOnlyProfileRoute);
  await aliceContext.unroute(settledSlatePattern, settledSlateRoute);
  await aliceContext.unroute(settledCouponPattern, settledCouponRoute);

  await alice.goto('/leagues/the-coupon/leaderboard');
  const standings = alice.getByTestId('standings');
  await expect(standings).toContainText('Bob');
  await expect(standings.locator('> li')).toHaveCount(3);
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expectOneOrderedColumn(standings.locator('> li').first(), standings.locator('> li').nth(1));
    await expect(alice.getByText('Played', { exact: true })).toBeVisible();
    await expect(alice.getByText('Avg odds', { exact: true })).toBeVisible();
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-140-standings-${theme}-1280x800.png`),
    });
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-176-standings-${theme}-1280x800.png`),
    });
  }

  await alice.setViewportSize({ width: 390, height: 844 });
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    const rows = standings.locator('> li');
    await expectOneOrderedColumn(rows.first(), rows.nth(1));
    const firstBox = await rows.first().boundingBox();
    expect(firstBox?.height, 'phone standing rows are 52px').toBe(52);
    const pointType = await rows.first().getByTestId('standing-points').evaluate((node) => ({
      size: getComputedStyle(node).fontSize,
      weight: getComputedStyle(node).fontWeight,
    }));
    expect(pointType).toEqual({ size: '17px', weight: '600' });
    expect((await rows.first().getByTestId('rank-medal').boundingBox())?.width).toBe(3);
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-176-standings-${theme}-390x844.png`),
    });
  }

  await alice.setViewportSize({ width: 1280, height: 800 });
  const resultsPattern = '**/api/v1/leagues/the-coupon/results';
  await aliceContext.route(resultsPattern, async (route) => {
    const response = await route.fetch();
    const rows = (await response.json()) as GameweekResult[];
    expect(rows.length).toBeGreaterThan(0);
    await route.fulfill({
      response,
      json: [rows[0], { ...rows[0], gameweek_id: 'older-ranking-proof', starts_on: '2026-07-25', season_week: '1a' }],
    });
  });

  await alice.goto('/leagues/the-coupon/predictions/results');
  const results = alice.getByTestId('results-list');
  await expect(results).toContainText('Bob');
  await expect(results.locator('> li')).toHaveCount(2);
  await expect(results.locator('> li').first()).toContainText('Gameweek 1b');
  await expect(results.locator('> li').nth(1)).toContainText('Gameweek 1a');
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expectOneOrderedColumn(results.locator('> li').first(), results.locator('> li').nth(1));
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-176-season-${theme}-1280x800.png`),
    });
  }
  await alice.setViewportSize({ width: 390, height: 844 });
  for (const theme of ['dark', 'light'] as const) {
    await setTheme(alice, theme);
    await expectOneOrderedColumn(results.locator('> li').first(), results.locator('> li').nth(1));
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-176-season-${theme}-390x844.png`),
    });
  }
  await aliceContext.unroute(resultsPattern);
  await alice.setViewportSize({ width: 1280, height: 800 });

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

  // Batch 170. At exactly 1280 @ 200% the brand, five links and the account menu did not
  // fit: every signed-in page scrolled 47px sideways and the menu sat past the right edge.
  // Below `md` Settings is left to the account menu and Football Stats reads Football; the
  // name beside the avatar waits for `lg`. 768 is the same display at about 167%, the
  // narrowest width that shows all five links in full.
  for (const [width, linkCount] of [[768, 5], [640, 4]] as const) {
    await alice.setViewportSize({ width, height: 400 });
    for (const path of ['/', '/leagues/the-coupon/predictions', '/leagues/the-coupon/leaderboard']) {
      await alice.goto(path);
      const nav = alice.getByRole('navigation', { name: 'Main navigation' });
      await expect(nav.getByRole('link', { name: 'Football Stats' })).toHaveText(
        width < 768 ? 'Football' : 'Football Stats',
        { useInnerText: true },
      );
      const fit = await alice.evaluate(() => {
        const header = document.querySelector('header')!;
        return {
          page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          header: header.scrollWidth - header.clientWidth,
          linkHeights: Array.from(header.querySelectorAll('nav[aria-label="Main navigation"] a'))
            .filter((link) => getComputedStyle(link).display !== 'none')
            .map((link) => Math.round(link.getBoundingClientRect().height)),
        };
      });
      expect(fit.page, `${path} at ${width} does not scroll sideways`).toBe(0);
      expect(fit.header, `${path} at ${width} header fits`).toBe(0);
      expect(fit.linkHeights, `${path} at ${width} link count`).toHaveLength(linkCount);
      expect(new Set(fit.linkHeights).size, `${path} at ${width} links on one line`).toBe(1);
    }
  }
  const accountMenu = alice.getByRole('button', { name: 'Account menu (Alice)' });
  const accountBox = await accountMenu.boundingBox();
  expect(accountBox).not.toBeNull();
  expect(accountBox!.x + accountBox!.width).toBeLessThanOrEqual(640);
  await accountMenu.click();
  await expect(alice.getByRole('menuitem', { name: 'Settings' })).toBeVisible();
  await expect(alice.getByRole('menuitem', { name: 'Log out' })).toBeVisible();
  await alice.keyboard.press('Escape');
  await expect(alice.getByRole('menuitem', { name: 'Log out' })).toBeHidden();
  await alice.screenshot({ path: join(ARTIFACT_DIR, 'batch-170-zoom-header-640x400.png') });

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
    await expectTabBarSettled(alice, 'Home');
    await expectNoAxeViolations(alice);
    await expectNoColourContrastViolations(alice);
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-97-home-${theme}-390x844.png`),
    });
    await alice.screenshot({
      path: join(ARTIFACT_DIR, `batch-106-home-single-${theme}-390x844.png`),
    });
  }

  // Batch 170: the fifth tab, and the segmented control that shares the bar's indicator.
  await alice.goto('/football');
  await expectTabBarSettled(alice, 'Football');
  await expectSegmentedTabsSettled(alice);
  await alice.goto('/');

  // The old "Football Stats" label only just fit at 390px and wrapped in a 64px tab at
  // the WCAG reflow width. Enlarged text spacing must not bring the two-line, crushed-icon
  // failure back either.
  await alice.setViewportSize({ width: 320, height: 720 });
  await alice.addStyleTag({
    content: '* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }',
  });
  await expectTabBarSettled(alice, 'Home');

  // Batch 170. The home figures and the standings title at the reflow width and at 390,
  // with and without the text-spacing override: either may wrap, neither may be cut.
  for (const width of [320, 390]) {
    await alice.setViewportSize({ width, height: 720 });
    for (const spaced of [false, true]) {
      await alice.goto('/');
      if (spaced) await alice.addStyleTag({ content: TEXT_SPACING_OVERRIDE });
      await expectHomeFiguresLegible(alice);
      await alice.screenshot({
        path: join(ARTIFACT_DIR, `batch-170-home-${width}${spaced ? '-spaced' : ''}.png`),
      });
      await alice.goto('/leagues/the-coupon/leaderboard');
      if (spaced) await alice.addStyleTag({ content: TEXT_SPACING_OVERRIDE });
      await expectPageTitleWhole(alice);
    }
  }
  await alice.goto('/');

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
  // Batch 170: the segmented tabs at desktop width too, where the bottom bar is gone.
  await alice.goto('/football');
  await expectSegmentedTabsSettled(alice);
  await alice.goto('/');
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
  await expectTabBarSettled(alice, 'More');
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
