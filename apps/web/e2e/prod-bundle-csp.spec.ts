import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { expect, test, type Page } from '@playwright/test';

// Batch 141. A policy that has never been run is a guess. `vercel.json` is not applied
// by `vite preview`, so this spec reads the shipped policy out of that file and puts it
// on the document response itself, then loads every public route under it and fails on
// any violation the browser reports.
//
// The one deliberate difference from production: `connect-src` gains the invalid origin
// the prod-bundle build points at. `ci-local.sh` builds with
// `VITE_API_URL=https://api.example.invalid`, so without this a blocked request to a
// host that does not exist would read as a policy defect rather than a test fixture.
// Everything else is byte-for-byte what Vercel serves.

const require_ = createRequire(import.meta.url);
const VERCEL = JSON.parse(
  readFileSync(require_.resolve('../vercel.json'), 'utf8'),
) as { headers: { source: string; headers: { key: string; value: string }[] }[] };

const SHIPPED = VERCEL.headers
  .find((entry) => entry.source === '/(.*)')!
  .headers.find((entry) => entry.key === 'Content-Security-Policy')!.value;

const PREVIEW_API = 'https://api.example.invalid';
const POLICY = SHIPPED.replace('connect-src ', `connect-src ${PREVIEW_API} `);

const ROUTES = ['/login', '/register', '/forgot-pin', '/set-pin', '/join/INVITE', '/welcome'];

// Every test here installs a `page.route` handler that re-fetches the document to add
// the policy header. A font or asset request can still be in that handler when the test
// body finishes, and closing the page underneath it fails the test with
// "Target page, context or browser has been closed" — which is a flaky gate rather than
// a finding. Draining the routes first is Playwright's own answer.
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});

interface Violation {
  directive: string;
  blocked: string;
}

/** Serve every document under the shipped policy and collect what it refuses. */
async function underPolicy(page: Page): Promise<Violation[]> {
  const violations: Violation[] = [];
  await page.exposeFunction('__cspViolation', (directive: string, blocked: string) => {
    violations.push({ directive, blocked });
  });
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      void (
        window as unknown as {
          __cspViolation: (directive: string, blocked: string) => void;
        }
      ).__cspViolation(event.effectiveDirective, event.blockedURI);
    });
  });
  await page.route('**/*', async (route) => {
    const response = await route.fetch();
    const headers = { ...response.headers() };
    if ((headers['content-type'] ?? '').includes('text/html')) {
      headers['content-security-policy'] = POLICY;
    }
    await route.fulfill({ response, headers });
  });
  return violations;
}

for (const path of ROUTES) {
  test(`${path} loads clean under the shipped CSP`, async ({ page }) => {
    const violations = await underPolicy(page);
    const consoleErrors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });

    await page.goto(path);
    await expect(page.locator('main')).toBeVisible();
    // The theme script is the hashed one, and it runs before anything else. If the hash
    // were wrong this is what would be missing, silently, in production.
    await expect(page.locator('html.dark, html.light')).toHaveCount(1);
    // Give anything deferred a chance to be refused before the assertions below.
    await page.waitForTimeout(500);

    expect(violations, `CSP violations on ${path}`).toEqual([]);
    expect(
      consoleErrors.filter((text) => /content security policy/i.test(text)),
      `CSP console errors on ${path}`,
    ).toEqual([]);
  });
}

test('the policy actually reaches the document', async ({ page }) => {
  // Guards the guard: if the route interception stopped applying the header, every test
  // above would pass by testing nothing at all.
  await underPolicy(page);
  const response = await page.goto('/login');
  expect(response?.headers()['content-security-policy']).toBe(POLICY);
});

test('a policy this tight really does refuse something', async ({ page }) => {
  // The other half of the same worry. If `securitypolicyviolation` never fired — wrong
  // event, listener attached too late, `exposeFunction` not wired — the suite would be
  // green on a policy that blocked everything.
  const violations = await underPolicy(page);
  await page.goto('/login');
  await expect(page.locator('main')).toBeVisible();
  await page.evaluate(() => {
    const script = document.createElement('script');
    script.textContent = 'window.__csp_probe = true;';
    document.head.appendChild(script);
  });
  await page.waitForTimeout(200);

  expect(violations.map((entry) => entry.directive)).toContain('script-src-elem');
  expect(await page.evaluate(() => '__csp_probe' in window)).toBe(false);
});

test('the service worker still registers under the policy', async ({ page }) => {
  // Named explicitly in the batch because `worker-src` is the directive most likely to
  // break something invisible: a blocked registration costs the app its offline pick
  // queue and its precache, and nothing on screen says so.
  const violations = await underPolicy(page);
  await page.goto('/login');
  await expect(page.locator('main')).toBeVisible();

  const registered = await page.waitForFunction(
    () => navigator.serviceWorker?.controller !== undefined &&
      navigator.serviceWorker.getRegistration().then((r) => r !== undefined),
    undefined,
    { timeout: 10_000 },
  ).catch(() => null);

  // Some browsers decline a worker in this harness for reasons unrelated to CSP, so the
  // assertion that matters is the negative one: whatever happened, the policy did not
  // refuse it.
  expect(violations.filter((entry) => entry.directive.startsWith('worker-src'))).toEqual([]);
  expect(violations).toEqual([]);
  void registered;
});

test('the preloaded font is not refused', async ({ page }) => {
  // `font-src 'self'` against a self-hosted woff2 that the splash wordmark's LCP
  // depends on. Cheap to assert, and expensive to discover in production.
  const violations = await underPolicy(page);
  await page.goto('/welcome');
  await expect(page.locator('main')).toBeVisible();
  await page.waitForTimeout(500);

  expect(violations.filter((entry) => entry.directive.startsWith('font-src'))).toEqual([]);
  // The font is actually fetched and actually arrives — the listener goes on before the
  // navigation that issues the request, or it would be watching an empty window.
  const fonts: string[] = [];
  page.on('requestfinished', (request) => {
    if (request.url().includes('.woff2')) fonts.push(request.url());
  });
  await page.reload();
  await expect(page.locator('main')).toBeVisible();
  await page.waitForTimeout(500);

  expect(violations).toEqual([]);
  expect(fonts.length, 'no woff2 was fetched, so nothing was proved').toBeGreaterThan(0);
});
