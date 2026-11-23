import { createRequire } from "node:module";
import { join } from "node:path";
import {
  test,
  expect,
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
  legacy_fixture: string;
  fixtures: string[][];
  players: Record<string, string>;
}
const path = (s: Seed, week = 0, kind = "fantasy") =>
  `/leagues/${s.league_id}/weeks/${s.weeks[week]}/${kind}`;
async function post(
  request: APIRequestContext,
  endpoint: string,
  data: unknown = {},
) {
  const response = await request.post(API + "/__two_game_e2e/" + endpoint, {
    data,
  });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}
async function setup(
  request: APIRequestContext,
  context: BrowserContext,
  page: Page,
  options: Record<string, unknown> = {},
) {
  const s: Seed = await post(request, "seed", { fantasy: true, ...options });
  await context.addInitScript((ids) => {
    Object.defineProperty(navigator, "standalone", {
      value: true,
      configurable: true,
    });
    for (const id of ids)
      localStorage.setItem(`coupon_notif_prompt_seen_${id}`, "1");
  }, Object.values(s.players));
  await page.clock.install({ time: new Date(s.now) });
  return s;
}
async function login(page: Page, s: Seed, week = 0) {
  await page.goto(path(s, week));
  await page.getByLabel("Display name", { exact: true }).fill("Alice");
  for (let i = 0; i < 4; i++)
    await page
      .getByLabel(`PIN digit ${i + 1}`, { exact: true })
      .fill("1357"[i]);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByTestId("fantasy-game")).toBeVisible();
}
async function warm(request: APIRequestContext, week = 0) {
  await post(request, "quotes", { warm: true, week });
}
const slot = (page: Page, n: number) =>
  page.getByRole("article", { name: `Fantasy slot ${n}`, exact: true });
// Batch 232 (owner-approved, 23 Nov): prices sit on the fixture cards, and the list names
// the slot it is choosing for, so a choice for slot n is made in that list.
const chooser = (page: Page, n: number) =>
  page.getByRole("region", { name: `Choose fixture for slot ${n}`, exact: true });
async function select(page: Page, n: number) {
  await slot(page, n)
    .getByRole("button", { name: new RegExp(`^(Fill|Replace) slot ${n}$`) })
    .click();
}
async function choose(
  page: Page,
  n: number,
  home: number,
  odds = "2.1500",
  away = false,
) {
  await chooser(page, n)
    .getByRole("button", {
      name: `Choose ${away ? "Away" : "Home"} ${home} to win at ${away ? "4.0000" : odds}`,
      exact: true,
    })
    .click();
}
async function saved(page: Page, n: number) {
  await expect(slot(page, n).getByTestId(`intent-${n}`)).toContainText(
    "Saved choice confirmed.",
  );
}
async function current(request: APIRequestContext) {
  return (await request.get(API + "/__two_game_e2e/state")).json();
}
async function at(request: APIRequestContext, page: Page, at: string) {
  await post(request, "clock", { at });
  const delta =
    new Date(at).getTime() - (await page.evaluate(() => Date.now()));
  expect(delta).toBeGreaterThanOrEqual(0);
  await page.clock.fastForward(delta);
}
async function refresh(page: Page) {
  await page
    .getByRole("button", { name: "Refresh prices and results", exact: true })
    .click();
}
async function home(page: Page) {
  await page
    .getByRole("navigation", { name: "Game navigation" })
    .getByRole("link", { name: "Home", exact: true })
    .click();
}
async function apiMember(request: APIRequestContext, name: string) {
  const response = await request.post(API + "/api/v1/auth/login", {
    data: { display_name: name, pin: "1357" },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()).access_token as string;
}
async function rawSave(
  request: APIRequestContext,
  s: Seed,
  token: string,
  n: number,
  fixture: number,
  odds = "4.00",
  outcome = "AWAY",
) {
  const response = await request.put(
    API +
      `/api/v1/leagues/${s.league_id}/weeks/${s.weeks[0]}/games/fantasy/slots/${n}`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        fixture_id: s.fixtures[0][fixture - 1],
        market: "MATCH_ODDS",
        outcome,
        odds,
        operation_id: crypto.randomUUID(),
        expected_revision: 0,
      },
    },
  );
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

