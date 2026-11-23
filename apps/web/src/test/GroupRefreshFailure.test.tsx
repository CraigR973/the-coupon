import { afterEach, describe, it, expect, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GroupGamePage } from "../pages/GroupGamePage";
import { GameIntentContext } from "../hooks/useGameIntents";
import { GameIntents } from "../lib/gameIntents";
import { ApiError, NetworkError } from "../lib/api";
import { gamePath, type GameEntry, type GroupGame } from "../lib/twoGameTypes";

/**
 * Batch 236: a refresh of the group game that fails on the connection — the 30-second
 * poll, or the refetch when a member comes back from the group chat — keeps the last view
 * with a notice, as the fantasy week does. A failed first load, or a refusal from the
 * server, still shows the unavailable screen.
 */
const target = {
  league_id: "league-a",
  week_id: "week-a",
  game_kind: "group" as const,
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
  useExpiry: (value: string) => value.includes("opens"),
}));

const claim = (player_id: string, display_name: string, number: number) => ({
  player_id,
  display_name,
  market: "MATCH_ODDS",
  outcome: "HOME",
  runner_name: `Home ${number}`,
  result: "pending",
});
const mine = {
  id: "pick-alice",
  fixture_id: "fixture-2",
  player_id: "alice",
  market: "MATCH_ODDS",
  outcome: "HOME",
  runner_name: "Home 2",
  revision: 1,
  operation_id: "operation",
  result: "pending",
};
const game: GroupGame = {
  ...target,
  game_id: "game-a",
  week_label: "2026-11-28",
  week_number: "1",
  destination: "/",
  opens_at: "opens",
  locks_at: "locks",
  entry_state: "open",
  coverage_state: "complete",
  my_entries: [mine],
  progress: { picked_count: 2, member_count: 4, all_picked: false },
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
  fixtures: [1, 2, 3].map((number) => ({
    fixture_id: `fixture-${number}`,
    home: `Home ${number}`,
    away: `Away ${number}`,
    competition_id: "scotland-premiership",
    kickoff_at: "2026-11-28T15:00:00Z",
    status: "pending",
    eligible: true,
    claim:
      number === 1 ? claim("bob", "Bob", 1) : number === 2 ? claim("alice", "Alice", 2) : null,
    allowed_markets: [{ market: "MATCH_ODDS", outcomes: ["HOME", "DRAW", "AWAY"] }],
  })),
};
const entry: GameEntry = {
  ...target,
  game_id: "game-a",
  revision: 1,
  operation_id: null,
  pick: mine,
};

/** Answers every read; `failGame` decides what the group game's own read does. */
function serve(failGame: () => Error | null) {
  api.mockImplementation(async (path: string) => {
    if (path === gamePath(target)) {
      const failure = failGame();
      if (failure) throw failure;
      return game;
    }
    return entry;
  });
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const engine = new GameIntents("alice", {
    member: () => "alice",
    read: async () => entry,
    write: vi.fn(),
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
  const refresh = () =>
    act(async () => {
      await client.refetchQueries({ queryKey: ["two-games"] });
    });
  const done = () => {
    client.clear();
    engine.dispose();
  };
  return { refresh, done };
}

const notice = /Showing the last received view/;
const loaded = () =>
  waitFor(() =>
    expect(screen.getByRole("button", { name: "Choose Home 3 to win" })).toBeEnabled(),
  );

afterEach(() => {
  vi.clearAllMocks();
});

describe("the group screen through a failed refresh", () => {
  it("keeps the fixtures, the status card and the coupon with a notice when the connection drops", async () => {
    let failure: Error | null = null;
    serve(() => failure);
    const { refresh, done } = mount();
    await loaded();
    expect(screen.queryByText(notice)).toBeNull();

    failure = new NetworkError("The network request failed", true);
    await refresh();
    expect(await screen.findByText(notice)).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Group game unavailable" }),
    ).toBeNull();
    expect(
      within(screen.getByTestId("group-card-fixture-1")).getByText("Picked by Bob"),
    ).toBeTruthy();
    expect(
      screen.getByRole("region", { name: "Group progress and result" }),
    ).toHaveTextContent("Your saved contribution: Home 2");
    expect(screen.getByTestId("group-fold")).toHaveTextContent("2-fold");

    failure = null;
    await refresh();
    await waitFor(() => expect(screen.queryByText(notice)).toBeNull());
    done();
  });

  it("still shows the unavailable screen when the server refuses a refresh", async () => {
    let failure: Error | null = null;
    serve(() => failure);
    const { refresh, done } = mount();
    await loaded();
    failure = new ApiError(503, "The service is unavailable");
    await refresh();
    expect(
      await screen.findByRole("heading", { name: "Group game unavailable" }),
    ).toBeVisible();
    expect(screen.queryByTestId("group-game")).toBeNull();
    done();
  });

  it("still shows the unavailable screen when the first load fails on the connection", async () => {
    serve(() => new NetworkError("You are offline", false));
    const { done } = mount();
    expect(
      await screen.findByRole("heading", { name: "Group game unavailable" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(screen.queryByText(notice)).toBeNull();
    done();
  });
});
