import { expect, test } from '@playwright/test';

test('production bundle serves deep links through the SPA shell', async ({ page }) => {
  await page.goto('/settings');
  await expect(page).toHaveURL('/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();

  await page.goto('/forgot-pin');
  await expect(page.getByRole('heading', { name: 'Reset PIN' })).toBeVisible();
});
