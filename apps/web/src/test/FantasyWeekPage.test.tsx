import { describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
  act,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import {
  QueryClient,
  QueryClientProvider,
  onlineManager,
} from "@tanstack/react-query";
import { FantasyWeekPage } from "../pages/FantasyWeekPage";
import { GameIntentContext } from "../hooks/useGameIntents";
import { GameIntents } from "../lib/gameIntents";
import { ApiError, NetworkError } from "../lib/api";
import {
  gamePath,
  type GameEntry,
  type FantasyGame,
} from "../lib/twoGameTypes";
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
const entry = (slot: number, revision = 0): GameEntry => ({
  ...target,
  slot,
  game_id: "game-a",
  revision,
  operation_id: null,
  pick: null,
});
function game(): FantasyGame {
  return {
    ...target,
    game_id: "game-a",
    week_label: "2026-11-21",
    destination: "/",
    opens_at: "opens",
    locks_at: "locks",
    window_start: "2026-11-21T12:30:00Z",
    window_end: "2026-11-23T00:00:00Z",
    entry_state: "open",
    coverage_state: "complete",
    slots: Array.from({ length: 6 }, (_, i) => entry(i + 1)),
    progress: { filled_count: 0, slot_count: 6, partial: false },
    result: { status: "no_entry", points: 0, provisional: true },
    fee: {
      league_id: "league-a",
      week_id: "week-a",
      week_label: "2026-11-21",
      billing_starts_at: "2026-11-16T00:00:00Z",
      billing_ends_at: "2026-11-23T00:00:00Z",
      obligation_pence: 100,
      amount_owed_pence: 0,
      paid_through: true,
      pooled_credit_pence: 0,
      payment_url: null,
      destination: "/",
      obligations: [],
    },
    fixtures: [1, 2].map((i) => ({
      fixture_id: `fixture-${i}`,
      home: `Home ${i}`,
      away: `Away ${i}`,
      competition_id: "synthetic",
      kickoff_at: "2026-11-21T15:00:00Z",
      status: "pending",
      eligible: true,
      quote: {
        prices: [{ market: "MATCH_ODDS", outcome: "HOME", odds: "2.1500" }],
        provider: "synthetic",
        bookmaker: "Bet365",
        observed_at: "2026-11-21T11:50:00Z",
        age_seconds: 0,
        availability: "available",
        degraded: false,
      },
    })),
  };
}
// Batch 235: "Fill slot n" is gone; a verified empty slot reads "Empty slot" instead.
const emptySlot = (n: number) =>
  within(screen.getByRole("article", { name: `Fantasy slot ${n}` })).getByText("Empty slot");
// A second price on fixture 1 aims a tap at the slot that already holds it.
function withAway(value: FantasyGame): FantasyGame {
  return {
    ...value,
    fixtures: value.fixtures.map((fixture) =>
      fixture.fixture_id === "fixture-1"
        ? {
            ...fixture,
            quote: {
              ...fixture.quote,
              prices: [
                ...fixture.quote.prices,
                { market: "MATCH_ODDS", outcome: "AWAY", odds: "3.0000" },
              ],
            },
          }
        : fixture,
    ),
  };
}
function mount(client: QueryClient, engine: GameIntents) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GameIntentContext.Provider value={engine}>
          <FantasyWeekPage />
        </GameIntentContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
describe("Fantasy slot editor", () => {
  it("does not replay abandoned Fantasy route reads on reconnect", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const engine = new GameIntents("alice", { member: () => "alice" });
    // The real shell stays mounted when its route child leaves.
    client.mount();
    api.mockImplementation(async (path: string) =>
      path === gamePath(target)
        ? game()
        : entry(Number(path.split("/").at(-1))),
    );
    const first = mount(client, engine);
    await waitFor(() =>
      expect(emptySlot(6)).toBeTruthy(),
    );
    first.unmount();
    api.mockClear();
    try {
      onlineManager.setOnline(false);
      const abandoned = mount(client, engine);
      await waitFor(() =>
        expect(
          client
            .getQueryCache()
            .getAll()
            .filter((query) => query.state.fetchStatus === "paused"),
        ).toHaveLength(7),
      );
      abandoned.unmount();
      expect(
        client
          .getQueryCache()
          .getAll()
          .filter((query) => query.state.fetchStatus === "paused"),
      ).toHaveLength(0);
      await act(async () => {
        onlineManager.setOnline(true);
      });
      await waitFor(() => expect(client.isFetching()).toBe(0));
      expect(api).not.toHaveBeenCalled();
      const returned = mount(client, engine);
      await waitFor(() =>
        expect(emptySlot(6)).toBeTruthy(),
      );
      expect(api).toHaveBeenCalled();
      returned.unmount();
    } finally {
      onlineManager.setOnline(true);
      client.unmount();
      client.clear();
    }
  });
  it("keeps another slot usable while one save is in flight", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const current = withAway(game());
    api.mockImplementation(async (path: string) =>
      path === gamePath(target)
        ? current
        : entry(Number(path.split("/").at(-1))),
    );
    let release!: (value: GameEntry) => void;
    const paused = new Promise<GameEntry>((resolve) => {
      release = resolve;
    });
    const write = vi.fn(() => paused);
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async (path) => entry(Number(path.split("/").at(-1))),
      write,
      changed: async () => {},
    });
    mount(client, engine);
    await waitFor(() => expect(emptySlot(1)).toBeTruthy());
    fireEvent.click(
      screen.getByRole("button", { name: "Choose Home 1 to win at 2.1500" }),
    );
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    // Slot 1 is busy: another price on its fixture cannot be sent to it yet.
    expect(
      screen.getByRole("button", { name: "Choose Away 1 to win at 3.0000" }),
    ).toBeDisabled();
    expect(emptySlot(2)).toBeTruthy();
    const chooser = screen.getByRole("region", { name: "Fantasy fixtures" });
    expect(
      within(chooser).getByRole("button", {
        name: "Choose Home 1 to win at 2.1500",
      }),
    ).toHaveAttribute("aria-disabled", "true");
    expect(
      within(chooser).getByRole("button", {
        name: "Choose Home 2 to win at 2.1500",
      }),
    ).toBeEnabled();
    release(entry(1, 1));
    await waitFor(() =>
      expect(engine.getSnapshot()[0].phase).toBe("confirmed"),
    );
    client.clear();
    engine.dispose();
  });
  it.each(["success", "failure"])(
    "holds the accepted slot until its authoritative revision refreshes (%s)",
    async (outcome) => {
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      let revision = 0;
      let release!: (value: GameEntry) => void;
      let reject!: (error: Error) => void;
      const paused = new Promise<GameEntry>((resolve, fail) => {
        release = resolve;
        reject = fail;
      });
      api.mockImplementation(async (path: string) =>
        path === gamePath(target)
          ? withAway(game())
          : path.endsWith("/1") && revision === 1
            ? paused
            : entry(Number(path.split("/").at(-1)), revision),
      );
      const write = vi.fn(async () => {
        revision++;
        return entry(1, revision);
      });
      const engine = new GameIntents("alice", {
        member: () => "alice",
        read: async () => entry(1, revision),
        write,
        changed: () =>
          client.invalidateQueries(
            { queryKey: ["two-games"] },
            { throwOnError: true },
          ),
      });
      mount(client, engine);
      await waitFor(() => expect(emptySlot(1)).toBeTruthy());
      fireEvent.click(
        screen.getByRole("button", { name: "Choose Home 1 to win at 2.1500" }),
      );
      await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
      await waitFor(() => expect(client.isFetching()).toBeGreaterThan(0));
      // Another price on fixture 1 aims at slot 1, which stays busy until it refreshes.
      expect(
        screen.getByRole("button", { name: "Choose Away 1 to win at 3.0000" }),
      ).toBeDisabled();
      if (outcome === "failure") {
        reject(new Error("Read unavailable"));
        await screen.findByText(
          "Could not verify slot 1. Your saved choice has not been replaced.",
        );
        expect(
          screen.getByRole("button", {
            name: "Choose Away 1 to win at 3.0000",
          }),
        ).toBeDisabled();
        expect(write).toHaveBeenCalledTimes(1);
      } else {
        release(entry(1, revision));
        await waitFor(() =>
          expect(
            screen.getByRole("button", {
              name: "Choose Away 1 to win at 3.0000",
            }),
          ).toBeEnabled(),
        );
      }
      client.clear();
      engine.dispose();
    },
  );
  it("creates a fresh operation for named price consent without mutating the refused body", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    api.mockImplementation(async (path: string) =>
      path === gamePath(target)
        ? game()
        : entry(Number(path.split("/").at(-1))),
    );
    const write = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError(409, "Confirm price", {
          code: "PRICE_MOVED",
          ...target,
          slot: 1,
          current_odds: "3.2500",
        }),
      )
      .mockResolvedValue(entry(1, 1));
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async () => entry(1),
      write,
      changed: async () => {},
    });
    mount(client, engine);
    await waitFor(() => expect(emptySlot(1)).toBeTruthy());
    fireEvent.click(
      screen.getByRole("button", { name: "Choose Home 1 to win at 2.1500" }),
    );
    const confirm = await screen.findByRole("button", {
      name: "Confirm odds 3.2500 for slot 1",
    });
    const original = write.mock.calls[0][1];
    fireEvent.click(confirm);
    await waitFor(() => expect(write).toHaveBeenCalledTimes(2));
    expect(write.mock.calls[1][1]).toMatchObject({
      odds: "3.2500",
      expected_revision: 0,
    });
    expect(write.mock.calls[1][1].operation_id).not.toBe(original.operation_id);
    expect(original.odds).toBe("2.1500");
    client.clear();
    engine.dispose();
  });
});

