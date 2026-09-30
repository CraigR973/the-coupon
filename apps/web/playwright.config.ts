import { defineConfig, devices } from '@playwright/test';

// The gate (`scripts/ci-local.sh`) starts both servers itself, proves it owns their
// ports, and names the bundle it built here. Only a hand run (`pnpm e2e`) without it
// gets the managed preview, which may reuse whatever already holds 4173.
const gateWebURL = process.env.COUPON_E2E_WEB_URL;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: gateWebURL ?? 'http://127.0.0.1:4173',
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'coupon-flow',
      testMatch: ['**/coupon-flow.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  ...(gateWebURL
    ? {}
    : {
        webServer: {
          command: 'pnpm preview --host 127.0.0.1 --port 4173',
          url: 'http://127.0.0.1:4173',
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
        },
      }),
});
