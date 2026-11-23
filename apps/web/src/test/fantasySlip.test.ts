import { describe, it, expect } from "vitest";
import {
  destinationFor,
  fantasyPoints,
  fixturesHeldElsewhere,
  heldSelection,
  slipSummary,
  type SlotView,
} from "../lib/fantasySlip";
import type { GameIntent, IntentPhase } from "../lib/gameIntents";
import type { GamePick } from "../lib/twoGameTypes";

const target = { league_id: "l", week_id: "w", game_kind: "fantasy" as const };
const pick = (fixture: string, extra: Partial<GamePick> = {}): GamePick => ({
  id: `pick-${fixture}`,
  fixture_id: fixture,
  player_id: "alice",
  market: "MATCH_ODDS",
  outcome: "HOME",
  runner_name: `${fixture} home`,
  revision: 1,
  operation_id: `op-${fixture}`,
  result: "pending",
  frozen_odds: "2.0000",
  points: 0,
  ...extra,
});
const intent = (slot: number, fixture: string, phase: IntentPhase): GameIntent => ({
  target,
  slot,
  body: {
    fixture_id: fixture,
    market: "MATCH_ODDS",
    outcome: "AWAY",
    odds: "3.0000",
    expected_revision: 0,
    operation_id: `op-${slot}`,
  },
  phase,
  message: "",
});
const empty = (): SlotView[] =>
  [1, 2, 3, 4, 5, 6].map((slot) => ({
    slot,
    pick: null,
    movedPrice: null,
    ready: true,
  }));

describe("where a tapped price lands", () => {
  it("takes the first free slot when the fixture is not in the slip", () => {
    const views = empty();
    views[0].pick = pick("a");
    expect(destinationFor("b", views)).toEqual({ kind: "slot", slot: 2 });
  });

  it("goes back to the slot already holding the fixture, so a second price swaps that pick", () => {
    const views = empty();
    views[0].pick = pick("a");
    views[3].pick = pick("b");
    expect(destinationFor("b", views)).toEqual({ kind: "slot", slot: 4 });
  });

  it("counts a choice still on its way as holding its slot and its fixture", () => {
    const views = empty();
    views[0].intent = intent(1, "a", "sending");
    expect(destinationFor("a", views)).toEqual({ kind: "slot", slot: 1 });
    expect(destinationFor("b", views)).toEqual({ kind: "slot", slot: 2 });
  });

  it("keeps a slot whose moved price awaits an answer, but frees one refused for any other reason", () => {
    const views = empty();
    views[0].intent = intent(1, "a", "refused");
    views[0].movedPrice = "3.2500";
    views[1].intent = intent(2, "b", "refused");
    expect(destinationFor("c", views)).toEqual({ kind: "slot", slot: 2 });
    expect(destinationFor("a", views)).toEqual({ kind: "slot", slot: 1 });
  });

  it("asks rather than replacing anything once all six slots are spoken for", () => {
    const views = empty().map((view, index) => ({
      ...view,
      pick: pick(`f${index}`),
    }));
    expect(destinationFor("new", views)).toEqual({ kind: "full" });
    expect(destinationFor("f2", views)).toEqual({ kind: "slot", slot: 3 });
  });

  it("shows the choice on its way, not the saved pick it is replacing", () => {
    const views = empty();
    views[0].pick = pick("a");
    views[0].intent = intent(1, "a", "checking");
    expect(heldSelection(views[0])).toEqual({
      fixture_id: "a",
      market: "MATCH_ODDS",
      outcome: "AWAY",
    });
    views[0].intent = intent(1, "a", "confirmed");
    expect(heldSelection(views[0])?.outcome).toBe("HOME");
  });
});

describe("fixtures another slot holds", () => {
  it("are the other slots' saved picks and choices on their way, never the slot's own", () => {
    const views = empty();
    views[0].pick = pick("a");
    views[1].intent = intent(2, "b", "queued");
    views[2].intent = intent(3, "c", "refused");
    views[3].pick = pick("d");
    const held = fixturesHeldElsewhere(4, views);
    expect([...held].sort()).toEqual(["a", "b"]);
  });
});

describe("points on the slip", () => {
  it("rounds the exact decimal half up, as the API scores a win", () => {
    expect(fantasyPoints("2.1500")).toBe(22);
    expect(fantasyPoints("1.65")).toBe(17);
    expect(fantasyPoints("3.75")).toBe(38);
    expect(fantasyPoints("1.80")).toBe(18);
    expect(fantasyPoints("1.0449")).toBe(10);
    expect(fantasyPoints("10")).toBe(100);
  });

  it("refuses anything that is not a plain positive decimal", () => {
    expect(fantasyPoints("")).toBeNull();
    expect(fantasyPoints("abc")).toBeNull();
    expect(fantasyPoints("0")).toBeNull();
    expect(fantasyPoints("-2.00")).toBeNull();
    expect(fantasyPoints("2.12345")).toBeNull();
  });

  it("counts saved picks and adds won points to every pending win for the most still possible", () => {
    const views = empty();
    views[0].pick = pick("a", { frozen_odds: "2.1500" });
    views[1].pick = pick("b", { result: "won", points: 30, frozen_odds: "3.0000" });
    views[2].pick = pick("c", { result: "lost", frozen_odds: "5.0000" });
    views[3].pick = pick("d", { result: "void", frozen_odds: "1.5000" });
    views[4].intent = intent(5, "e", "sending");
    expect(slipSummary(views)).toEqual({ filled: 4, upTo: 52 });
  });
});
