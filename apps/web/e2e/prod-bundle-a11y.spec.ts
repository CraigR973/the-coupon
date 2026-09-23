import { createRequire } from 'node:module';
import { expect, test, type Page } from '@playwright/test';

// UX-07 and UX-12. Screens that render outside `Layout`/`ProtectedRoute` get
// neither the `<main>` landmark nor the `<h1>` every authenticated screen
// inherits from `PageHeader`. The 2026-08-26 sweep
// (`docs/review/2026-08-26/03-ux-accessibility.md`) found three rules failing on
// `/login` and `/register`, in both themes, and Batch 86 fixed exactly those two
// — its scope boundary said so. The 2026-09-13 sweep then found the same three
// rules still failing on the four public routes nobody had listed, `/set-pin`
// worst of them, which is where a member lands after an admin clears their PIN.
//
// So this list is now **every public route**, and Batch 137 is the last time it
// should need extending by discovery rather than by adding a route.
//
// This runs in a real browser rather than in the jsdom suite on purpose.
// `landmark-one-main` and `page-has-heading-one` both resolve through axe's
// visibility check, which needs layout; jsdom gives every element zero
// dimensions, so under jsdom axe returns them as `incomplete` — "needs review" —
// for *any* markup, passing and failing alike. A jsdom assertion on these two
// rules would be green whatever the pages contained. `src/test/accessibility.test.tsx`
// keeps a structural check for the same shape; this is the one that reproduces
// what the review measured.
const AXE_PATH = createRequire(import.meta.url).resolve('axe-core');

declare global {
  interface Window {
    axe: typeof import('axe-core');
  }
}

const RULES = ['landmark-one-main', 'page-has-heading-one', 'region'];

interface AxeSummary {
  violations: string[];
  incomplete: string[];
}

/**
 * Every route reachable without a session, with the element that means it has
 * finished rendering. They do not share a shape — two of the six have no form —
 * so readiness is per route rather than a single `form` wait.
 */
const PUBLIC_ROUTES: [string, string][] = [
  ['/login', 'form'],
  ['/register', 'form'],
  ['/forgot-pin', 'form'],
  ['/set-pin', 'form'],
  ['/join/INVITE', 'h1'],
  ['/welcome', 'h1'],
];

async function sweep(
  page: Page,
  path: string,
  ready: string,
  theme: 'light' | 'dark',
): Promise<AxeSummary> {
  // Seeded before the first paint: ThemeContext reads `coupon_theme` during its
  // initial render, so setting it after navigation would measure the default.
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    ['coupon_theme', theme],
  );
  await page.goto(path);
  await expect(page.locator(`html.${theme}`)).toHaveCount(1);
  await expect(page.locator(ready).first()).toBeVisible();

  await page.addScriptTag({ path: AXE_PATH });
  return page.evaluate(async (rules) => {
    const results = await window.axe.run(document.documentElement, {
      runOnly: { type: 'rule', values: rules },
    });
    return {
      violations: results.violations.map((v) => v.id),
      // An `incomplete` here is not a pass. In a real browser these rules only
      // land in `incomplete` when axe genuinely cannot decide, and that is a
      // result worth failing on rather than reading as silence.
      incomplete: results.incomplete.map((v) => v.id),
    };
  }, RULES);
}

for (const theme of ['light', 'dark'] as const) {
  for (const [path, ready] of PUBLIC_ROUTES) {
    test(`${path} has a main landmark and a level-one heading (${theme})`, async ({ page }) => {
      const { violations, incomplete } = await sweep(page, path, ready, theme);
      expect(violations).toEqual([]);
      expect(incomplete).toEqual([]);

      // axe's two landmark rules ask only whether *at least one* exists — a page
      // with three <main>s passes `landmark-one-main`. These pages should have
      // exactly one of each.
      await expect(page.locator('main')).toHaveCount(1);
      await expect(page.locator('h1')).toHaveCount(1);
    });
  }
}
