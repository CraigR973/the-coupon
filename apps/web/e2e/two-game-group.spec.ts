import { createRequire } from "node:module";
import { join } from "node:path";
import {
  expect,
  test,
  type Page,
  type BrowserContext,
  type APIRequestContext,
} from "@playwright/test";
const API = process.env.COUPON_TWO_GAME_API_URL!;
const ART = process.env.COUPON_TWO_GAME_ARTIFACT_DIR!;
const AXE = createRequire(import.meta.url).resolve("axe-core");
interface Seed {
  now: string;
  league_id: string;
  slug: string;
  weeks: string[];
  legacy_week: string;
  players: Record<string, string>;
}
const group = (seed: Seed, index = 0) =>
  `/leagues/${seed.league_id}/weeks/${seed.weeks[index]}/group`;
async function seed(
  request: APIRequestContext,
  enabled = true,
  credit_pence = 1000,
) {
  const response = await request.post(API + "/__two_game_e2e/seed", {
    data: { enabled, credit_pence },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()) as Seed;
}
async function prepare(context: BrowserContext, page: Page, now: string, members: Seed["players"]) {
  // Phone play requires an installed app. Seed these synthetic members as having
  // already declined notification onboarding; never request push permissions.
  await context.addInitScript((ids) => {
    Object.defineProperty(navigator, "standalone", {value: true, configurable: true});
    for (const id of ids) localStorage.setItem(`coupon_notif_prompt_seen_${id}`, "1");
  }, Object.values(members));
  await page.clock.install({ time: new Date(now) });
}
async function signIn(page: Page, name = "Alice") {
  await page.getByLabel("Display name", { exact: true }).fill(name);
  for (let index = 0; index < 4; index++)
    await page
      .getByLabel(`PIN digit ${index + 1}`, { exact: true })
      .fill("1357"[index]);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toHaveCount(0);
}
async function open(page: Page, s: Seed, name = "Alice") {
  await page.goto("/login");
  await signIn(page, name);
  await expect(
    page.getByRole("heading", { name: `Hi ${name}`, exact: true }),
  ).toBeVisible();
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Saturday Group · 21 Nov", exact: true })
    .click();
  await expect(page.getByTestId("group-game")).toBeVisible();
}
async function choose(page: Page, home: number, outcome = "HOME") {
  const name =
    outcome === "HOME"
      ? `Choose Home ${home} to win`
      : outcome === "AWAY"
        ? `Choose Away ${home} to win`
        : "Choose Draw";
  await page.getByRole("button", { name, exact: true }).click();
}
async function confirmed(page: Page) {
  await expect(page.getByTestId("intent-0")).toContainText(/Saved/);
}
async function state(request: APIRequestContext) {
  return (await request.get(API + "/__two_game_e2e/state")).json();
}
async function at(request: APIRequestContext, page: Page, time: string) {
  expect(
    (
      await request.post(API + "/__two_game_e2e/clock", { data: { at: time } })
    ).ok(),
  ).toBe(true);
  const delta =
    new Date(time).getTime() - (await page.evaluate(() => Date.now()));
  expect(delta).toBeGreaterThanOrEqual(0);
  await page.clock.fastForward(delta);
}
async function refresh(page: Page) {
  await page
    .getByRole("button", { name: "Check payment status", exact: true })
    .click();
}

test("exact cold-login/payment link, unpriced contribution, mobile layout and accessibility", async ({
  page,
  context,
  request,
}, info) => {
  const s = await seed(request);
  await prepare(context, page, s.now, s.players);
  await page.goto(group(s) + "#payment");
  await expect(page).toHaveURL(/\/login\?next=/);
  await signIn(page);
  await expect(page).toHaveURL(new RegExp(`${s.weeks[0]}/group#payment$`));
  await expect(
    page.getByRole("heading", { name: "Payment for 21 Nov" }),
  ).toBeVisible();
  await expect(page.locator("#payment")).toBeFocused();
  const invalid = await (
    await request.get(API + "/__two_game_e2e/invalid-auth-tokens")
  ).json();
  for (const bearer of Object.values(invalid)) {
    const response = await request.get(API + "/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${bearer}` },
    });
    expect(response.status()).toBe(401);
  }
  await choose(page, 1);
  await confirmed(page);
  await expect(page.getByLabel("Group progress and result")).toContainText(
    "1 of 3 contributed · 2 missing contributors",
  );
  await expect(page.getByTestId("group-game")).not.toContainText(
    /odds|points/i,
  );
  const saved = await state(request);
  expect(saved.group).toHaveLength(1);
  expect(saved.quote_calls).toBe(0);
  expect(saved.counts.two_game_operations).toBe(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter((a) => Number.isFinite(a.effect?.getComputedTiming().endTime))
        .map((a) => a.finished),
    );
  });
  await page.addScriptTag({ path: AXE });
  const violations = await page.evaluate(async () => {
    const axe = (window as typeof window & { axe: typeof import("axe-core") })
      .axe;
    return (
      await axe.run(document.documentElement, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
      })
    ).violations.map((value) => ({
      id: value.id,
      targets: value.nodes.flatMap((node) => node.target),
    }));
  });
  expect(violations).toEqual([]);
  const originalViewport = page.viewportSize()!;
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: join(ART, `group-${info.project.name}-dark.png`),
    fullPage: true,
  });
  for (const width of [320, 640]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const target = page.getByRole("button", {
      name: "Choose Home 2 to win",
      exact: true,
    });
    const box = await target.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    await target.focus();
    await expect(target).toBeFocused();
  }
  await page.evaluate(() => document.documentElement.classList.add("light"));
  await page.evaluate(() => document.documentElement.classList.remove("dark"));
  const light = await page.evaluate(async () => {
    const axe = (window as typeof window & { axe: typeof import("axe-core") })
      .axe;
    return (
      await axe.run(document.documentElement, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
      })
    ).violations.map((value) => value.id);
  });
  expect(light).toEqual([]);
  await page.setViewportSize(originalViewport);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: join(ART, `group-${info.project.name}.png`),
    fullPage: true,
  });
});

