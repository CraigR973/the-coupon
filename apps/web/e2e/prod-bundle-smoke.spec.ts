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
});
