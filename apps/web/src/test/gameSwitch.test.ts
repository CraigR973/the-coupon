import { describe, it, expect } from "vitest";
import {
  gamesTabDestination,
  leagueForGames,
  switchCard,
  switchTarget,
  weekStep,
  weekStops,
} from "../lib/gameSwitch";
import type { GameCard, LeagueGames, LegacyGameCard } from "../lib/twoGameTypes";

function card(
  kind: "group" | "fantasy",
  week: string,
  purpose: string,
  extra: Partial<GameCard> = {},
): GameCard {
  return {
    league_id: "league-a",
    week_id: `${kind}-${week}`,
    game_kind: kind,
    game_id: `game-${kind}-${week}`,
    week_label: week,
    week_number: "1",
    destination: `/leagues/league-a/weeks/${week}/${kind}`,
    opens_at: `${week}T12:00:00Z`,
    locks_at:
      kind === "group" ? `${week}T14:30:00Z` : `${week}T12:00:00Z`,
    entry_state: purpose === "entry" ? "open" : purpose === "results" ? "locked" : "not_open",
    purpose,
    archived: false,
    fee: {} as GameCard["fee"],
    coverage_state: "complete",
    result_version: 1,
    progress: {},
    result: { final: false },
    ...extra,
  };
}
function league(games: GameCard[]): LeagueGames {
  return {
    league_id: "league-a",
    slug: "two-one-hibs",
    name: "2-1 Hibs",
    two_games_enabled: true,
    suspended: false,
    server_now: "2026-11-28T12:30:00Z",
    games,
    legacy_rounds: [],
    next_cursor: null,
    next_game_state: "known",
    next_game_opens_at: null,
    season_stats: null,
    weekly_form: [],
  };
}

describe("the switch's week for each game", () => {
  it("opens the open entry first, so Saturday afternoon's Fantasy is next week's", () => {
    const games = league([
      card("fantasy", "2026-11-28", "results"),
      card("fantasy", "2026-12-05", "entry"),
      card("group", "2026-11-28", "entry"),
    ]);
    expect(switchCard(games, "fantasy")?.week_label).toBe("2026-12-05");
    expect(switchCard(games, "group")?.week_label).toBe("2026-11-28");
  });

  it("falls back to the newest results, then the soonest opening, and never an archived week", () => {
    const games = league([
      card("fantasy", "2026-11-21", "results"),
      card("fantasy", "2026-11-28", "results"),
      card("fantasy", "2026-12-12", "upcoming"),
      card("group", "2026-12-05", "upcoming"),
      card("group", "2026-11-28", "entry", { archived: true }),
    ]);
    expect(switchCard(games, "fantasy")?.week_label).toBe("2026-11-28");
    expect(switchCard(games, "group")?.week_label).toBe("2026-12-05");
  });

});

describe("the Games tab", () => {
  it("opens the untouched open game that locks soonest", () => {
    const games = league([
      card("fantasy", "2026-12-05", "entry", { progress: { slots_filled: 0 } }),
      card("group", "2026-11-28", "entry", {
        my_entry: {
          league_id: "league-a",
          week_id: "group-2026-11-28",
          game_id: "g",
          game_kind: "group",
          revision: 0,
          operation_id: null,
          pick: null,
        },
      }),
    ]);
    expect(gamesTabDestination(games)).toBe(
      "/leagues/league-a/weeks/2026-11-28/group",
    );
  });

  it("keeps this week's played game over next week's untouched Fantasy (Batch 244)", () => {
    const games = league([
      card("group", "2026-11-28", "entry", {
        my_entry: {
          league_id: "league-a",
          week_id: "group-2026-11-28",
          game_id: "g",
          game_kind: "group",
          revision: 1,
          operation_id: "op",
          pick: {
            id: "p",
            fixture_id: "f",
            player_id: "alice",
            market: "MATCH_ODDS",
            outcome: "HOME",
            runner_name: "Hibs",
            revision: 1,
            operation_id: "op",
            result: "pending",
          },
        },
      }),
      card("fantasy", "2026-12-05", "entry", { progress: { slots_filled: 0 } }),
    ]);
    // Batch 244 (owner-approved, 25 Nov 2026): a link without a week follows Home's rule,
    // this week until its results are final; next week's Fantasy waits behind the arrow.
    expect(gamesTabDestination(games)).toBe(
      "/leagues/league-a/weeks/2026-11-28/group",
    );
  });

  it("falls back to an open game by lock, then the current fantasy week, then the archive", () => {
    expect(
      gamesTabDestination(
        league([
          card("fantasy", "2026-12-05", "entry", { progress: { slots_filled: 3 } }),
        ]),
      ),
    ).toBe("/leagues/league-a/weeks/2026-12-05/fantasy");
    expect(
      gamesTabDestination(league([card("fantasy", "2026-11-28", "results")])),
    ).toBe("/leagues/league-a/weeks/2026-11-28/fantasy");
    expect(gamesTabDestination(league([]))).toBe("/leagues/league-a/games");
  });

  it("belongs to the league in the address, else the league in use", () => {
    const leagues = [
      league([]),
      { ...league([]), league_id: "league-b", slug: "other" },
    ];
    expect(
      leagueForGames(leagues, "/leagues/league-b/games", "two-one-hibs")?.league_id,
    ).toBe("league-b");
    expect(leagueForGames(leagues, undefined, "two-one-hibs")?.league_id).toBe(
      "league-a",
    );
    expect(leagueForGames(leagues, "/leagues/gone/games", "two-one-hibs")).toBeUndefined();
  });
});