test("two members race a whole fixture and the loser keeps their prior contribution", async ({
  page,
  context,
  request,
  browser,
}, info) => {
  const s = await seed(request);
  await prepare(context, page, s.now, s.players);
  await open(page, s);
  await choose(page, 3);
  await confirmed(page);
  const bobContext = await browser.newContext({
    viewport: page.viewportSize() ?? { width: 1280, height: 720 },
    isMobile: info.project.name === "phone",
    hasTouch: info.project.name === "phone",
    serviceWorkers: "block",
    baseURL: process.env.COUPON_TWO_GAME_WEB_URL,
  });
  try {
    const bob = await bobContext.newPage();
    await prepare(bobContext, bob, s.now, s.players);
    await open(bob, s, "Bob");
    await choose(bob, 2);
    await confirmed(bob);
    const attempts = [page, bob].map((member) =>
      member.waitForResponse(
        (response) =>
          response.request().method() === "PUT" &&
          response.url().endsWith("/games/group/pick"),
      ),
    );
    await Promise.all([choose(page, 1), choose(bob, 1, "AWAY")]);
    const responses = await Promise.all(attempts);
    expect(responses.map((response) => response.status()).sort()).toEqual([
      200, 409,
    ]);
    const refusal = responses.find((response) => response.status() === 409)!;
    expect((await refusal.json()).detail.code).toBe("FIXTURE_TAKEN");
    await expect
      .poll(async () => {
        const data = await state(request);
        return data.group.filter(
          (pick: { fixture_id: string }) =>
            pick.fixture_id ===
            data.group.find(
              (pick: { player_id: string; revision: number }) =>
                pick.revision === 2,
            )?.fixture_id,
        ).length;
      })
      .toBe(1);
    const data = await state(request);
    expect(data.group).toHaveLength(2);
    expect(
      data.group.map((pick: { revision: number }) => pick.revision).sort(),
    ).toEqual([1, 2]);
    const winner = data.group.find(
      (pick: { revision: number }) => pick.revision === 2,
    );
    const loserPage = winner.player_id === s.players.Alice ? bob : page;
    const loser = data.group.find(
      (pick: { player_id: string }) => pick.player_id !== winner.player_id,
    );
    expect(loser.revision).toBe(1);
    const previous = winner.player_id === s.players.Alice ? "Home 2" : "Home 3";
    await expect(
      loserPage.getByLabel("Group progress and result"),
    ).toContainText(`Your saved contribution: ${previous}`);
    await expect(loserPage.getByTestId("intent-0")).toContainText(
      /claimed|taken|another|contribution/i,
    );
    expect(data.quote_calls).toBe(0);
  } finally {
    await bobContext.close();
  }
});

