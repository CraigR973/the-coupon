import { defineConfig, devices } from "@playwright/test";
if (!process.env.COUPON_TWO_GAME_WEB_URL)
  throw new Error("Use scripts/verify-two-game-web.py with isolated servers");
export default defineConfig({
  testDir: "./e2e",
  testMatch: ["**/two-game-group.spec.ts"],
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: process.env.COUPON_TWO_GAME_WEB_URL,
    serviceWorkers: "block",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "phone",
      use: { ...devices["iPhone 13"], browserName: "chromium" },
    },
  ],
});
