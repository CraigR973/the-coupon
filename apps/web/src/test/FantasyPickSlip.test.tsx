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
import { FantasyWeekPage } from "../pages/FantasyWeekPage";
import {
  GameIntentContext,
  GameNavigationContext,
} from "../hooks/useGameIntents";
import { GameIntents, type GameIntent } from "../lib/gameIntents";
import {
  gamePath,
  type FantasyGame,
  type GameCard,
  type GameEntry,
  type GamePick,
  type LeagueGames,
} from "../lib/twoGameTypes";

/**
 * Batch 232: the fantasy week fills like a betting slip. A tapped price saves straight
 * into the slip with no slot opened first, a second price on the same fixture swaps that
 * pick, and a seventh asks which pick it replaces. Writes go through a stateful fake of
 * the slot API, so each save's readback is what decides where the next tap lands — as
 * it does against the real API.
 */
const target = {
  league_id: "league-a",
  week_id: "week-a",
  game_kind: "fantasy" as const,
};
const { api } = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  apiFetch: api,
}));
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({ player: { id: "alice" } }),
}));
vi.mock("../hooks/useGameRoute", () => ({ useGameRoute: () => target }));
vi.mock("../hooks/useExpiry", () => ({
  useExpiry: (value: string) => value === "opens",
}));

const slotOf = (path: string) => Number(path.split("/").at(-1));
const fixtureNumber = (id: string) => Number(id.split("-").at(-1));

function saved(slot: number, fixture: number, extra: Partial<GamePick> = {}): GamePick {
  return {
    id: `pick-${slot}`,
    fixture_id: `fixture-${fixture}`,
    player_id: "alice",
    market: "MATCH_ODDS",
    outcome: "HOME",
    runner_name: `Home ${fixture}`,
    revision: 1,
    operation_id: `operation-${slot}`,
    result: "pending",
    frozen_odds: "2.1500",
    points: 0,
    ...extra,
  };
}

// Batch 238: a test may spread the card over two competitions; the rest use one.
let competitionOf = (_fixture: number) => "scotland-premiership";
afterEach(() => {
  competitionOf = () => "scotland-premiership";
});

function view(picks: Record<number, GamePick | null>): FantasyGame {
  const filled = Object.values(picks).filter(Boolean).length;
  return {
    ...target,
    game_id: "game-a",
    week_label: "2026-11-28",
    destination: "/leagues/league-a/weeks/week-a/fantasy",
    opens_at: "opens",
    locks_at: "locks",
    window_start: "2026-11-28T12:30:00Z",
    window_end: "2026-11-30T00:00:00Z",
    entry_state: "open",
    coverage_state: "complete",
    slots: [1, 2, 3, 4, 5, 6].map((slot) => ({
      ...target,
      slot,
      game_id: "game-a",
      revision: picks[slot] ? 1 : 0,
      operation_id: null,
      pick: picks[slot] ?? null,
    })),
    progress: { filled_count: filled, slot_count: 6, partial: filled > 0 && filled < 6 },
    result: { status: filled ? "pending" : "no_entry", points: 0, provisional: true },
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
    fixtures: [1, 2, 3, 4, 5, 6, 7].map((i) => ({
      fixture_id: `fixture-${i}`,
      home: `Home ${i}`,
      away: `Away ${i}`,
      competition_id: competitionOf(i),
      kickoff_at: `2026-11-28T15:0${i}:00Z`,
      status: "pending",
      eligible: true,
      quote: {
        prices: [
          { market: "MATCH_ODDS", outcome: "HOME", odds: "2.1500" },
          { market: "MATCH_ODDS", outcome: "AWAY", odds: "3.0000" },
        ],
        provider: "synthetic",
        bookmaker: "Betfair Sportsbook",
        observed_at: "2026-11-28T11:00:00Z",
        age_seconds: 0,
        availability: "available",
        degraded: false,
      },
    })),
  };
}

