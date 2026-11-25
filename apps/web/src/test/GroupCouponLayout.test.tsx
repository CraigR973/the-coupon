import { afterEach, describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GroupGamePage } from "../pages/GroupGamePage";
import { GameIntentContext } from "../hooks/useGameIntents";
import { GameIntents, type GameIntent } from "../lib/gameIntents";
import {
  gamePath,
  type GameEntry,
  type GamePick,
  type GroupFixture,
  type GroupGame,
} from "../lib/twoGameTypes";

/**
 * Batch 233: the Saturday group on the old coupon layout. Another member's fixture reads
 * "Picked by <name>" and greys out, the member's own reads "Your game", a tap saves the
 * one contribution and another switches it, and the coupon copies as text for the group
 * chat. Writes go through a stateful fake of the group pick API, so every claim on screen
 * comes from the readback, as it does against the real API.
 */
const target = {
  league_id: "league-a",
  week_id: "week-a",
  game_kind: "group" as const,
};
const { api, toast } = vi.hoisted(() => ({
  api: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  apiFetch: api,
}));
vi.mock("sonner", () => ({ toast }));
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({ player: { id: "alice" } }),
}));
vi.mock("../hooks/useGameRoute", () => ({ useGameRoute: () => target }));
vi.mock("../hooks/useExpiry", () => ({
  useExpiry: (value: string) => value.includes("opens"),
}));

type Claim = NonNullable<GroupFixture["claim"]>;
const NAMES: Record<string, string> = { alice: "Alice", bob: "Bob Smith" };
const runner = (fixture: number, outcome: string) =>
  outcome === "HOME" ? `Home ${fixture}` : outcome === "AWAY" ? `Away ${fixture}` : "Draw";
const claimOf = (player: string, fixture: number, outcome = "HOME"): Claim => ({
  player_id: player,
  display_name: NAMES[player],
  market: "MATCH_ODDS",
  outcome,
  runner_name: runner(fixture, outcome),
  result: "pending",
});