test("six slots, shared Group/member selection, quote provenance and accessible phone layout", async ({
  page,
  context,
  request,
}, info) => {
  const s = await setup(request, context, page);
  // Bob's independent real login need not delay Alice's browser interactions.
  const bob = apiMember(request, "Bob");
  await warm(request);
  await login(page, s);
  await expect(page.getByRole("article", { name: /Fantasy slot/ })).toHaveCount(
    6,
  );
  await select(page, 1);
  await choose(page, 1, 1);
  await saved(page, 1);
  await expect(slot(page, 1)).toContainText("Frozen odds 2.1500");
  // Keep Alice's first accepted selection before Bob's shared selection.
  const sharedSave = rawSave(request, s, await bob, 1, 1, "2.15", "HOME");
  await select(page, 2);
  await expect(
    chooser(page, 2).getByText("Already chosen in another slot.", { exact: true }),
  ).toBeVisible();
  await choose(page, 2, 8);
  await saved(page, 2);
  await expect(page.getByLabel("Fantasy weekly result")).toContainText(
    "2 of 6 slots",
  );
  await sharedSave;
  await home(page);
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Saturday Group · 21 Nov", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Choose Home 1 to win", exact: true })
    .click();
  await expect(page.getByTestId("intent-0")).toContainText(
    "Saved choice confirmed.",
  );
  await home(page);
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Fantasy · 21 Nov", exact: true })
    .click();
  await select(page, 3);
  const state = await current(request);
  expect(state.group).toHaveLength(1);
  expect(state.fantasy).toHaveLength(3);
  expect(
    state.fantasy.filter(
      (p: { fixture_id: string }) => p.fixture_id === s.fixtures[0][0],
    ),
  ).toHaveLength(2);
  await page.addScriptTag({ path: AXE });
  const original = page.viewportSize()!;
  for (const theme of ["dark", "light"]) {
    await page.evaluate((theme) => {
      document.documentElement.classList.remove("dark", "light");
      document.documentElement.classList.add(theme);
    }, theme);
    const violations = await page.evaluate(async () => {
      const axe = (window as typeof window & { axe: typeof import("axe-core") })
        .axe;
      return (
        await axe.run(document.documentElement, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
        })
      ).violations.map((v) => ({
        id: v.id,
        targets: v.nodes.flatMap((n) => n.target),
      }));
    });
    expect(violations).toEqual([]);
    await page.screenshot({
      path: join(ART, `fantasy-${info.project.name}-${theme}.png`),
      fullPage: true,
    });
  }
  for (const width of [320, 640]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const button = chooser(page, 3).getByRole("button", {
      name: "Choose Home 2 to win at 2.1500",
      exact: true,
    });
    expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await button.focus();
    await expect(button).toBeFocused();
  }
  await page.setViewportSize(original);
});