describe("authoritative Fantasy results", () => {
  it("refreshes a cached pending slot after passive settlement and correction without a user action", async () => {
    vi.useFakeTimers();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const engine = new GameIntents("alice", { member: () => "alice" });
    let result = "pending",
      points = 0;
    const pick = () => ({
      id: "pick-1",
      fixture_id: "fixture-1",
      player_id: "alice",
      market: "MATCH_ODDS",
      outcome: "HOME",
      runner_name: "Home 1",
      revision: 1,
      operation_id: "operation-1",
      frozen_odds: "2.1500",
      result,
      points,
    });
    api.mockImplementation(async (path: string) => {
      if (path === gamePath(target)) {
        const current = game();
        current.slots[0] = { ...entry(1, 1), pick: pick() };
        current.progress.filled_count = 1;
        current.result = {
          status: result === "pending" ? "pending" : "scored",
          points,
          provisional: result === "pending",
        };
        return current;
      }
      const n = Number(path.split("/").at(-1));
      return { ...entry(n, n === 1 ? 1 : 0), pick: n === 1 ? pick() : null };
    });
    try {
      await act(async () => {
        mount(client, engine);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10);
      });
      const first = screen.getByRole("article", { name: "Fantasy slot 1" });
      expect(first).toHaveTextContent("Waiting for results");
      // Batch 249: a pick still to play shows no points yet.
      expect(first).not.toHaveTextContent("0 points");
      result = "won";
      points = 22;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_020);
      });
      expect(first).toHaveTextContent("Won · 22 points");
      expect(screen.getByLabelText("Fantasy weekly result")).toHaveTextContent(
        "22 weekly points",
      );
      result = "lost";
      points = 0;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_020);
      });
      expect(first).toHaveTextContent("Lost · 0 points");
      expect(first).not.toHaveTextContent("Won");
    } finally {
      client.clear();
      engine.dispose();
      vi.useRealTimers();
    }
  });
  it("preserves an authoritative empty slot instead of resurrecting an older game-view pick", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const engine = new GameIntents("alice", { member: () => "alice" });
    const current = game();
    current.slots[0] = {
      ...entry(1, 1),
      pick: {
        id: "old",
        fixture_id: "fixture-1",
        player_id: "alice",
        market: "MATCH_ODDS",
        outcome: "HOME",
        runner_name: "Released old selection",
        revision: 1,
        operation_id: "old-operation",
        result: "pending",
        points: 0,
      },
    };
    api.mockImplementation(async (path: string) =>
      path === gamePath(target)
        ? current
        : entry(Number(path.split("/").at(-1)), 2),
    );
    mount(client, engine);
    await waitFor(() => expect(emptySlot(1)).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Remove slot 1" })).toBeNull();
    expect(
      screen.getByRole("article", { name: "Fantasy slot 1" }),
    ).toHaveTextContent("Empty slot");
    expect(screen.queryByText("Released old selection")).toBeNull();
    client.clear();
    engine.dispose();
  });
});

describe("known offline Fantasy choices", () => {
  it("retains a cached view after network refresh failure and queues a known slot without writing", async () => {
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const write = vi.fn();
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async () => {
        throw new NetworkError("offline", false);
      },
      write,
    });
    api.mockImplementation(async (path: string) =>
      path === gamePath(target)
        ? game()
        : entry(Number(path.split("/").at(-1))),
    );
    try {
      mount(client, engine);
      await waitFor(() => expect(emptySlot(1)).toBeTruthy());
      api.mockRejectedValue(new NetworkError("offline", false));
      await act(async () => {
        await client.refetchQueries({ queryKey: ["two-games"] });
      });
      expect(screen.getByTestId("fantasy-game")).toBeVisible();
      expect(
        await screen.findByText(/Showing the last received view/),
      ).toBeVisible();
      fireEvent.click(
        screen.getByRole("button", { name: "Choose Home 1 to win at 2.1500" }),
      );
      await waitFor(() => expect(engine.getSnapshot()[0].phase).toBe("queued"));
      expect(write).not.toHaveBeenCalled();
      expect(engine.getSnapshot()[0].target).toEqual(target);
    } finally {
      client.clear();
      engine.dispose();
      online.mockRestore();
    }
  });
});
