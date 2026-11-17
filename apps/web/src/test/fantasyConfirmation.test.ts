import { describe, it, expect } from "vitest";
import { movedPrice, fantasyResultLabel } from "../lib/fantasy";
import { ApiError } from "../lib/api";
import type { GameIntent } from "../lib/gameIntents";
const target = {
  league_id: "league-a",
  week_id: "week-a",
  game_kind: "fantasy" as const,
};
const intent = (detail: Record<string, unknown> = {}): GameIntent => ({
  target,
  slot: 1,
  body: {
    fixture_id: "a",
    market: "MATCH_ODDS",
    outcome: "HOME",
    odds: "2.1500",
    expected_revision: 1,
    operation_id: "op",
  },
  phase: "refused",
  message: "Confirm",
  refusal: new ApiError(409, "Confirm", {
    code: "PRICE_MOVED",
    ...target,
    slot: 1,
    current_odds: "3.2500",
    ...detail,
  }),
});
describe("named Fantasy price confirmation", () => {
  it("preserves all four decimal places from the addressed server refusal", () =>
    expect(movedPrice(intent(), target, 1)).toBe("3.2500"));
  it.each([
    { league_id: "other" },
    { week_id: "other" },
    { game_kind: "group" },
    { slot: 2 },
    { current_odds: 3.25 },
    { current_odds: "3.25001" },
    { current_odds: "0.0000" },
    { code: "ENTRY_CHANGED" },
  ])("rejects a mismatched or invalid confirmation %j", (detail) =>
    expect(movedPrice(intent(detail), target, 1)).toBeNull(),
  );
  it("does not retain a confirmation after a different local choice", () =>
    expect(movedPrice({ ...intent(), phase: "queued" }, target, 1)).toBeNull());
  it("keeps no entry, all void and scored zero conceptually distinct", () =>
    expect(["no_entry", "all_void", "scored"].map(fantasyResultLabel)).toEqual([
      "No entry",
      "All void",
      "Scored",
    ]));
});
