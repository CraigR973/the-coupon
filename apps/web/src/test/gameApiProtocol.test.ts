import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { apiFetch, ApiError, NetworkError } from "../lib/api";
import { GameIntents } from "../lib/gameIntents";
import { getStoredPlayer, getAccessToken, storeTokens } from "../lib/tokens";
const player = (id: string) => ({
  id,
  displayName: id,
  role: "player" as const,
  timezone: "Europe/London",
});
const token = (seconds = 3600) =>
  `x.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + seconds }))}.x`;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
beforeEach(() => {
  localStorage.clear();
  storeTokens(token(), "refresh-a", player("alice"));
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
describe("game API authentication and refusal protocol", () => {
  it.each([402, 409])(
    "preserves structured %i after a successful401 refresh",
    async (status) => {
      const fetcher = vi
        .fn()
        .mockResolvedValueOnce(json({ detail: "Expired" }, 401))
        .mockResolvedValueOnce(
          json({ access_token: token(), refresh_token: "refresh-new" }),
        )
        .mockResolvedValueOnce(
          json(
            {
              detail: {
                code: status === 402 ? "PAYMENT_REQUIRED" : "ENTRY_CHANGED",
                message: "Keep the saved choice",
                current: { revision: 3 },
              },
            },
            status,
          ),
        );
      vi.stubGlobal("fetch", fetcher);
      const error = await apiFetch("/game", {
        method: "PUT",
        expectedMemberId: "alice",
      }).catch((value) => value);
      expect(error).toBeInstanceOf(ApiError);
      if (!(error instanceof ApiError)) throw error;
      expect(error.status).toBe(status);
      expect(error.data?.current).toEqual({ revision: 3 });
      expect(getStoredPlayer()?.id).toBe("alice");
      expect(fetcher).toHaveBeenCalledTimes(3);
    },
  );
  it("handles a204 retry without parsing JSON or clearing the session", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(json({}, 401))
      .mockResolvedValueOnce(
        json({ access_token: token(), refresh_token: "next" }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);
    expect(
      await apiFetch("/game", { expectedMemberId: "alice" }),
    ).toBeUndefined();
    expect(getStoredPlayer()?.id).toBe("alice");
  });
  it("keeps the session and labels a lost retry as an uncertain network answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json({}, 401))
        .mockResolvedValueOnce(
          json({ access_token: token(), refresh_token: "next" }),
        )
        .mockRejectedValueOnce(new TypeError("lost")),
    );
    const error = await apiFetch("/game", {
      method: "PUT",
      expectedMemberId: "alice",
    }).catch((value) => value);
    expect(error).toBeInstanceOf(NetworkError);
    if (!(error instanceof NetworkError)) throw error;
    expect(error.mayHaveLanded).toBe(true);
    expect(getStoredPlayer()?.id).toBe("alice");
  });
  it.each([true, false])(
    "fences member switch while refresh is paused (proactive=%s)",
    async (proactive) => {
      if (proactive) storeTokens(token(-1), "refresh-a", player("alice"));
      let release!: (response: Response) => void;
      const paused = new Promise<Response>((resolve) => {
        release = resolve;
      });
      const fetcher = vi.fn(async (url: string) =>
        url.endsWith("/refresh") ? paused : json({}, 401),
      );
      vi.stubGlobal("fetch", fetcher);
      const pending = apiFetch("/game", {
        method: "PUT",
        expectedMemberId: "alice",
      }).catch((value) => value);
      await vi.waitFor(() =>
        expect(
          fetcher.mock.calls.some((call) => call[0].endsWith("/refresh")),
        ).toBe(true),
      );
      const bobToken = token(7200);
      storeTokens(bobToken, "refresh-b", player("bob"));
      release(json({ access_token: token(), refresh_token: "stale-alice" }));
      const error = await pending;
      expect(error).toBeInstanceOf(ApiError);
      if (!(error instanceof ApiError)) throw error;
      expect(error.code).toBe("SESSION_CHANGED");
      expect(getStoredPlayer()?.id).toBe("bob");
      expect(getAccessToken()).toBe(bobToken);
      expect(
        fetcher.mock.calls.filter((call) => call[0].endsWith("/game")),
      ).toHaveLength(proactive ? 0 : 1);
    },
  );
  it("keeps legacy string refusals and transient refresh failures from becoming logout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(json({ detail: "Old refusal" }, 409)),
    );
    const error = await apiFetch("/legacy").catch((value) => value);
    expect(error).toBeInstanceOf(ApiError);
    if (!(error instanceof ApiError)) throw error;
    expect(error.detail).toBe("Old refusal");
    expect(error.data).toBeNull();
    storeTokens(token(-1), "refresh-a", player("alice"));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValueOnce(new TypeError("offline")),
    );
    await expect(
      apiFetch("/game", { expectedMemberId: "alice" }),
    ).rejects.toBeInstanceOf(NetworkError);
    expect(getStoredPlayer()?.id).toBe("alice");
  });
});

