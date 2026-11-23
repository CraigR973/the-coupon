import { describe, it, expect } from "vitest";
import {
  buildGroupShareText,
  foldNote,
  groupFold,
  groupLegs,
  groupPhase,
  groupSelection,
  shortName,
  type GroupPhaseInput,
} from "../lib/groupCoupon";
import type { GroupFixture } from "../lib/twoGameTypes";

/**
 * Batch 233: the Saturday group in the old coupon's words. Its phase chip, every member's
 * leg in slate order, the unpriced fold and the text a member pastes into the group chat.
 */
function fixture(
  number: number,
  competition_id: string,
  claim: GroupFixture["claim"] = null,
): GroupFixture {
  return {
    fixture_id: `fixture-${number}`,
    home: `Home ${number}`,
    away: `Away ${number}`,
    competition_id,
    kickoff_at: "2026-11-28T15:00:00Z",
    status: "pending",
    eligible: true,
    allowed_markets: [
      { market: "MATCH_ODDS", outcomes: ["HOME", "DRAW", "AWAY"] },
      { market: "BOTH_TEAMS_TO_SCORE", outcomes: ["YES", "NO"] },
    ],
    claim,
  };
}

const claim = (
  player_id: string,
  display_name: string,
  market: string,
  outcome: string,
  runner_name: string,
  result = "pending",
) => ({ player_id, display_name, market, outcome, runner_name, result });

const open: GroupPhaseInput = {
  entryState: "open",
  notOpened: false,
  expired: false,
  final: false,
  hasPick: false,
  picked: 1,
  members: 4,
};

describe("the group status card's phase", () => {
  it("asks for a pick, then reports it submitted, then the coupon complete", () => {
    expect(groupPhase(open)).toBe("open");
    expect(groupPhase({ ...open, hasPick: true, picked: 2 })).toBe("submitted");
    expect(groupPhase({ ...open, hasPick: true, picked: 4 })).toBe("complete");
  });

  it("names a game the lock caught short, a settled one and the shut states", () => {
    expect(groupPhase({ ...open, expired: true })).toBe("locked_incomplete");
    expect(groupPhase({ ...open, entryState: "locked", picked: 4 })).toBe("complete");
    expect(groupPhase({ ...open, entryState: "locked", picked: 0, members: 0 })).toBe(
      "locked",
    );
    expect(groupPhase({ ...open, expired: true, final: true })).toBe("settled");
    expect(groupPhase({ ...open, notOpened: true })).toBe("not_open");
    expect(groupPhase({ ...open, entryState: "not_open" })).toBe("not_open");
    expect(groupPhase({ ...open, entryState: "suspended" })).toBe("suspended");
    expect(groupPhase({ ...open, entryState: "cancelled" })).toBe("cancelled");
  });
});

