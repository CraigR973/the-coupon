import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

test('the installed-app manifest serves both screenshots and a separate maskable icon', async ({ request }) => {
  const response = await request.get('/manifest.webmanifest');
  expect(response.ok()).toBe(true);
  const manifest = await response.json();
  expect(manifest.id).toBe('/');
  expect(manifest.theme_color).toBe('#0B0E13');
  expect(manifest.background_color).toBe('#0B0E13');
  expect(manifest.icons).toContainEqual({
    src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable',
  });
  expect(manifest.screenshots).toEqual([
    { src: '/screenshots/login-phone.png', sizes: '390x844', type: 'image/png', form_factor: 'narrow', label: 'The Coupon sign-in on a phone' },
    { src: '/screenshots/login-desktop.png', sizes: '1280x800', type: 'image/png', form_factor: 'wide', label: 'The Coupon sign-in on a desktop' },
  ]);

  for (const screenshot of manifest.screenshots) {
    const asset = await request.get(screenshot.src);
    expect(asset.ok(), screenshot.src).toBe(true);
    expect(asset.headers()['content-type']).toContain('image/png');
    const png = await asset.body();
    expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
    expect(`${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`).toBe(screenshot.sizes);
  }

  const config = JSON.parse(readFileSync('vercel.json', 'utf8'));
  // Vercel matches its route pattern from the start; a loose JS search would
  // incorrectly match the second slash inside /screenshots/.
  const rewrite = new RegExp(`^${config.rewrites[0].source}$`);
  expect(rewrite.test('/screenshots/login-phone.png')).toBe(false);
  expect(rewrite.test('/admin/dashboard')).toBe(true);
});

test('stored and system themes activate exactly one matching status-bar colour', async ({ page }) => {
  await page.goto('/login');
  await expect(page.locator('html.dark')).toHaveCount(1);
  await expect(page.locator('meta[name="theme-color"][data-theme="dark"]')).toHaveAttribute('media', 'all');
  await expect(page.locator('meta[name="theme-color"][data-theme="light"]')).toHaveAttribute('media', 'not all');
  await expect(page.locator('meta[name="apple-mobile-web-app-status-bar-style"]')).toHaveAttribute('content', 'default');

  await page.evaluate(() => localStorage.setItem('coupon_theme', 'light'));
  await page.reload();
  await expect(page.locator('html.light')).toHaveCount(1);
  await expect(page.locator('meta[name="theme-color"][data-theme="dark"]')).toHaveAttribute('media', 'not all');
  await expect(page.locator('meta[name="theme-color"][data-theme="light"]')).toHaveAttribute('media', 'all');

  await page.emulateMedia({ colorScheme: 'light' });
  await page.evaluate(() => localStorage.setItem('coupon_theme', 'system'));
  await page.reload();
  await expect(page.locator('html.light')).toHaveCount(1);
  await expect(page.locator('meta[name="theme-color"][data-theme="light"]')).toHaveAttribute('media', 'all');
});

test('every coloured maskable-icon pixel fits the guaranteed safe circle', async ({ page }) => {
  await page.goto('/login');
  const geometry = await page.evaluate(async () => {
    const icon = new Image();
    icon.src = '/icon-maskable-512.png';
    await icon.decode();
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 512;
    const context = canvas.getContext('2d')!;
    context.drawImage(icon, 0, 0);
    const pixels = context.getImageData(0, 0, 512, 512).data;
    let maxRadius = 0;
    let minAlpha = 255;
    let coloured = 0;
    for (let y = 0; y < 512; y += 1) {
      for (let x = 0; x < 512; x += 1) {
        const offset = (y * 512 + x) * 4;
        minAlpha = Math.min(minAlpha, pixels[offset + 3]);
        if (Math.max(
          Math.abs(pixels[offset] - 11),
          Math.abs(pixels[offset + 1] - 14),
          Math.abs(pixels[offset + 2] - 19),
        ) > 12) {
          coloured += 1;
          maxRadius = Math.max(maxRadius, Math.hypot(x - 255.5, y - 255.5));
        }
      }
    }
    return { maxRadius, minAlpha, coloured };
  });
  expect(geometry.coloured).toBeGreaterThan(0);
  expect(geometry.minAlpha).toBe(255);
  expect(geometry.maxRadius).toBeLessThanOrEqual(512 * 0.4);
});
