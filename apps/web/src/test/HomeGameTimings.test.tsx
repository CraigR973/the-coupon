import { act, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, vi, expect } from "vitest";
import { useHomeGames } from "../hooks/useHomeGames";
const { api } = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  apiFetch: api,
}));
function Home() {
  const { data } = useHomeGames("alice");
  return (
    <p>
      {data?.leagues
        ?.flatMap((league) => league.games.map((game) => game.entry_state))
        .join(",") ?? "Loading"}
    </p>
  );
}
async function start() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <Home />
      </QueryClientProvider>,
    );
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10);
  });
  return client;
}
describe("simultaneous Home freshness", () => {
  it("updates current results and next entry at the exact shared deadline while the shell remains mounted", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-21T11:59:59Z"));
    const noon = Date.parse("2026-11-21T12:00:00Z");
    api.mockImplementation(async () => ({
      leagues: [
        {
          two_games_enabled: true,
          games: [
            {
              opens_at: "2026-11-14T12:00:00Z",
              locks_at: "2026-11-21T12:00:00Z",
              entry_state: Date.now() < noon ? "open" : "locked",
            },
            {
              opens_at: "2026-11-21T12:00:00Z",
              locks_at: "2026-11-28T12:00:00Z",
              entry_state: Date.now() < noon ? "not_open" : "open",
            },
          ],
        },
      ],
    }));
    const client = await start();
    try {
      expect(screen.getByText("open,not_open")).toBeVisible();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1010);
      });
      expect(screen.getByText("locked,open")).toBeVisible();
    } finally {
      client.clear();
      vi.useRealTimers();
    }
  });
  it("polls enabled results without remounting", async () => {
    vi.useFakeTimers();
    let state = "pending";
    api.mockImplementation(async () => ({
      leagues: [
        {
          two_games_enabled: true,
          games: [
            {
              opens_at: "1970-01-01T00:00:00Z",
              locks_at: "1970-01-01T00:00:00Z",
              entry_state: state,
            },
          ],
        },
      ],
    }));
    const client = await start();
    try {
      expect(screen.getByText("pending")).toBeVisible();
      state = "settled";
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_020);
      });
      expect(screen.getByText("settled")).toBeVisible();
    } finally {
      client.clear();
      vi.useRealTimers();
    }
  });
  it("does not schedule new-format polling for an inactive installation", async () => {
    vi.useFakeTimers();
    api.mockResolvedValue({ leagues: [] });
    const client = await start();
    try {
      const calls = api.mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(90_000);
      });
      expect(api).toHaveBeenCalledTimes(calls);
    } finally {
      client.clear();
      vi.useRealTimers();
    }
  });
});
