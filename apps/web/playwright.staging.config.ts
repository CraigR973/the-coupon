import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.COUPON_E2E_WEB_URL;
if (!baseURL?.startsWith('https://')) {
  throw new Error('COUPON_E2E_WEB_URL must be the explicit HTTPS staging origin');
}

export default defineConfig({
  testDir: './e2e',
  testMatch: ['**/staging-flow.spec.ts'],
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  timeout: 90_000,
  reporter: 'line',
  outputDir: process.env.COUPON_E2E_OUTPUT_DIR ?? 'test-results/staging',
  use: {
    baseURL,
    serviceWorkers: 'allow',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'staging-chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