test("two offline fills survive SPA navigation independently and an uncertain replacement commits once", async ({
  page,
  context,
  request,
}) => {
  const s = await setup(request, context, page);
  await warm(request);
  await login(page, s);
  await page
    .getByRole("navigation", { name: "Game navigation" })
    .getByRole("link", { name: "Game archive", exact: true })
    .click();
  await page
    .getByRole("link", { name: "Fantasy · 28 Nov", exact: true })
    .click();
  await expect(
    page.getByText("Entry has not opened", { exact: true }),
  ).toBeVisible();
  await home(page);
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Saturday Group · 21 Nov", exact: true })
    .click();
  await expect(page.getByTestId("group-game")).toBeVisible();
  await home(page);
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Fantasy · 21 Nov", exact: true })
    .click();
  await expect(page.getByTestId("fantasy-game")).toBeVisible();
  for (let n = 1; n <= 6; n++)
    await expect(
      slot(page, n).getByRole("button", {
        name: `Fill slot ${n}`,
        exact: true,
      }),
    ).toBeEnabled();
  await context.setOffline(true);
  await select(page, 1);
  await choose(page, 1, 1);
  await expect(slot(page, 1)).toContainText("Offline choice kept");
  await select(page, 2);
  await choose(page, 2, 2);
  await expect(slot(page, 2)).toContainText("Offline choice kept");
  await home(page);
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Saturday Group · 21 Nov", exact: true })
    .click();
  await expect(page.getByTestId("intent-0")).toHaveCount(0);
  await home(page);
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Game archive", exact: true })
    .click();
  await page
    .getByRole("link", { name: "Fantasy · 28 Nov", exact: true })
    .click();
  await expect(page.getByTestId("intent-1")).toHaveCount(0);
  await expect(page.getByTestId("intent-2")).toHaveCount(0);
  await home(page);
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Fantasy · 21 Nov", exact: true })
    .click();
  await expect(slot(page, 1)).toContainText("Offline choice kept");
  await expect(slot(page, 2)).toContainText("Offline choice kept");
  await context.setOffline(false);
  await saved(page, 1);
  await saved(page, 2);
  let attempts = 0;
  await page.route("**/games/fantasy/slots/1", async (route) => {
    if (route.request().method() === "PUT") {
      attempts++;
      expect((await route.fetch()).status()).toBe(200);
      await route.abort("failed");
    } else await route.continue();
  });
  await select(page, 1);
  await choose(page, 1, 3);
  await expect(slot(page, 1)).toContainText("No answer yet");
  await slot(page, 1)
    .getByRole("button", { name: "Check and retry this choice", exact: true })
    .click();
  await saved(page, 1);
  expect(attempts).toBe(1);
  const state = await current(request);
  expect(state.fantasy).toHaveLength(2);
  expect(
    state.fantasy.find((p: { slot: number }) => p.slot === 1),
  ).toMatchObject({ fixture_id: s.fixtures[0][2], revision: 2 });
  expect(
    state.fantasy.find((p: { slot: number }) => p.slot === 2),
  ).toMatchObject({ fixture_id: s.fixtures[0][1], revision: 1 });
  expect(state.counts.two_game_operations).toBe(3);
});

test("two price movements each require fresh consent and unavailable prices preserve the old slot", async ({
  page,
  context,
  request,
}) => {
  const s = await setup(request, context, page);
  await warm(request);
  await login(page, s);
  await select(page, 1);
  await choose(page, 1, 1);
  await saved(page, 1);
  const operations: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "PUT" && r.url().endsWith("/fantasy/slots/1"))
      operations.push(r.postDataJSON().operation_id);
  });
  await post(request, "quotes", { price: "3.25" });
  await at(request, page, "2026-11-21T11:51:05Z");
  await choose(page, 1, 2);
  await expect(slot(page, 1)).toContainText("The price changed to 3.2500");
  expect((await current(request)).fantasy[0].fixture_id).toBe(s.fixtures[0][0]);
  await post(request, "quotes", { price: "4.25" });
  await at(request, page, "2026-11-21T11:52:10Z");
  await slot(page, 1)
    .getByRole("button", {
      name: "Confirm odds 3.2500 for slot 1",
      exact: true,
    })
    .click();
  await expect(slot(page, 1)).toContainText("The price changed to 4.2500");
  await slot(page, 1)
    .getByRole("button", {
      name: "Confirm odds 4.2500 for slot 1",
      exact: true,
    })
    .click();
  await saved(page, 1);
  expect(new Set(operations).size).toBe(3);
  expect((await current(request)).fantasy[0]).toMatchObject({
    fixture_id: s.fixtures[0][1],
    revision: 2,
  });
  await post(request, "quotes", { priced: false });
  await at(request, page, "2026-11-21T11:53:15Z");
  await choose(page, 1, 3);
  await expect(slot(page, 1)).toContainText(/unavailable/i);
  const state = await current(request);
  expect(state.fantasy[0]).toMatchObject({
    fixture_id: s.fixtures[0][1],
    revision: 2,
  });
  expect(state.counts.two_game_operations).toBe(2);
});

