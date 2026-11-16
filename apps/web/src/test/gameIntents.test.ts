import { describe, it, expect, vi } from "vitest";
import { GameIntents, type GameIntent } from "../lib/gameIntents";
import { ApiError, NetworkError } from "../lib/api";
import type { GameEntry, GameTarget } from "../lib/twoGameTypes";
const target: GameTarget = {
  league_id: "league-a",
  week_id: "week-a",
  game_kind: "fantasy",
};
const choice = {
  fixture_id: "fixture-a",
  market: "MATCH_ODDS",
  outcome: "HOME",
  odds: "2.15",
};
const entry = (
  revision = 0,
  operation_id: string | null = null,
): GameEntry => ({
  ...target,
  game_id: "game-a",
  slot: 1,
  revision,
  operation_id,
  pick: null,
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
const settled = async (engine: GameIntents, phase: string, count = 1) => {
  await vi.waitFor(() => {
    expect(
      engine.getSnapshot().filter((value) => value.phase === phase),
    ).toHaveLength(count);
  });
};

describe("addressed deferred operations", () => {
  it("keeps two offline slots independent and reconnects each exact operation once", async () => {
    let online = false;
    const write = vi.fn(async (_path: string, body: GameIntent["body"]) =>
      entry(1, body.operation_id),
    );
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async () => {
        if (!online) throw new NetworkError("offline", false);
        return entry();
      },
      write,
    });
    engine.choose(target, 1, choice, 0);
    engine.choose(target, 2, { ...choice, fixture_id: "fixture-b" }, 0);
    await settled(engine, "queued", 2);
    const operations = engine
      .getSnapshot()
      .map((value) => value.body.operation_id);
    expect(new Set(operations).size).toBe(2);
    expect(write).not.toHaveBeenCalled();
    online = true;
    engine.reconnect();
    await settled(engine, "confirmed", 2);
    engine.reconnect();
    expect(write.mock.calls.map((call) => call[0]).sort()).toEqual([
      "/api/v1/leagues/league-a/weeks/week-a/games/fantasy/slots/1",
      "/api/v1/leagues/league-a/weeks/week-a/games/fantasy/slots/2",
    ]);
    expect(write.mock.calls.map((call) => call[1].operation_id)).toEqual(
      operations,
    );
  });
  it("confirms a committed unanswered operation by exact readback without another write", async () => {
    let current = entry();
    const write = vi.fn(async (_path: string, body: GameIntent["body"]) => {
      current = entry(1, body.operation_id);
      throw new NetworkError("lost response", true);
    });
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async () => current,
      write,
    });
    engine.choose(target, 1, choice, 0);
    await settled(engine, "uncertain");
    engine.reconnect();
    await settled(engine, "confirmed");
    expect(write).toHaveBeenCalledTimes(1);
  });
  it("retries an unanswered non-commit with the same immutable operation after readback", async () => {
    const write = vi
      .fn()
      .mockRejectedValueOnce(new NetworkError("dropped", true))
      .mockResolvedValue(entry(1));
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async () => entry(),
      write,
    });
    engine.choose(target, 1, choice, 0);
    await settled(engine, "uncertain");
    engine.reconnect();
    await settled(engine, "confirmed");
    expect(write.mock.calls[0][1]).toEqual(write.mock.calls[1][1]);
  });
  it("does not overwrite a newer device revision after an uncertain request", async () => {
    let current = entry();
    const write = vi.fn(async () => {
      throw new NetworkError("lost", true);
    });
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async () => current,
      write,
    });
    engine.choose(target, 1, choice, 0);
    await settled(engine, "uncertain");
    current = entry(2, "other-device");
    engine.reconnect();
    await settled(engine, "conflict");
    expect(write).toHaveBeenCalledTimes(1);
    expect(engine.getSnapshot()[0].body.fixture_id).toBe("fixture-a");
  });
  it("a late old response cannot confirm a newer deliberate replacement", async () => {
    const gate = deferred<GameEntry>();
    let current = entry();
    const write = vi.fn(async () => gate.promise);
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async () => current,
      write,
    });
    engine.choose(target, 1, choice, 0);
    await settled(engine, "sending");
    const old = engine.getSnapshot()[0];
    engine.choose(target, 1, { ...choice, fixture_id: "fixture-b" }, 0);
    current = entry(1, old.body.operation_id);
    gate.resolve(current);
    await settled(engine, "conflict");
    expect(engine.getSnapshot()[0].body.fixture_id).toBe("fixture-b");
    expect(write).toHaveBeenCalledTimes(1);
  });
  it("isolates another week and slot while a readback is paused", async () => {
    const gate = deferred<GameEntry>();
    const write = vi.fn(async () => entry(1));
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async (path) =>
        path.includes("/week-a/") ? gate.promise : entry(),
      write,
    });
    engine.choose(target, 1, choice, 0);
    engine.choose({ ...target, week_id: "week-b" }, 2, choice, 0);
    await settled(engine, "confirmed");
    expect(
      engine.getSnapshot().find((value) => value.target.week_id === "week-a")
        ?.phase,
    ).toBe("checking");
    gate.resolve(entry(3, "other"));
    await settled(engine, "conflict");
    expect(write.mock.calls).toHaveLength(1);
  });
  it("never sends or accepts a deferred operation after member change/disposal", async () => {
    const gate = deferred<GameEntry>();
    let member = "alice";
    const write = vi.fn(async () => entry(1));
    const engine = new GameIntents("alice", {
      member: () => member,
      read: async () => gate.promise,
      write,
    });
    engine.choose(target, 1, choice, 0);
    await settled(engine, "checking");
    member = "bob";
    engine.dispose();
    gate.resolve(entry());
    await Promise.resolve();
    await Promise.resolve();
    engine.reconnect();
    expect(write).not.toHaveBeenCalled();
    expect(engine.getSnapshot()).toEqual([]);
  });
  it.each([402, 409, 429])(
    "keeps a refused slot choice without changing another target (%i)",
    async (status) => {
      const write = vi.fn(async (path: string) => {
        if (path.endsWith("/1"))
          throw new ApiError(status, "Refused", { code: "PAYMENT_REQUIRED" });
        return entry(1);
      });
      const engine = new GameIntents("alice", {
        member: () => "alice",
        read: async () => entry(),
        write,
      });
      engine.choose(target, 1, choice, 0);
      engine.choose(target, 2, { ...choice, fixture_id: "fixture-b" }, 0);
      await settled(engine, "refused");
      await settled(engine, "confirmed");
      expect(
        engine.getSnapshot().find((value) => value.slot === 1)?.refusal?.status,
      ).toBe(status);
    },
  );
  it("invalidates authoritative readers after an accepted historical receipt", async () => {
    const changed = vi.fn();
    const engine = new GameIntents("alice", {
      member: () => "alice",
      read: async () => entry(),
      write: async () => ({ ...entry(1), pick: null }),
      changed,
    });
    engine.choose(target, 1, choice, 0);
    await settled(engine, "confirmed");
    expect(changed).toHaveBeenCalledTimes(1);
  });
});