test("offline route changes retain a replacement and unanswered commit reconciles once", async ({
  page,
  context,
  request,
}) => {
  const s = await seed(request);
  await prepare(context, page, s.now, s.players);
  await open(page, s);
  await choose(page, 1);
  await confirmed(page);
  await context.setOffline(true);
  await choose(page, 2);
  await expect(page.getByTestId("intent-0")).toContainText(
    "Offline choice kept",
  );
  await page
    .getByRole("navigation", { name: "Game navigation" })
    .getByRole("link", { name: "Home", exact: true })
    .click();
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Saturday Group · 21 Nov", exact: true })
    .click();
  await expect(page.getByTestId("intent-0")).toContainText(
    "Offline choice kept",
  );
  await context.setOffline(false);
  await confirmed(page);
  await expect
    .poll(async () => (await state(request)).group[0].revision)
    .toBe(2);
  let attempts = 0;
  await page.route("**/games/group/pick", async (route) => {
    if (route.request().method() === "PUT") {
      attempts++;
      const response = await route.fetch();
      expect(response.ok()).toBe(true);
      await route.abort("failed");
    } else await route.continue();
  });
  await choose(page, 3);
  await expect(page.getByTestId("intent-0")).toContainText("No answer yet");
  expect((await state(request)).group[0].revision).toBe(3);
  await page
    .getByRole("button", { name: "Check and retry this choice", exact: true })
    .click();
  await confirmed(page);
  expect(attempts).toBe(1);
  const data = await state(request);
  expect(data.counts.two_game_operations).toBe(3);
  expect(data.quote_calls).toBe(0);
});

test("stored lock disables entry exactly, real settlement is final and departed history remains readable", async ({
  page,
  context,
  request,
}) => {
  const s = await seed(request);
  await prepare(context, page, s.now, s.players);
  await open(page, s);
  await choose(page, 1);
  await confirmed(page);
  await at(request, page, "2026-11-21T14:29:59Z");
  await expect(
    page.getByRole("button", { name: "Choose Home 2 to win", exact: true }),
  ).toBeEnabled();
  await at(request, page, "2026-11-21T14:30:00Z");
  await expect(
    page.getByRole("button", { name: "Choose Home 2 to win", exact: true }),
  ).toBeDisabled();
  const before = await state(request);
  const bearer = await page.evaluate(() =>
    localStorage.getItem("coupon_access"),
  );
  const refused = await request.put(
    `${API}/api/v1/leagues/${s.league_id}/weeks/${s.weeks[0]}/games/group/pick`,
    {
      headers: { Authorization: `Bearer ${bearer}` },
      data: {
        fixture_id: before.group[0].fixture_id,
        market: "MATCH_ODDS",
        outcome: "AWAY",
        expected_revision: 1,
        operation_id: crypto.randomUUID(),
      },
    },
  );
  expect(refused.status()).toBe(409);
  expect((await refused.json()).detail.code).toBe("LOCKED");
  await at(request, page, "2026-11-21T15:01:00Z");
  expect(
    (await request.post(API + "/__two_game_e2e/settle", { data: {} })).ok(),
  ).toBe(true);
  await refresh(page);
  await expect(page.getByLabel("Group progress and result")).toContainText(
    "Won · Final",
  );
  await request.post(API + "/__two_game_e2e/leave", {
    data: { player_id: s.players.Alice },
  });
  await page.reload();
  await expect(page.getByTestId("group-game")).toContainText(
    "Retained locked history",
  );
  await expect(page.getByLabel("Group progress and result")).toContainText(
    "Won · Final",
  );
  expect((await state(request)).group).toHaveLength(1);
});

test("all-void is distinct from an empty future coupon, with exact archive links", async ({
  page,
  context,
  request,
}) => {
  const s = await seed(request);
  await prepare(context, page, s.now, s.players);
  await open(page, s);
  await choose(page, 1);
  await confirmed(page);
  await at(request, page, "2026-11-21T15:01:00Z");
  const settled = await request.post(API + "/__two_game_e2e/settle", {
    data: { statuses: { "local-0-0": "cancelled" } },
  });
  expect(settled.ok(), await settled.text()).toBe(true);
  await refresh(page);
  await expect(page.getByLabel("Group progress and result")).toContainText(
    "Void · Final",
  );
  await at(request, page, "2026-11-28T15:01:00Z");
  expect(
    (await request.post(API + "/__two_game_e2e/settle", { data: {} })).ok(),
  ).toBe(true);
  await page.goto(group(s, 1));
  await expect(page.getByLabel("Group progress and result")).toContainText(
    "No coupon · Final",
  );
  await page.getByRole("link", { name: "Game archive", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Previous games", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Saturday Group · 21 Nov", exact: true })
    .click();
  await expect(page.getByLabel("Group progress and result")).toContainText(
    "Void · Final",
  );
});