test("noon opens the next Fantasy, payment is target-specific and early dues are never duplicated", async ({
  page,
  context,
  request,
}) => {
  const s = await setup(request, context, page, { credit_pence: 100 });
  await warm(request);
  await login(page, s);
  await expect(page.getByRole("region", { name: "Week payment" })).toHaveCount(
    0,
  );
  await expect(page.locator("#payment")).toContainText(
    "Paid through this week",
  );
  await at(request, page, "2026-11-21T12:00:00Z");
  await expect(page.getByText("Fantasy locked", { exact: true })).toBeVisible();
  await expect(
    slot(page, 1).getByRole("button", { name: "Fill slot 1", exact: true }),
  ).toHaveCount(0);
  await warm(request, 1);
  await home(page);
  await expect(
    page
      .getByTestId("two-game-home")
      .getByRole("link", { name: "Saturday Group · 21 Nov", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByTestId("two-game-home")
      .getByRole("link", { name: "Fantasy · 21 Nov", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("two-game-home")).toContainText(
    "Locked results",
  );
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Fantasy · 28 Nov", exact: true })
    .click();
  await expect(page.locator("#payment")).toContainText("£1.00");
  await select(page, 1);
  const refusal = page.waitForResponse(
    (r) =>
      r.request().method() === "PUT" && r.url().endsWith("/fantasy/slots/1"),
  );
  await chooser(page, 1)
    .getByRole("button", {
      name: "Choose Next Home 1 to win at 2.1500",
      exact: true,
    })
    .click();
  expect((await refusal).status()).toBe(402);
  await slot(page, 1)
    .getByRole("link", { name: "Review this week’s payment" })
    .click();
  await expect(page.locator("#payment")).toBeFocused();
  expect((await current(request)).fantasy).toHaveLength(0);
  await post(request, "credit", {
    player_id: s.players.Alice,
    amount_pence: 100,
  });
  await page
    .getByRole("button", { name: "Check payment status", exact: true })
    .click();
  await expect(page.locator("#payment")).toContainText(
    "Paid through this week",
  );
  await chooser(page, 1)
    .getByRole("button", {
      name: "Choose Next Home 1 to win at 2.1500",
      exact: true,
    })
    .click();
  await saved(page, 1);
  await at(request, page, "2026-11-23T00:01:00Z");
  await post(request, "bill");
  await post(request, "bill");
  const state = await current(request);
  const alice = state.obligations.filter(
    (o: { player_id: string }) => o.player_id === s.players.Alice,
  );
  expect(alice.map((o: { week_label: string }) => o.week_label).sort()).toEqual(
    ["2026-11-21", "2026-11-28"],
  );
  expect(state.fantasy[0].week_id).toBe(s.weeks[1]);
});

test("a late save receipt cannot overwrite Sunday results, corrections or continuing legacy points", async ({
  page,
  context,
  request,
}) => {
  const s = await setup(request, context, page, { legacy_points: true });
  await warm(request);
  await login(page, s);
  await select(page, 1);
  await choose(page, 1, 1);
  await saved(page, 1);
  let release!: () => void;
  let committed!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const landed = new Promise<void>((resolve) => {
    committed = resolve;
  });
  await page.route("**/games/fantasy/slots/1", async (route) => {
    if (route.request().method() === "PUT") {
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      committed();
      await held;
      await route.fulfill({ response });
    } else await route.continue();
  });
  await choose(page, 1, 8);
  await landed;
  await post(request, "clock", { at: "2026-11-22T23:59:00Z" });
  await page.clock.setSystemTime(new Date("2026-11-22T23:59:00Z"));
  await post(request, "settle", { statuses: { "local-0-7": "in_progress" } });
  await refresh(page);
  await expect(page.getByLabel("Fantasy weekly result")).toContainText(
    "Pending results",
  );
  await post(request, "clock", { at: "2026-11-23T00:05:00Z" });
  await page.clock.setSystemTime(new Date("2026-11-23T00:05:00Z"));
  await post(request, "settle", { statuses: { "local-0-7": "finished" } });
  await refresh(page);
  await expect(page.getByLabel("Fantasy weekly result")).toContainText(
    "22 weekly points · Final",
  );
  release();
  await saved(page, 1);
  await expect(page.getByLabel("Fantasy weekly result")).toContainText(
    "22 weekly points · Final",
  );
  await expect(slot(page, 1)).toContainText("Won · 22 points");
  await home(page);
  await expect(page.getByTestId("two-game-home")).toContainText(
    "Season total: 52 points",
  );
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Season table", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Two Game Local", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("2026/27 standings", { exact: true })).toBeVisible();
  await expect(
    page
      .getByTestId("standings")
      .getByRole("listitem")
      .filter({ hasText: "Alice" })
      .getByTestId("standing-points"),
  ).toHaveText("52 points");
  const aliceStanding = page.getByTestId("standings").getByRole("listitem").filter({ hasText: "Alice" });
  await expect(aliceStanding.getByTestId("pick-form")).toHaveText("W30F22");
  await expect(aliceStanding.getByTestId("pick-form")).toHaveAccessibleName(/won 30 points, Fantasy week scored 22 points/);
  await aliceStanding.getByRole("link").click();
  await expect(page.getByTestId("profile-stats")).toContainText("52");
  await expect(page.getByTestId("profile-history").getByRole("listitem")).toHaveCount(2);
  await expect(page.getByTestId(`history-${s.fixtures[0][7]}`)).toContainText("22 pts");
  await expect(page.getByRole("link", { name: "Fantasy slot 1 · 21 Nov 2026", exact: true })).toHaveAttribute("href", path(s));
  await expect(page.getByRole("link", { name: "Legacy round · 14 Nov 2026", exact: true })).toHaveAttribute("href", `/leagues/${s.slug}/predictions?gw=${s.legacy_week}#coupon`);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const historyLink = page.getByRole("link", { name: "Fantasy slot 1 · 21 Nov 2026", exact: true });
  expect((await historyLink.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await historyLink.focus();
  await expect(historyLink).toBeFocused();
  expect(
    (
      await post(request, "correct", {
        fixture_id: s.fixtures[0][7],
        home_won: false,
      })
    ).changed,
  ).toBe(1);
  expect(
    (
      await post(request, "correct", {
        fixture_id: s.fixtures[0][7],
        home_won: false,
      })
    ).changed,
  ).toBe(0);
  await page.goto(path(s));
  await expect(page.getByLabel("Fantasy weekly result")).toContainText(
    "0 weekly points · Final",
  );
  await home(page);
  await expect(page.getByTestId("two-game-home")).toContainText(
    "Season total: 30 points",
  );
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Game archive", exact: true })
    .click();
  await page.getByRole("link", { name: /Legacy.*14 Nov/ }).click();
  await expect(page).toHaveURL(new RegExp(`gw=${s.legacy_week}`));
});

test("partial zero-point entries tie while all-void and no-entry remain distinct", async ({
  page,
  context,
  request,
}) => {
  const s = await setup(request, context, page);
  await warm(request);
  await login(page, s);
  await select(page, 1);
  await choose(page, 1, 1, "2.15", true);
  await saved(page, 1);
  await rawSave(request, s, await apiMember(request, "Bob"), 1, 1);
  await rawSave(
    request,
    s,
    await apiMember(request, "Carol"),
    1,
    2,
    "2.15",
    "HOME",
  );
  await at(request, page, "2026-11-23T00:05:00Z");
  await post(request, "settle", { statuses: { "local-0-1": "postponed" } });
  await refresh(page);
  await expect(page.getByLabel("Fantasy weekly result")).toContainText(
    "1 of 6 slots · Scored",
  );
  await expect(page.getByLabel("Fantasy weekly result")).toContainText(
    "0 weekly points · Final",
  );
  const totals = page.getByLabel("Member weekly totals");
  await expect(totals).toContainText("Carol: 0 points · All void");
  await expect(totals).toContainText("Bob: 0 points · Scored");
  await expect(totals).toContainText(/Weekly winners: (Alice, Bob|Bob, Alice)/);
  await page.goto(path(s, 1));
  await expect(page.getByLabel("Fantasy weekly result")).toContainText(
    "0 of 6 slots · No entry",
  );
  await expect(page.getByLabel("Fantasy weekly result")).not.toContainText(
    "All void",
  );
});

test("first mixed Saturday preserves the legacy game and exact next-week Fantasy destination", async ({
  page,
  context,
  request,
}) => {
  const s = await setup(request, context, page, { mixed: true, mixed_paid_legacy: true, credit_pence: 100 });
  await login(page, s);
  await expect(
    page.getByText("Entry has not opened", { exact: true }),
  ).toBeVisible();
  await at(request, page, "2026-11-14T12:00:00Z");
  await refresh(page);
  await expect(
    slot(page, 1).getByRole("button", { name: "Fill slot 1", exact: true }),
  ).toBeEnabled();
  await home(page);
  const cards = page.getByTestId("two-game-home");
  const legacyCard = cards.getByRole("link", { name: "Legacy round · 14 Nov", exact: true }).locator("..");
  const nextCard = cards.getByRole("link", { name: "Fantasy · 21 Nov", exact: true }).locator("..");
  await expect(legacyCard).toContainText("Your pick: Legacy Away");
  await expect(legacyCard).toContainText("Frozen odds 4.00");
  await expect(legacyCard).toContainText("£1.00 per legacy round · Paid through this round");
  await expect(legacyCard).toContainText("Entry open");
  await expect(legacyCard).toContainText("Locks Sat 14 Nov 14:30 London.");
  await expect(nextCard).toContainText("£1.00 owed through this week");
  await expect(nextCard.getByRole("link", { name: "Fantasy · 21 Nov", exact: true })).toHaveAttribute("href", path(s));
  await expect(legacyCard.getByRole("link", { name: "Legacy round · 14 Nov", exact: true })).toHaveAttribute("href", `/leagues/${s.slug}/predictions?gw=${s.legacy_week}#coupon`);
  await expect(
    cards.getByRole("link", { name: "Legacy round · 14 Nov", exact: true }),
  ).toBeVisible();
  await expect(
    cards.getByRole("link", { name: "Fantasy · 21 Nov", exact: true }),
  ).toBeVisible();
  await expect(
    cards.getByRole("link", { name: "Saturday Group · 21 Nov", exact: true }),
  ).toHaveCount(0);
  await cards
    .getByRole("link", { name: "Legacy round · 14 Nov", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`gw=${s.legacy_week}`));
  const competition = page.getByTestId("competition-synthetic");
  const toggle = competition.getByRole("button").first();
  if ((await toggle.getAttribute("aria-expanded")) === "false")
    await toggle.click();
  const first = page.getByTestId(
    `selection-${s.legacy_fixture}-MATCH_ODDS-HOME`,
  );
  const replacement = page.getByTestId(
    `selection-${s.legacy_fixture}-MATCH_ODDS-AWAY`,
  );
  const firstSaved = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      r.url().endsWith(`/leagues/${s.slug}/picks`),
  );
  await first.click();
  expect((await firstSaved).status()).toBe(201);
  await expect(first).toHaveAttribute("aria-pressed", "true");
  // Batch 231: the seeded legacy pick is already AWAY, so the final check alone would pass
  // even if neither browser write landed. Prove the first one replaced it on the server.
  const afterFirst = await current(request);
  expect(afterFirst.legacy).toHaveLength(1);
  expect(afterFirst.legacy[0]).toMatchObject({
    fixture_id: s.legacy_fixture,
    outcome: "HOME",
  });
  const replaced = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      r.url().endsWith(`/leagues/${s.slug}/picks`),
  );
  await replacement.click();
  expect((await replaced).status()).toBe(201);
  await expect(replacement).toHaveAttribute("aria-pressed", "true");
  await expect(first).toHaveAttribute("aria-pressed", "false");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Home", exact: true })
    .first()
    .click();
  await warm(request);
  await post(request, "credit", { player_id: s.players.Alice, amount_pence: 100 });
  await page
    .getByTestId("two-game-home")
    .getByRole("link", { name: "Fantasy · 21 Nov", exact: true })
    .click();
  await select(page, 1);
  await choose(page, 1, 1);
  await saved(page, 1);
  const state = await current(request);
  expect(state.legacy).toHaveLength(1);
  expect(state.legacy[0]).toMatchObject({
    fixture_id: s.legacy_fixture,
    outcome: "AWAY",
  });
  expect(state.fantasy).toHaveLength(1);
  expect(state.fantasy[0].week_id).toBe(s.weeks[0]);
});