it("a delayed retry401 cannot clear a newer member session", async () => {
  let release!: (response: Response) => void;
  const retry = new Promise<Response>((resolve) => {
    release = resolve;
  });
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(json({}, 401))
    .mockResolvedValueOnce(
      json({ access_token: token(), refresh_token: "rotated-alice" }),
    )
    .mockImplementationOnce(() => retry);
  vi.stubGlobal("fetch", fetcher);
  const pending = apiFetch("/game", {
    method: "PUT",
    expectedMemberId: "alice",
  }).catch((error) => error);
  await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
  const bobToken = token(7200);
  storeTokens(bobToken, "refresh-bob", player("bob"));
  release(json({}, 401));
  const error = await pending;
  expect(error).toBeInstanceOf(ApiError);
  if (!(error instanceof ApiError)) throw error;
  expect(error.code).toBe("SESSION_CHANGED");
  expect(getStoredPlayer()?.id).toBe("bob");
  expect(getAccessToken()).toBe(bobToken);
});

it("does not clear or redirect a new session established during old cache cleanup", async () => {
  let release!: (value: boolean) => void;
  const cleanup = new Promise<boolean>((resolve) => {
    release = resolve;
  });
  const remove = vi.fn(() => cleanup);
  vi.stubGlobal("caches", { delete: remove });
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(json({}, 401))
      .mockResolvedValueOnce(json({}, 401)),
  );
  const location = window.location.href;
  const pending = apiFetch("/game", { expectedMemberId: "alice" }).catch(
    (error) => error,
  );
  await vi.waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
  const bobToken = token(7200);
  storeTokens(bobToken, "refresh-bob", player("bob"));
  release(true);
  const error = await pending;
  expect(error).toBeInstanceOf(ApiError);
  if (!(error instanceof ApiError)) throw error;
  expect(error.code).toBe("SESSION_CHANGED");
  expect(getStoredPlayer()?.id).toBe("bob");
  expect(getAccessToken()).toBe(bobToken);
  expect(window.location.href).toBe(location);
  expect(remove).toHaveBeenCalledTimes(1);
});

it.each([
  "/leagues/league-b/weeks/week-a/group?from=receipt#payment",
  "/leagues/league-b/weeks/week-z/fantasy#payment",
  "/leagues/former/games",
])(
  "retains exact addressed destination after a genuinely rejected refresh on %s",
  async (path) => {
    const location = {
      pathname: path.split(/[?#]/)[0],
      search: path.includes("?") ? "?" + path.split("?")[1].split("#")[0] : "",
      hash: path.includes("#") ? "#" + path.split("#")[1] : "",
      href: path,
    };
    vi.stubGlobal("location", location);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json({}, 401))
        .mockResolvedValueOnce(json({}, 401)),
    );
    await expect(
      apiFetch("/game", { expectedMemberId: "alice" }),
    ).rejects.toThrow("Session expired");
    expect(location.href).toBe("/login?next=" + encodeURIComponent(path));
    expect(getStoredPlayer()).toBeNull();
  },
);

it.each([new TypeError("body stream lost"), new SyntaxError("truncated JSON")])(
  "reconciles a committed200 with an unreadable receipt (%s) without a second PUT",
  async (failure) => {
    const target = {
      league_id: "league-a",
      week_id: "week-a",
      game_kind: "group" as const,
    };
    let revision = 0,
      operation_id: string | null = null;
    const current = () => ({
      ...target,
      game_id: "game-a",
      revision,
      operation_id,
      pick: null,
    });
    const fetcher = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        revision++;
        operation_id = JSON.parse(init.body as string).operation_id;
        return {
          ok: true,
          status: 200,
          json: async () => {
            throw failure;
          },
        };
      }
      return json(current());
    });
    vi.stubGlobal("fetch", fetcher);
    const engine = new GameIntents("alice");
    engine.choose(
      target,
      0,
      { fixture_id: "fixture-a", market: "MATCH_ODDS", outcome: "HOME" },
      0,
    );
    await vi.waitFor(() =>
      expect(engine.getSnapshot()[0].phase).toBe("uncertain"),
    );
    const operation = engine.getSnapshot()[0].body.operation_id;
    engine.reconnect();
    await vi.waitFor(() =>
      expect(engine.getSnapshot()[0].phase).toBe("confirmed"),
    );
    expect(
      fetcher.mock.calls.filter((call) => call[1]?.method === "PUT"),
    ).toHaveLength(1);
    expect(operation_id).toBe(operation);
    expect(getStoredPlayer()?.id).toBe("alice");
  },
);