test("disabled mode and an older backend keep legacy navigation and hide new entry", async ({
  page,
  context,
  request,
}) => {
  const s = await seed(request, false);
  await prepare(context, page, s.now, s.players);
  await page.goto("/login");
  await signIn(page);
  await expect(page.getByTestId("two-game-home")).toHaveCount(0);
  await page.route("**/api/v1/me/games", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: '{"detail":"Synthetic read failure"}',
    }),
  );
  await page.reload();
  await expect(
    page.getByText("Couldn't load game status", { exact: true }),
  ).toBeVisible();
  await page.unroute("**/api/v1/me/games");
  await page.route("**/api/v1/me/games", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: '{"detail":"Not Found"}',
    }),
  );
  await page.reload();
  await expect(page.getByTestId("two-game-home")).toHaveCount(0);
  await page.goto(`/leagues/${s.slug}/predictions?gw=${s.legacy_week}#coupon`);
  await expect(page).toHaveURL(new RegExp(`gw=${s.legacy_week}#coupon$`));
  await expect(page.getByTestId("group-game")).toHaveCount(0);
  await page.goto(group(s));
  await expect(
    page.getByRole("heading", { name: "Group game unavailable" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Choose / })).toHaveCount(0);
  expect((await state(request)).counts.two_game_operations).toBe(0);
});

test("unpaid Group targets payment focus, and sign-out discards an offline member choice", async ({
  page,
  context,
  request,
}) => {
  const s = await seed(request, true, 1);
  await prepare(context, page, s.now, s.players);
  await open(page, s);
  await choose(page, 1);
  await expect(page.getByTestId("intent-0")).toContainText(/payment|paid|owe/i);
  await page
    .getByRole("link", { name: "Review this week’s payment", exact: true })
    .click();
  await expect(page.locator("#payment")).toBeFocused();
  await expect(page.locator("#payment")).toContainText(
    "£0.99 owed through this week",
  );
  await context.setOffline(true);
  await choose(page, 2);
  await expect(page.getByTestId("intent-0")).toContainText(
    "Offline choice kept",
  );
  await page
    .getByRole("button", { name: "Account menu (Alice)", exact: true })
    .click();
  await page.getByRole("menuitem", { name: "Log out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await context.setOffline(false);
  await signIn(page, "Bob");
  await expect(page.getByTestId("group-game")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Account menu (Bob)", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("intent-0")).toHaveCount(0);
  expect((await state(request)).group).toHaveLength(0);
  await page.goto(`/leagues/${s.league_id}/weeks/${s.legacy_week}/group`);
  await page
    .getByRole("link", { name: "Open this legacy week", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`gw=${s.legacy_week}#coupon$`));
});

test("an incomplete Group with a neutral void still wins without adding season points", async ({
  page,
  context,
  request,
  browser,
}, info) => {
  const s = await seed(request);
  await prepare(context, page, s.now, s.players);
  await open(page, s);
  await choose(page, 1);
  await confirmed(page);
  const bobContext = await browser.newContext({
    viewport: page.viewportSize() ?? { width: 1280, height: 720 },
    isMobile: info.project.name === "phone",
    hasTouch: info.project.name === "phone",
    serviceWorkers: "block",
    baseURL: process.env.COUPON_TWO_GAME_WEB_URL,
  });
  try {
    const bob = await bobContext.newPage();
    await prepare(bobContext, bob, s.now, s.players);
    await open(bob, s, "Bob");
    await choose(bob, 2);
    await confirmed(bob);
    await at(request, page, "2026-11-21T15:01:00Z");
    const response = await request.post(API + "/__two_game_e2e/settle", {
      data: { statuses: { "local-0-0": "cancelled", "local-0-1": "finished" } },
    });
    expect(response.ok(), await response.text()).toBe(true);
    await refresh(page);
    await expect(page.getByLabel("Group progress and result")).toContainText(
      "Won · Final",
    );
    await expect(page.getByLabel("Group progress and result")).toContainText(
      "2 of 3 contributed · 1 missing contributors",
    );
    const data = await state(request);
    expect(
      data.group.map((pick: { result: string }) => pick.result).sort(),
    ).toEqual(["void", "won"]);
    expect(data.fantasy).toHaveLength(0);
    expect(data.quote_calls).toBe(0);
  } finally {
    await bobContext.close();
  }
});