function harness(
  initial: Record<number, GamePick> = {},
  leagues: LeagueGames[] = [],
  shape: (fixtures: FantasyGame["fixtures"]) => FantasyGame["fixtures"] = (fixtures) => fixtures,
) {
  const picks: Record<number, GamePick | null> = { ...initial };
  const revisions: Record<number, number> = {};
  for (const slot of [1, 2, 3, 4, 5, 6]) revisions[slot] = initial[slot] ? 1 : 0;
  const read = (slot: number): GameEntry => ({
    ...target,
    slot,
    game_id: "game-a",
    revision: revisions[slot],
    operation_id: null,
    pick: picks[slot] ?? null,
  });
  api.mockImplementation(async (path: string) =>
    path === gamePath(target)
      ? { ...view(picks), fixtures: shape(view(picks).fixtures) }
      : read(slotOf(path)),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const write = vi.fn(async (path: string, body: GameIntent["body"]) => {
    const slot = slotOf(path);
    revisions[slot] += 1;
    picks[slot] = saved(slot, fixtureNumber(body.fixture_id), {
      outcome: body.outcome,
      runner_name: `${body.outcome === "HOME" ? "Home" : "Away"} ${fixtureNumber(body.fixture_id)}`,
      frozen_odds: body.odds,
      revision: revisions[slot],
      operation_id: body.operation_id,
    });
    return { ...read(slot), operation_id: body.operation_id };
  });
  // Batch 235: a removal empties its slot at the next revision, as the API's DELETE does.
  const remove = vi.fn(
    async (path: string, body: { expected_revision: number; operation_id: string }) => {
      const slot = slotOf(path);
      revisions[slot] += 1;
      picks[slot] = null;
      return { ...read(slot), operation_id: body.operation_id };
    },
  );
  const engine = new GameIntents("alice", {
    member: () => "alice",
    read: async (path) => read(slotOf(path)),
    write,
    remove,
    changed: () =>
      client.invalidateQueries({ queryKey: ["two-games"] }, { throwOnError: true }),
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GameNavigationContext.Provider value={leagues}>
          <GameIntentContext.Provider value={engine}>
            <FantasyWeekPage />
          </GameIntentContext.Provider>
        </GameNavigationContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const done = () => {
    client.clear();
    engine.dispose();
  };
  return { write, remove, engine, done };
}

const price = (name: string) => screen.getByRole("button", { name });
// Batch 235: one club's table context, as the API sends it on a fixture.
const club = (team_id: string, name: string, position: number | null, form: string) => ({
  team_id,
  name,
  position,
  played: 10,
  points: 20,
  goal_difference: 1,
  form,
  recent: [],
});
const ready = (name: string) =>
  waitFor(() => expect(price(name)).toBeEnabled());

describe("the fantasy pick slip", () => {
  it("saves a tapped price straight into the first free slot, with no slot opened first", async () => {
    const { write, engine, done } = harness();
    await ready("Choose Home 1 to win at 2.1500");
    expect(screen.getByRole("region", { name: "Fantasy fixtures" })).toBeTruthy();
    fireEvent.click(price("Choose Home 1 to win at 2.1500"));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(write.mock.calls[0][0]).toBe(`${gamePath(target)}/slots/1`);
    expect(write.mock.calls[0][1]).toMatchObject({
      fixture_id: "fixture-1",
      market: "MATCH_ODDS",
      outcome: "HOME",
      odds: "2.1500",
      expected_revision: 0,
    });
    await waitFor(() => expect(engine.getSnapshot()[0].phase).toBe("confirmed"));
    await waitFor(() =>
      expect(
        screen.getByRole("article", { name: "Fantasy slot 1" }),
      ).toHaveTextContent("Home 1 · Frozen odds 2.1500"),
    );
    expect(price("Choose Home 1 to win at 2.1500")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const status = within(
      screen.getByRole("article", { name: "Fantasy slot 1" }),
    ).getByTestId("intent-1");
    expect(status).toHaveTextContent("Saved choice confirmed.");
    expect(status).not.toHaveTextContent("Choice:");
    done();
  });

  it("puts each new fixture in the next free slot as the slip fills", async () => {
    const { write, engine, done } = harness({ 1: saved(1, 1) });
    await ready("Choose Home 2 to win at 2.1500");
    fireEvent.click(price("Choose Home 2 to win at 2.1500"));
    await waitFor(() => expect(engine.getSnapshot()[0]?.phase).toBe("confirmed"));
    await ready("Choose Away 3 to win at 3.0000");
    fireEvent.click(price("Choose Away 3 to win at 3.0000"));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(2));
    expect(write.mock.calls.map((call) => call[0])).toEqual([
      `${gamePath(target)}/slots/2`,
      `${gamePath(target)}/slots/3`,
    ]);
    expect(write.mock.calls[1][1]).toMatchObject({
      fixture_id: "fixture-3",
      outcome: "AWAY",
      odds: "3.0000",
    });
    done();
  });

  it("swaps the pick when another price is tapped on a fixture already in the slip", async () => {
    const { write, done } = harness({ 3: saved(3, 1) });
    await ready("Choose Away 1 to win at 3.0000");
    expect(price("Choose Home 1 to win at 2.1500")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByTestId("fantasy-card-fixture-1")).toHaveTextContent(
      "Your pick · slot 3",
    );
    fireEvent.click(price("Choose Away 1 to win at 3.0000"));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(write.mock.calls[0][0]).toBe(`${gamePath(target)}/slots/3`);
    expect(write.mock.calls[0][1]).toMatchObject({
      fixture_id: "fixture-1",
      outcome: "AWAY",
      expected_revision: 1,
    });
    done();
  });

  it("asks which pick to swap once all six are in, and saves only to the slot named", async () => {
    const full = Object.fromEntries(
      [1, 2, 3, 4, 5, 6].map((slot) => [slot, saved(slot, slot)]),
    );
    const { write, done } = harness(full);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Remove slot 6" })).toBeEnabled(),
    );
    fireEvent.click(price("Choose Home 7 to win at 2.1500"));
    const sheet = await screen.findByRole("dialog", { name: "Swap a pick" });
    expect(write).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        within(sheet).getByRole("button", { name: "Swap slot 4 for Home 7 to win" }),
      ).toBeEnabled(),
    );
    fireEvent.click(
      within(sheet).getByRole("button", { name: "Swap slot 4 for Home 7 to win" }),
    );
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(write.mock.calls[0][0]).toBe(`${gamePath(target)}/slots/4`);
    expect(write.mock.calls[0][1]).toMatchObject({
      fixture_id: "fixture-7",
      outcome: "HOME",
      expected_revision: 1,
    });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Swap a pick" })).toBeNull(),
    );
    done();
  });

  it("keeps the count and the points still possible in the bar, which opens the slip", async () => {
    const { done } = harness({
      1: saved(1, 1),
      2: saved(2, 2, { result: "won", points: 30, frozen_odds: "3.0000" }),
      3: saved(3, 3, { result: "lost", frozen_odds: "4.0000" }),
    });
    const bar = await screen.findByRole("button", { name: /Your picks 3 of 6/ });
    expect(bar).toHaveTextContent("up to 52 pts");
    fireEvent.click(bar);
    const slip = await screen.findByRole("dialog", { name: "Your picks · 3 of 6" });
    expect(within(slip).getAllByRole("article")).toHaveLength(6);
    expect(within(slip).getByRole("article", { name: "Fantasy slot 2" })).toHaveTextContent(
      "Won · 30 points",
    );
    done();
  });

  it("removes a pick from its slot, or with a second tap on its own price", async () => {
    const { write, remove, engine, done } = harness({ 1: saved(1, 1), 2: saved(2, 2) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Remove slot 2" })).toBeEnabled(),
    );
    expect(screen.queryByRole("button", { name: /^(Fill|Replace) slot/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Remove slot 2" }));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
    expect(remove.mock.calls[0][0]).toBe(`${gamePath(target)}/slots/2`);
    expect(remove.mock.calls[0][1]).toEqual({
      expected_revision: 1,
      operation_id: expect.any(String),
    });
    await waitFor(() => expect(engine.getSnapshot()[0].phase).toBe("confirmed"));
    await waitFor(() =>
      expect(screen.getByRole("article", { name: "Fantasy slot 2" })).toHaveTextContent(
        "Empty slot",
      ),
    );
    await waitFor(() =>
      expect(price("Choose Home 1 to win at 2.1500")).toHaveAttribute(
        "aria-disabled",
        "false",
      ),
    );
    fireEvent.click(price("Choose Home 1 to win at 2.1500"));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(2));
    expect(remove.mock.calls[1][0]).toBe(`${gamePath(target)}/slots/1`);
    expect(write).not.toHaveBeenCalled();
    done();
  });

  it("shows each club's position and form and the competition's own name", async () => {
    competitionOf = () => "scotland-premiership";
    const { done } = harness({}, [], (fixtures) =>
      fixtures.map((fixture, index) =>
        index === 0
          ? {
              ...fixture,
              competition: "Premiership",
              context: {
                home: club("home-1", "Home 1", 3, "WWDLW"),
                away: club("away-1", "Away 1", null, "LL"),
              },
            }
          : { ...fixture, competition: "Premiership" },
      ),
    );
    await ready("Choose Home 1 to win at 2.1500");
    expect(screen.getByRole("button", { name: /^Premiership/ })).toBeTruthy();
    const card = screen.getByTestId("fantasy-card-fixture-1");
    expect(within(card).getByTestId("club-context-home-1")).toHaveTextContent("3rd");
    expect(within(card).getByTestId("club-context-away-1")).toBeTruthy();
    expect(
      within(screen.getByTestId("fantasy-card-fixture-2")).queryByTestId(/^club-context-/),
    ).toBeNull();
    done();
  });

  it("heads the screen with the Group and Fantasy switch and the fantasy weeks on screen", async () => {
    const card = (
      kind: "group" | "fantasy",
      week: string,
      purpose: string,
      extra: Partial<GameCard> = {},
    ): GameCard =>
      ({
        league_id: "league-a",
        week_id: week,
        game_kind: kind,
        game_id: `${kind}-${week}`,
        week_label: week === "week-a" ? "2026-11-28" : "2026-11-21",
        week_number: "1",
        destination: `/leagues/league-a/weeks/${week}/${kind}`,
        opens_at: "2026-11-21T12:00:00Z",
        locks_at: "2026-11-28T12:00:00Z",
        entry_state: purpose === "entry" ? "open" : "locked",
        purpose,
        archived: false,
        fee: {} as GameCard["fee"],
        coverage_state: "complete",
        result_version: 1,
        progress: {},
        result: { final: false },
        ...extra,
      }) as GameCard;
    const league: LeagueGames = {
      league_id: "league-a",
      slug: "two-one-hibs",
      name: "2-1 Hibs",
      two_games_enabled: true,
      suspended: false,
      server_now: "2026-11-24T10:00:00Z",
      games: [
        card("group", "week-a", "entry", {
          my_entry: {
            league_id: "league-a",
            week_id: "week-a",
            game_id: "g",
            game_kind: "group",
            revision: 0,
            operation_id: null,
            pick: null,
          },
        }),
        card("fantasy", "week-a", "entry", { progress: { slots_filled: 2 } }),
        card("fantasy", "week-z", "results"),
      ],
      legacy_rounds: [],
      next_cursor: null,
      next_game_state: "known",
      next_game_opens_at: null,
      season_stats: null,
      weekly_form: [],
    };
    const { done } = harness({}, [league]);
    const games = await screen.findByRole("navigation", { name: "Game switch" });
    const group = within(games).getByRole("link", { name: /Group/ });
    expect(group).toHaveAttribute("href", "/leagues/league-a/weeks/week-a/group");
    expect(group).toHaveTextContent("Pick needed");
    const fantasy = within(games).getByRole("link", { name: /Fantasy/ });
    expect(fantasy).toHaveAttribute("aria-current", "page");
    expect(fantasy).toHaveTextContent("2 of 6 picked");
    // Batch 244 (owner-approved, 25 Nov 2026): the week bar replaces the week chips. 21 Nov's
    // results are still coming in, so it is this week, and 28 Nov is next week, one arrow on.
    const weeks = screen.getByRole("navigation", { name: "Game navigation" });
    expect(within(weeks).getByText("Next week")).toBeTruthy();
    expect(within(weeks).getByText("Sat 28 Nov")).toBeTruthy();
    expect(
      within(weeks).getByRole("link", { name: "Earlier week, Sat 21 Nov" }),
    ).toHaveAttribute("href", "/leagues/league-a/weeks/week-z/fantasy");
    expect(within(weeks).queryByRole("link", { name: /^Next week/ })).toBeNull();
    done();
  });

  it("starts every competition open under its header, with a chip to jump to each", async () => {
    competitionOf = (fixture) =>
      fixture <= 4 ? "scotland-premiership" : "scotland-championship";
    const { done } = harness();
    const first = await screen.findByRole("button", { name: /Scottish Premiership/ });
    const second = screen.getByRole("button", { name: /Scottish Championship/ });
    // Batch 245 (owner-approved, 25 Nov 2026): every competition starts open, and a fold
    // the member makes is undone by that competition's jump chip.
    expect(first).toHaveAttribute("aria-expanded", "true");
    expect(second).toHaveAttribute("aria-expanded", "true");
    await ready("Choose Home 1 to win at 2.1500");
    expect(screen.getByRole("button", { name: /^Choose Home 5 to win/ })).toBeTruthy();
    const chips = screen.getByRole("navigation", { name: "Fantasy competitions" });
    const jump = within(chips).getByRole("link", { name: /Scottish Championship/ });
    expect(jump).toHaveAttribute("href", "#fantasy-competition-scotland-championship");
    fireEvent.click(second);
    expect(second).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /^Choose Home 5 to win/ })).toBeNull();
    fireEvent.click(jump);
    expect(second).toHaveAttribute("aria-expanded", "true");
    done();
  });

  it("folds fixtures without prices into one row at the end of their competition", async () => {
    // Batch 245: most of a real card is unpriced (lower leagues), so those wait in one row.
    const { done } = harness({}, [], (fixtures) =>
      fixtures.map((fixture, index) =>
        index >= 5
          ? { ...fixture, quote: { ...fixture.quote, prices: [], availability: "unavailable" } }
          : fixture,
      ),
    );
    await ready("Choose Home 1 to win at 2.1500");
    expect(screen.queryByTestId("fantasy-card-fixture-6")).toBeNull();
    const fold = screen.getByRole("button", { name: "2 fixtures without prices yet" });
    expect(fold).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(fold);
    expect(
      within(screen.getByTestId("fantasy-card-fixture-6")).getByText("No prices yet."),
    ).toBeTruthy();
    expect(screen.getByTestId("fantasy-card-fixture-7")).toBeTruthy();
    done();
  });

  it("keeps a held fixture in view after its prices go", async () => {
    const { done } = harness({ 1: saved(1, 6) }, [], (fixtures) =>
      fixtures.map((fixture, index) =>
        index >= 5
          ? { ...fixture, quote: { ...fixture.quote, prices: [], availability: "unavailable" } }
          : fixture,
      ),
    );
    await waitFor(() =>
      expect(
        within(screen.getByTestId("fantasy-card-fixture-6")).getByText("Your pick · slot 1"),
      ).toBeTruthy(),
    );
    expect(screen.getByRole("button", { name: "1 fixture without prices yet" })).toBeTruthy();
    done();
  });

  it("shows the picks as tiles, a held one removed by a tap and an empty one leading to the fixtures", async () => {
    // Batch 246: one "Your picks" card of six compact tiles.
    const { remove, done } = harness({ 1: saved(1, 1) });
    await ready("Choose Home 2 to win at 2.1500");
    const card = screen.getByRole("complementary", { name: "Your Fantasy picks" });
    expect(within(card).getAllByRole("article")).toHaveLength(6);
    expect(within(card).getByRole("heading", { name: "Your picks" })).toBeTruthy();
    const empty = within(card).getByRole("article", { name: "Fantasy slot 2" });
    fireEvent.click(within(empty).getByRole("button", { name: "Pick for slot 2" }));
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("region", { name: "Fantasy fixtures" })),
    );
    fireEvent.click(within(card).getByRole("button", { name: "Remove slot 1" }));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
    expect(remove.mock.calls[0][0]).toBe(`${gamePath(target)}/slots/1`);
    done();
  });

  it("keeps the picks bar slim: how many, what they can score, and Review", async () => {
    const { done } = harness({ 1: saved(1, 1) });
    const bar = await screen.findByRole("button", { name: /Your picks 1 of 6/ });
    expect(bar).toHaveTextContent("1 of 6");
    expect(bar).toHaveTextContent("Review");
    done();
  });

  it("opens a week's only competition and leads with the payment strip", async () => {
    const { done } = harness();
    await ready("Choose Home 1 to win at 2.1500");
    expect(screen.getByRole("button", { name: /Scottish Premiership/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    const strip = screen.getByRole("region", { name: "Payment for 28 Nov" });
    expect(strip.compareDocumentPosition(screen.getByTestId("fantasy-slate"))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    done();
  });

  it("drops the recent weeks and the refresh button from the fantasy screen", async () => {
    const league = {
      league_id: "league-a",
      slug: "two-one-hibs",
      name: "2-1 Hibs",
      two_games_enabled: true,
      suspended: false,
      server_now: "2026-11-24T10:00:00Z",
      games: [],
      legacy_rounds: [],
      next_cursor: null,
      next_game_state: "known",
      next_game_opens_at: null,
      season_stats: null,
      weekly_form: [
        {
          week_id: "week-z",
          week_label: "2026-11-21",
          format: "fantasy",
          destination: "/leagues/league-a/weeks/week-z/fantasy",
          status: "final",
          weekly_points: 21,
        },
      ],
    } as unknown as LeagueGames;
    const { done } = harness({}, [league]);
    await ready("Choose Home 1 to win at 2.1500");
    expect(screen.queryByRole("region", { name: "Your recent weeks" })).toBeNull();
    expect(screen.queryByText("Your recent weeks")).toBeNull();
    expect(screen.queryByRole("button", { name: "Refresh prices and results" })).toBeNull();
    expect(screen.getByRole("button", { name: "Check payment status" })).toBeEnabled();
    done();
  });
});