/** Batch 244: both games of one football week share its id, as the API sends them. */
function weekCard(
  kind: "group" | "fantasy",
  week: string,
  purpose: string,
  extra: Partial<GameCard> = {},
): GameCard {
  return card(kind, week, purpose, {
    week_id: `week-${week}`,
    destination: `/leagues/league-a/weeks/week-${week}/${kind}`,
    ...extra,
  });
}

function legacyRound(startsOn: string): LegacyGameCard {
  return {
    format: "legacy",
    league_id: "league-a",
    week_id: `legacy-${startsOn}`,
    destination: `/leagues/two-one-hibs/predictions?gw=legacy-${startsOn}#coupon`,
    starts_on: startsOn,
    week_number: "16",
    status: "settled",
    locks_at: `${startsOn}T14:30:00Z`,
    can_pick: false,
    archived: true,
    picks_open_at: null,
    picked_count: 5,
    my_pick: null,
    fee: null,
  };
}

describe("the week bar (Batch 244)", () => {
  // Saturday 28 Nov, 15:30: this week's games have locked and its results are coming in;
  // next week's Fantasy opened at noon and its Group is announced. 14 Nov was legacy.
  const saturday = (): LeagueGames => ({
    ...league([
      weekCard("fantasy", "2026-11-21", "results", { archived: true, result: { final: true } }),
      weekCard("group", "2026-11-21", "results", { archived: true, result: { final: true } }),
      weekCard("fantasy", "2026-11-28", "results"),
      weekCard("group", "2026-11-28", "results"),
      weekCard("fantasy", "2026-12-05", "entry"),
      weekCard("group", "2026-12-05", "upcoming"),
    ]),
    legacy_rounds: [legacyRound("2026-11-14")],
  });

  it("lists every week oldest first, both games together, with a legacy round among them", () => {
    expect(
      weekStops(saturday()).map((stop) => [stop.label, !!stop.group, !!stop.fantasy, !!stop.legacy]),
    ).toEqual([
      ["2026-11-14", false, false, true],
      ["2026-11-21", true, true, false],
      ["2026-11-28", true, true, false],
      ["2026-12-05", true, true, false],
    ]);
  });

  it("leaves out a week whose games were all cancelled", () => {
    const games = league([
      weekCard("fantasy", "2026-11-21", "results", { entry_state: "cancelled" }),
      weekCard("group", "2026-11-21", "results", { entry_state: "cancelled" }),
      weekCard("fantasy", "2026-11-28", "entry"),
    ]);
    expect(weekStops(games).map((stop) => stop.label)).toEqual(["2026-11-28"]);
  });

  it("keeps Saturday's results as this week, with next week's open Fantasy one arrow on", () => {
    const step = weekStep(saturday(), { weekId: "week-2026-11-28", label: "2026-11-28" }, "fantasy");
    expect(step.relation).toBe("this");
    expect(step.next).toEqual({
      destination: "/leagues/league-a/weeks/week-2026-12-05/fantasy",
      label: "2026-12-05",
      fantasyOpen: true,
    });
    expect(step.previous).toEqual({
      destination: "/leagues/league-a/weeks/week-2026-11-21/fantasy",
      label: "2026-11-21",
    });
  });

  it("names next week as next, and steps the Group screen through Group weeks", () => {
    const step = weekStep(saturday(), { weekId: "week-2026-12-05", label: "2026-12-05" }, "group");
    expect(step.relation).toBe("next");
    expect(step.next).toBeNull();
    expect(step.previous?.destination).toBe("/leagues/league-a/weeks/week-2026-11-28/group");
  });

  it("steps back from the first two-game week into the legacy round before it", () => {
    const step = weekStep(saturday(), { weekId: "week-2026-11-21", label: "2026-11-21" }, "fantasy");
    expect(step.relation).toBe("past");
    expect(step.previous).toEqual({
      destination: "/leagues/two-one-hibs/predictions?gw=legacy-2026-11-14#coupon",
      label: "2026-11-14",
    });
  });

  it("places a deep-linked week older than the summary by its date", () => {
    const step = weekStep(saturday(), { weekId: "week-2026-10-31", label: "2026-10-31" }, "fantasy");
    expect(step.relation).toBe("past");
    expect(step.previous).toBeNull();
    expect(step.next?.destination).toBe(
      "/leagues/two-one-hibs/predictions?gw=legacy-2026-11-14#coupon",
    );
    expect(step.next?.fantasyOpen).toBe(false);
  });

  it("flips Group and Fantasy within the week on screen, else to the game's current week", () => {
    expect(switchTarget(saturday(), "group", "week-2026-11-21")?.destination).toBe(
      "/leagues/league-a/weeks/week-2026-11-21/group",
    );
    const fantasyOnly = league([
      weekCard("fantasy", "2026-11-21", "results"),
      weekCard("group", "2026-11-28", "upcoming"),
    ]);
    expect(switchTarget(fantasyOnly, "group", "week-2026-11-21")?.destination).toBe(
      "/leagues/league-a/weeks/week-2026-11-28/group",
    );
  });

  it("sends the Games tab to this week's results on Saturday afternoon, not next week's entry", () => {
    expect(gamesTabDestination(saturday())).toBe(
      "/leagues/league-a/weeks/week-2026-11-28/fantasy",
    );
  });
});