function harness(
  initial: Record<number, Claim>,
  { single = false, shape = (value: GroupGame) => value } = {},
) {
  const claims: Record<number, Claim | null> = { ...initial };
  let revision = Object.values(initial).some((value) => value.player_id === "alice") ? 1 : 0;
  const myPick = (): GamePick | null => {
    const held = Object.entries(claims).find(([, value]) => value?.player_id === "alice");
    if (!held || !held[1]) return null;
    return {
      id: "pick-alice",
      fixture_id: `fixture-${held[0]}`,
      player_id: "alice",
      market: held[1].market,
      outcome: held[1].outcome,
      runner_name: held[1].runner_name,
      revision,
      operation_id: "operation",
      result: "pending",
    };
  };
  const entry = (): GameEntry => ({
    ...target,
    game_id: "game-a",
    revision,
    operation_id: null,
    pick: myPick(),
  });
  const game = (): GroupGame => {
    const picked = Object.values(claims).filter(Boolean).length;
    const pick = myPick();
    return {
      ...target,
      game_id: "game-a",
      week_label: "2026-11-28",
      week_number: "1",
      destination: "/",
      opens_at: "opens",
      locks_at: "locks",
      entry_state: "open",
      coverage_state: "complete",
      my_entries: pick ? [pick] : [],
      progress: { picked_count: picked, member_count: 4, all_picked: picked === 4 },
      result: { status: "pending", final: false },
      fee: {
        league_id: "league-a",
        week_id: "week-a",
        week_label: "2026-11-28",
        billing_starts_at: "2026-11-23T00:00:00Z",
        billing_ends_at: "2026-11-30T00:00:00Z",
        obligation_pence: 100,
        amount_owed_pence: 0,
        paid_through: true,
        pooled_credit_pence: 0,
        payment_url: null,
        destination: "/",
        obligations: [],
      },
      fixtures: [1, 2, 3, 4].map((number) => ({
        fixture_id: `fixture-${number}`,
        home: `Home ${number}`,
        away: `Away ${number}`,
        competition_id:
          number === 4 && !single ? "scotland-championship" : "scotland-premiership",
        kickoff_at: "2026-11-28T15:00:00Z",
        status: "pending",
        eligible: true,
        claim: claims[number] ?? null,
        allowed_markets: [{ market: "MATCH_ODDS", outcomes: ["HOME", "DRAW", "AWAY"] }],
      })),
    };
  };
  api.mockImplementation(async (path: string) =>
    path === gamePath(target) ? shape(game()) : entry(),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const write = vi.fn(async (_path: string, body: GameIntent["body"]) => {
    for (const [number, value] of Object.entries(claims))
      if (value?.player_id === "alice") claims[Number(number)] = null;
    const number = Number(body.fixture_id.split("-").at(-1));
    claims[number] = claimOf("alice", number, body.outcome);
    revision += 1;
    return { ...entry(), operation_id: body.operation_id };
  });
  // Batch 235: a withdrawal frees the member's fixture at the next revision, as the API's
  // DELETE does.
  const remove = vi.fn(
    async (_path: string, body: { expected_revision: number; operation_id: string }) => {
      for (const [number, value] of Object.entries(claims))
        if (value?.player_id === "alice") claims[Number(number)] = null;
      revision += 1;
      return { ...entry(), operation_id: body.operation_id };
    },
  );
  const engine = new GameIntents("alice", {
    remove,
    member: () => "alice",
    read: async () => entry(),
    write,
    changed: () =>
      client.invalidateQueries({ queryKey: ["two-games"] }, { throwOnError: true }),
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GameIntentContext.Provider value={engine}>
          <GroupGamePage />
        </GameIntentContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const done = () => {
    client.clear();
    engine.dispose();
  };
  return { write, remove, engine, done };
}

const card = (number: number) => screen.getByTestId(`group-card-fixture-${number}`);
const choice = (name: string) => screen.getByRole("button", { name });
// Batch 238: every competition starts folded, so open the first before choosing in it.
const ready = async (name: string) => {
  const first = await screen.findByRole("button", { name: /Scottish Premiership/ });
  if (first.getAttribute("aria-expanded") === "false") fireEvent.click(first);
  await waitFor(() => expect(choice(name)).toBeEnabled());
};
const status = () => screen.getByRole("region", { name: "Group progress and result" });

afterEach(() => {
  vi.clearAllMocks();
});

describe("the Saturday group on the old coupon layout", () => {
  it("greys out another member's fixture as theirs and marks the member's own game", async () => {
    const { done } = harness({ 1: claimOf("bob", 1), 2: claimOf("alice", 2) });
    await ready("Choose Home 3 to win");
    expect(within(card(1)).getByText("Picked by Bob")).toBeTruthy();
    for (const button of within(card(1)).getAllByRole("button"))
      expect(button).toBeDisabled();
    expect(within(card(1)).getByText("Bob’s pick")).toBeTruthy();
    expect(within(card(2)).getByText("Your game")).toBeTruthy();
    expect(choice("Choose Home 2 to win")).toHaveAttribute("aria-pressed", "true");
    expect(choice("Choose Away 2 to win")).toBeEnabled();
    expect(within(card(3)).queryByTestId("group-claim-fixture-3")).toBeNull();
    expect(status()).toHaveTextContent("Pick submitted");
    expect(status()).toHaveTextContent("2 of 4 contributed · 2 missing contributors.");
    expect(status()).toHaveTextContent("Your saved contribution: Home 2");
    expect(status()).toHaveTextContent("Picks lock in");
    done();
  });

  it("saves a tapped selection as the one contribution, and another tap switches it", async () => {
    const { write, engine, done } = harness({ 2: claimOf("alice", 2) });
    await ready("Choose Home 3 to win");
    fireEvent.click(choice("Choose Home 3 to win"));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(write.mock.calls[0][0]).toBe(`${gamePath(target)}/pick`);
    expect(write.mock.calls[0][1]).toMatchObject({
      fixture_id: "fixture-3",
      market: "MATCH_ODDS",
      outcome: "HOME",
      expected_revision: 1,
    });
    await waitFor(() => expect(engine.getSnapshot()[0].phase).toBe("confirmed"));
    await waitFor(() => expect(within(card(3)).getByText("Your game")).toBeTruthy());
    expect(within(card(3)).getByTestId("intent-0")).toHaveTextContent(
      "Saved choice confirmed.",
    );
    expect(within(card(2)).queryByTestId("group-claim-fixture-2")).toBeNull();
    expect(status()).toHaveTextContent("Your saved contribution: Home 3");

    fireEvent.click(within(card(3)).getByRole("button", { name: "Choose Draw" }));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(2));
    expect(write.mock.calls[1][1]).toMatchObject({
      fixture_id: "fixture-3",
      outcome: "DRAW",
      expected_revision: 2,
    });
    await waitFor(() =>
      expect(status()).toHaveTextContent("Your saved contribution: Draw"),
    );
    done();
  });

  it("asks for a pick until there is one, with the coupon empty", async () => {
    const { done } = harness({});
    await ready("Choose Home 1 to win");
    expect(status()).toHaveTextContent("Pick required");
    expect(status()).toHaveTextContent("No pick yet — tap a selection to make it yours.");
    expect(screen.getByTestId("group-coupon")).toHaveTextContent("No picks yet");
    expect(screen.queryByRole("button", { name: "Copy text" })).toBeNull();
    done();
  });

  it("starts every competition open, counting the games already picked", async () => {
    const { done } = harness({ 1: claimOf("bob", 1), 2: claimOf("alice", 2) });
    await screen.findByRole("button", { name: /Scottish Premiership/ });
    const first = within(screen.getByTestId("group-competition-scotland-premiership"));
    // Batch 245 (owner-approved, 25 Nov 2026): every competition starts open, with a jump
    // chip each carrying the same count as its header.
    expect(first.getByRole("button", { name: /Scottish Premiership/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("button", { name: /Scottish Championship/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(first.getByText("2/3")).toBeTruthy();
    await waitFor(() => expect(choice("Choose Home 4 to win")).toBeEnabled());
    expect(choice("Choose Home 3 to win")).toBeEnabled();
    const chips = screen.getByRole("navigation", { name: "Group competitions" });
    expect(within(chips).getByRole("link", { name: /Scottish Premiership/ })).toHaveTextContent(
      "2/3",
    );
    done();
  });

  it("saves both teams to score from its sheet, behind the row's fourth button", async () => {
    // Batch 245 (owner, 25 Nov 2026): rows shaped like Fantasy's, with the two
    // both-teams-to-score selections one tap further, in a sheet.
    const { write, done } = harness(
      {},
      {
        shape: (value) => ({
          ...value,
          fixtures: value.fixtures.map((fixture) =>
            fixture.fixture_id === "fixture-3"
              ? {
                  ...fixture,
                  allowed_markets: [
                    ...fixture.allowed_markets,
                    { market: "BOTH_TEAMS_TO_SCORE", outcomes: ["YES", "NO"] },
                  ],
                }
              : fixture,
          ),
        }),
      },
    );
    await ready("Choose Home 3 to win");
    expect(within(card(2)).queryByRole("button", { name: "Both teams to score" })).toBeNull();
    fireEvent.click(within(card(3)).getByRole("button", { name: "Both teams to score" }));
    const sheet = await screen.findByRole("dialog", { name: /Both teams to score/ });
    fireEvent.click(within(sheet).getByRole("button", { name: "Choose Both teams score" }));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(write.mock.calls[0][1]).toMatchObject({
      fixture_id: "fixture-3",
      market: "BOTH_TEAMS_TO_SCORE",
      outcome: "YES",
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    done();
  });

  it("puts the member's pick first, with Change taking them to their fixture", async () => {
    // Batch 246: the pick, then who is in (a dot each), then the coupon card.
    const { done } = harness({ 1: claimOf("bob", 1), 2: claimOf("alice", 2) });
    await ready("Choose Home 3 to win");
    const mine = within(status()).getByTestId("group-my-pick");
    expect(mine).toHaveTextContent("Home 2");
    const dots = within(status()).getByTestId("group-member-dots");
    expect(dots.children).toHaveLength(4);
    expect(mine.compareDocumentPosition(dots)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    fireEvent.click(within(mine).getByRole("button", { name: "Change" }));
    await waitFor(() =>
      expect(document.activeElement).toBe(choice("Choose Home 2 to win")),
    );
    done();
  });

  it("lists each leg with its picker's initials, the copy in the coupon's header", async () => {
    const { done } = harness({ 1: claimOf("bob", 1), 2: claimOf("alice", 2) });
    await ready("Choose Home 3 to win");
    const coupon = screen.getByTestId("group-coupon");
    expect(within(coupon).getByTestId("group-leg-0")).toHaveTextContent(/^BS/);
    expect(within(coupon).getByTestId("group-leg-1")).toHaveTextContent(/^AL/);
    const header = coupon.firstElementChild as HTMLElement;
    expect(within(header).getByRole("button", { name: /^Copy/ })).toBeTruthy();
    done();
  });

  it("withdraws the member's own pick when it is tapped again", async () => {
    const { write, remove, engine, done } = harness({ 2: claimOf("alice", 2) });
    await ready("Choose Home 2 to win");
    fireEvent.click(choice("Choose Home 2 to win"));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
    expect(remove.mock.calls[0][0]).toBe(`${gamePath(target)}/pick`);
    expect(remove.mock.calls[0][1]).toEqual({
      expected_revision: 1,
      operation_id: expect.any(String),
    });
    await waitFor(() => expect(engine.getSnapshot()[0].phase).toBe("confirmed"));
    await waitFor(() => expect(within(card(2)).queryByText("Your game")).toBeNull());
    expect(status()).toHaveTextContent("Pick required");
    expect(write).not.toHaveBeenCalled();
    done();
  });

  it("names who is still to pick and shows each club's position and form", async () => {
    const { done } = harness(
      { 1: claimOf("bob", 1) },
      {
        shape: (value) => ({
          ...value,
          still_to_pick: [
            { player_id: "alice", display_name: "Alice" },
            { player_id: "carol", display_name: "Carol" },
          ],
          fixtures: value.fixtures.map((fixture) =>
            fixture.fixture_id === "fixture-3"
              ? {
                  ...fixture,
                  competition: "Premiership",
                  context: {
                    home: {
                      team_id: "home-3",
                      name: "Home 3",
                      position: 2,
                      played: 10,
                      points: null,
                      goal_difference: 4,
                      form: "WWW",
                      recent: [],
                    },
                    away: null,
                  },
                }
              : fixture,
          ),
        }),
      },
    );
    await ready("Choose Home 3 to win");
    expect(screen.getByTestId("group-still-to-pick")).toHaveTextContent(
      "Still to pick: Alice, Carol",
    );
    expect(status()).toHaveTextContent("1 of 4 contributed · 3 missing contributors.");
    expect(within(card(3)).getByTestId("club-context-home-3")).toHaveTextContent("2nd");
    expect(screen.getByTestId("group-game")).not.toHaveTextContent(/odds|points/i);
    done();
  });

  it("opens a week's only competition, so the screen never starts empty", async () => {
    const { done } = harness({}, { single: true });
    await waitFor(() => expect(choice("Choose Home 4 to win")).toBeEnabled());
    expect(screen.getByRole("button", { name: /Scottish Premiership/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    done();
  });

  it("puts the payment strip, the status card and the coupon above the fixtures", async () => {
    const { done } = harness({ 2: claimOf("alice", 2) });
    await ready("Choose Home 3 to win");
    const fixtures = screen.getByTestId("group-competition-scotland-premiership");
    const above = [
      screen.getByRole("region", { name: "Payment for 28 Nov" }),
      status(),
      screen.getByTestId("group-coupon"),
    ];
    for (const element of above)
      expect(element.compareDocumentPosition(fixtures)).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      );
    expect(above[0].compareDocumentPosition(above[1])).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    done();
  });

  it("lists every leg with the fold and copies the coupon for the group chat, unpriced", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    const { done } = harness({ 1: claimOf("bob", 1), 2: claimOf("alice", 2) });
    await ready("Choose Home 3 to win");
    const coupon = screen.getByTestId("group-coupon");
    expect(within(coupon).getByTestId("group-fold")).toHaveTextContent("2-fold");
    expect(coupon).toHaveTextContent("2 of 4 still to pick");
    expect(within(coupon).getByTestId("group-leg-0")).toHaveTextContent("Bob Smith — Home 1");
    expect(within(coupon).getByTestId("group-leg-1")).toHaveTextContent("Alice — Home 2");
    expect(screen.getByTestId("group-game")).not.toHaveTextContent(/odds|points/i);
    fireEvent.click(within(coupon).getByRole("button", { name: "Copy text" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0][0]).toBe(
      [
        "The Coupon — Saturday Group · 28 Nov",
        "2-fold accumulator — 2 of 4 still to pick",
        "",
        "1. Bob Smith — Home 1 (v Away 1)",
        "2. Alice — Home 2 (v Away 2)",
      ].join("\n"),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Coupon copied"));
    Reflect.deleteProperty(navigator, "clipboard");
    done();
  });
});
