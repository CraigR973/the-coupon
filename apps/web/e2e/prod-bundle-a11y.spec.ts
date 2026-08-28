import { createRequire } from 'node:module';
import { expect, test, type Page } from '@playwright/test';

// UX-07. `/login` and `/register` are the only two screens that render outside
// `Layout`/`ProtectedRoute`, so they get neither the `<main>` landmark nor the
// `<h1>` every authenticated screen inherits from `PageHeader`. The 2026-08-26
// sweep (`docs/review/2026-08-26/03-ux-accessibility.md`) found three rules
// failing on both, in both themes.
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

async function sweep(page: Page, path: string, theme: 'light' | 'dark'): Promise<AxeSummary> {
  // Seeded before the first paint: ThemeContext reads `coupon_theme` during its
  // initial render, so setting it after navigation would measure the default.
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    ['coupon_theme', theme],
  );
  await page.goto(path);
  await expect(page.locator(`html.${theme}`)).toHaveCount(1);
  await expect(page.locator('form')).toBeVisible();

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
  for (const path of ['/login', '/register']) {
    test(`${path} has a main landmark and a level-one heading (${theme})`, async ({ page }) => {
      const { violations, incomplete } = await sweep(page, path, theme);
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
