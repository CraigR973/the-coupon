import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GroupGamePage } from "../pages/GroupGamePage";
import { GameIntentContext } from "../hooks/useGameIntents";
import { GameIntents } from "../lib/gameIntents";
import { gamePath, type GameEntry, type GroupGame } from "../lib/twoGameTypes";
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

describe("Group authoritative revision readiness", () => {
  it.each(["success", "failure"])(
    "keeps edits disabled until an accepted save has refreshed its authoritative revision (%s)",
    async (outcome) => {
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      let revision = 0;
      let release!: (entry: GameEntry) => void;
      let reject!: (error: Error) => void;
      const paused = new Promise<GameEntry>((resolve, fail) => {
        release = resolve;
        reject = fail;
      });
      const current = (): GameEntry => ({
        ...target,
        game_id: "game-a",
        revision,
        operation_id: null,
        pick: null,
      });
      const game: GroupGame = {
        ...target,
        game_id: "game-a",
        week_label: "2026-11-21",
        week_number: "1",
        destination: "/",
        opens_at: "opens",
        locks_at: "locks",
        entry_state: "open",
        coverage_state: "complete",
        my_entries: [],
        progress: { picked_count: 0, member_count: 3, all_picked: false },
        result: { status: "pending", final: false },
        fee: {
          league_id: "league-a",
          week_id: "week-a",
          week_label: "2026-11-21",
          billing_starts_at: "2026-11-16T00:00:00Z",
          billing_ends_at: "2026-11-23T00:00:00Z",
          obligation_pence: 100,
          amount_owed_pence: 0,
          paid_through: true,
          pooled_credit_pence: 900,
          payment_url: null,
          destination: "/",
          obligations: [],
        },
        fixtures: [1, 2].map((number) => ({
          fixture_id: `fixture-${number}`,
          home: `Home ${number}`,
          away: `Away ${number}`,
          competition_id: "synthetic",
          kickoff_at: "2026-11-21T15:00:00Z",
          status: "pending",
          eligible: true,
          claim: null,
          allowed_markets: [{ market: "MATCH_ODDS", outcomes: ["HOME"] }],
        })),
      };
      api.mockImplementation(async (path: string) =>
        path === gamePath(target) ? game : revision === 1 ? paused : current(),
      );
      const write = vi.fn(async () => {
        revision++;
        return current();
      });
      const engine = new GameIntents("alice", {
        member: () => "alice",
        read: async () => current(),
        write,
        changed: () =>
          client.invalidateQueries(
            { queryKey: ["two-games"] },
            { throwOnError: true },
          ),
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
      const first = await screen.findByRole("button", {
        name: "Choose Home 1 to win",
      });
      await waitFor(() => expect(first).toBeEnabled());
      fireEvent.click(first);
      await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
      await waitFor(() =>
        expect(client.isFetching({ queryKey: ["two-games"] })).toBeGreaterThan(
          0,
        ),
      );
      const second = screen.getByRole("button", {
        name: "Choose Home 2 to win",
      });
      expect(second).toBeDisabled();
      expect(screen.getByTestId("intent-0")).not.toHaveTextContent(
        "Saved. Refreshing",
      );
      if (outcome === "failure") {
        reject(new Error("Read unavailable"));
        await screen.findByText("Could not verify your saved contribution");
        expect(second).toBeDisabled();
        expect(screen.getByTestId("intent-0")).toHaveTextContent(
          "current choice could not be refreshed",
        );
        expect(write).toHaveBeenCalledTimes(1);
        client.clear();
        return;
      }
      release(current());
      await waitFor(() => expect(second).toBeEnabled());
      fireEvent.click(second);
      await waitFor(() => expect(write).toHaveBeenCalledTimes(2));
      expect(engine.getSnapshot()[0].body.expected_revision).toBe(1);
      client.clear();
    },
  );
});
