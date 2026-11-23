import { describe, it, expect, vi } from "vitest";
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
      competition_id: "scotland-premiership",
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
    path === gamePath(target) ? view(picks) : read(slotOf(path)),
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
  const engine = new GameIntents("alice", {
    member: () => "alice",
    read: async (path) => read(slotOf(path)),
    write,
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
  return { write, engine, done };
}

const price = (name: string) => screen.getByRole("button", { name });
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
      expect(screen.getByRole("button", { name: "Replace slot 6" })).toBeEnabled(),
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

  it("points the fixture list at one slot from Fill slot until Done", async () => {
    const { write, engine, done } = harness();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Fill slot 3" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Fill slot 3" }));
    const list = screen.getByRole("region", { name: "Choose fixture for slot 3" });
    fireEvent.click(within(list).getByRole("button", { name: "Choose Home 1 to win at 2.1500" }));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(write.mock.calls[0][0]).toBe(`${gamePath(target)}/slots/3`);
    await waitFor(() => expect(engine.getSnapshot()[0].phase).toBe("confirmed"));
    expect(screen.getByRole("region", { name: "Choose fixture for slot 3" })).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Done" })[0]);
    expect(screen.getByRole("region", { name: "Fantasy fixtures" })).toBeTruthy();
    await ready("Choose Home 2 to win at 2.1500");
    fireEvent.click(price("Choose Home 2 to win at 2.1500"));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(2));
    expect(write.mock.calls[1][0]).toBe(`${gamePath(target)}/slots/1`);
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
    const weeks = screen.getByRole("navigation", { name: "Fantasy weeks" });
    expect(
      within(weeks)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["21 Nov · Results", "28 Nov · Open"]);
    expect(within(weeks).getByRole("link", { name: "28 Nov · Open" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    done();
  });
});
