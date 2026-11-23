import { describe, it, expect } from "vitest";
import {
  currentWeeks,
  gamesTabDestination,
  leagueForGames,
  switchCard,
} from "../lib/gameSwitch";
import type { GameCard, LeagueGames } from "../lib/twoGameTypes";

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

  it("lists every current week of one game, oldest first, for the week strip", () => {
    const games = league([
      card("fantasy", "2026-12-05", "entry"),
      card("fantasy", "2026-11-28", "results"),
      card("fantasy", "2026-11-21", "results", { archived: true }),
      card("group", "2026-11-28", "entry"),
    ]);
    expect(currentWeeks(games, "fantasy").map((value) => value.week_label)).toEqual([
      "2026-11-28",
      "2026-12-05",
    ]);
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

  it("passes over a game the member has already played for one they have not", () => {
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
    expect(gamesTabDestination(games)).toBe(
      "/leagues/league-a/weeks/2026-12-05/fantasy",
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
