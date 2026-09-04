import { expect, test } from '@playwright/test';

test('production bundle serves deep links through the SPA shell', async ({ page }) => {
  await page.goto('/settings');
  await expect(page).toHaveURL('/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();

  await page.goto('/forgot-pin');
  await expect(page.getByRole('heading', { name: 'Reset PIN' })).toBeVisible();

  // Batch 30's whole point is that a league's coupon has a shareable address, and
  // it is a segment deeper than anything the rewrite carried before. A shared link
  // that 404s at the CDN never reaches the router to be redirected.
  await page.goto('/leagues/the-coupon/predictions/coupon?gw=abc');
  await expect(page).toHaveURL('/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();

  // Batch 105 gave that link a fragment as well as a query, because the combined coupon
  // is a section of the round now. The rewrite has to carry both to the SPA shell.
  await page.goto('/leagues/the-coupon/predictions?gw=abc#coupon');
  await expect(page).toHaveURL('/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();

  // Batch 66. The far end of a PIN reset is a *public* route — the member arrives with
  // no credential, which is the whole state — so it has to render for a signed-out
  // browser rather than bouncing to /login like everything else here.
  await page.goto('/set-pin?name=Lewis');
  await expect(page.getByRole('heading', { name: 'Choose a new PIN' })).toBeVisible();

  // And the admin console is the opposite: authenticated *and* role-gated, so a
  // signed-out deep link lands on sign-in rather than on an empty console.
  await page.goto('/admin/players');
  await expect(page).toHaveURL('/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
});