describe("the group's legs and fold", () => {
  it("lists each claimed fixture as its member's leg, in the fixture list's order", () => {
    const legs = groupLegs([
      fixture(4, "scotland-championship", claim("carol", "Carol", "MATCH_ODDS", "DRAW", "Draw")),
      fixture(2, "scotland-premiership"),
      fixture(
        3,
        "scotland-premiership",
        claim("bob", "Bob Smith", "MATCH_ODDS", "AWAY", "Away 3"),
      ),
      fixture(
        1,
        "scotland-premiership",
        claim("alice", "Alice", "BOTH_TEAMS_TO_SCORE", "YES", "Both teams score"),
      ),
    ]);
    expect(
      legs.map((leg) => [leg.display_name, leg.selection, leg.context, leg.competition]),
    ).toEqual([
      ["Alice", "Both teams score", "Home 1 v Away 1", "Scottish Premiership"],
      ["Bob Smith", "Away 3", "at Home 3", "Scottish Premiership"],
      ["Carol", "Draw", "Home 4 v Away 4", "Scottish Championship"],
    ]);
  });

  it("orders fixtures kicking off together by home club, as the API and the old coupon do", () => {
    const named = (number: number, home: string) => ({
      ...fixture(number, "synthetic", claim(`p${number}`, `P${number}`, "MATCH_ODDS", "HOME", home)),
      home,
    });
    expect(
      groupLegs([named(1, "Rangers"), named(2, "Aberdeen"), named(3, "Hibernian")]).map(
        (leg) => leg.home,
      ),
    ).toEqual(["Aberdeen", "Hibernian", "Rangers"]);
  });

  it("drops a voided leg out of the fold and says who is still to pick or never did", () => {
    const legs = groupLegs([
      fixture(1, "synthetic", claim("alice", "Alice", "MATCH_ODDS", "HOME", "Home 1", "won")),
      fixture(2, "synthetic", claim("bob", "Bob", "MATCH_ODDS", "HOME", "Home 2", "void")),
    ]);
    const fold = groupFold(legs, 2, 3);
    expect(fold).toEqual({ fold: 1, voided: 1, landed: 1, missing: 1 });
    expect(foldNote(fold, 3, false)).toBe("1 leg void, not in the fold · 1 of 3 still to pick");
    expect(foldNote(fold, 3, true)).toBe("1 leg void, not in the fold · 1 of 3 never picked");
    expect(foldNote(groupFold(legs.slice(0, 1), 1, 1), 1, false)).toBe("Everyone has picked");
  });

  it("labels each selection as the old card does, inside the name a screen reader hears", () => {
    const teams = { home: "Hibs", away: "Hearts" };
    expect(groupSelection(teams, "MATCH_ODDS", "HOME")).toEqual({
      label: "Hibs",
      name: "Hibs to win",
    });
    expect(groupSelection(teams, "MATCH_ODDS", "DRAW")).toEqual({ label: "Draw", name: "Draw" });
    expect(groupSelection(teams, "BOTH_TEAMS_TO_SCORE", "NO")).toEqual({
      label: "No — not both score",
      name: "No — not both score",
    });
    expect(shortName("Bob Smith")).toBe("Bob");
    expect(shortName("Former member")).toBe("Former member");
  });
});

describe("the group's text for the group chat", () => {
  const legs = groupLegs([
    fixture(1, "synthetic", claim("alice", "Alice", "MATCH_ODDS", "HOME", "Home 1")),
    fixture(2, "synthetic", claim("bob", "Bob Smith", "MATCH_ODDS", "DRAW", "Draw")),
  ]);

  it("prints the fold and every leg with no price while picks are open", () => {
    const text = buildGroupShareText(legs, {
      weekLabel: "28 Nov",
      picked: 2,
      members: 3,
      locked: false,
      final: false,
    });
    expect(text).toBe(
      [
        "The Coupon — Saturday Group · 28 Nov",
        "2-fold accumulator — 1 of 3 still to pick",
        "",
        "1. Alice — Home 1 (v Away 1)",
        "2. Bob Smith — Draw (Home 2 v Away 2)",
      ].join("\n"),
    );
    expect(text).not.toMatch(/@|odds|points|pts/i);
  });

  it("says who never picked once the lock has passed", () => {
    expect(
      buildGroupShareText(legs, {
        weekLabel: "28 Nov",
        picked: 2,
        members: 3,
        locked: true,
        final: false,
      }).split("\n")[1],
    ).toBe("2-fold accumulator — incomplete, 1 of 3 never picked");
  });

  it("becomes the result once the game is final, each leg saying how it ended", () => {
    const settled = groupLegs([
      fixture(1, "synthetic", claim("alice", "Alice", "MATCH_ODDS", "HOME", "Home 1", "won")),
      fixture(2, "synthetic", claim("bob", "Bob Smith", "MATCH_ODDS", "DRAW", "Draw", "void")),
    ]);
    expect(
      buildGroupShareText(settled, {
        weekLabel: "21 Nov",
        picked: 2,
        members: 2,
        locked: true,
        final: true,
      }),
    ).toBe(
      [
        "The Coupon: Result — Saturday Group · 21 Nov — 1 of 2 picks landed",
        "1-fold accumulator — 1 leg void",
        "",
        "1. Alice — Home 1 (v Away 1) — Won",
        "2. Bob Smith — Draw (Home 2 v Away 2) — Void",
      ].join("\n"),
    );
  });
});
