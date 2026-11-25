import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { GameCard, LeagueGames } from "../lib/twoGameTypes";

const nav = vi.hoisted(() => ({ leagues: [] as unknown[] }));
vi.mock("../hooks/useGameIntents", () => ({
  useGameNavigation: () => nav.leagues,
}));

import { GameHeader, GameRules } from "../components/GameHeader";

/**
 * Batch 244: the game screens' week bar. One week on screen, arrows to the weeks either
 * side (a dot when next week's Fantasy is open), Home and the archive at either end, then
 * Group and Fantasy for the week on screen.
 */
function card(
  kind: "group" | "fantasy",
  week: string,
  purpose: string,
  extra: Partial<GameCard> = {},
): GameCard {
  return {
    league_id: "league-a",
    week_id: `week-${week}`,
    game_kind: kind,
    game_id: `game-${kind}-${week}`,
    week_label: week,
    week_number: "1",
    destination: `/leagues/league-a/weeks/week-${week}/${kind}`,
    opens_at: `${week}T03:00:00Z`,
    locks_at: kind === "group" ? `${week}T14:30:00Z` : `${week}T12:00:00Z`,
    entry_state: purpose === "entry" ? "open" : purpose === "results" ? "locked" : "not_open",
    purpose,
    archived: false,
    fee: {} as GameCard["fee"],
    coverage_state: "complete",
    result_version: 1,
    progress: { slots_filled: 4 },
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
    server_now: "2026-11-28T15:30:00Z",
    games,
    legacy_rounds: [],
    next_cursor: null,
    next_game_state: "known",
    next_game_opens_at: null,
    season_stats: null,
    weekly_form: [],
  };
}

function renderHeader(week: string, kind: "group" | "fantasy" = "fantasy") {
  render(
    <MemoryRouter>
      <GameHeader
        target={{ league_id: "league-a", week_id: `week-${week}`, game_kind: kind }}
        weekLabel={week}
      />
    </MemoryRouter>,
  );
  return screen.getByRole("navigation", { name: "Game navigation" });
}

describe("the week bar", () => {
  beforeEach(() => {
    // Saturday afternoon: this week's results are coming in, next week's Fantasy is open.
    nav.leagues = [
      league([
        card("fantasy", "2026-11-21", "results", { archived: true, result: { final: true } }),
        card("fantasy", "2026-11-28", "results"),
        card("group", "2026-11-28", "results"),
        card("fantasy", "2026-12-05", "entry", { progress: { slots_filled: 0 } }),
        card("group", "2026-12-05", "upcoming"),
      ]),
    ];
  });

  it("names this week, and steps back and on with a dot for next week's open Fantasy", () => {
    const bar = renderHeader("2026-11-28");
    expect(within(bar).getByText("This week")).toBeTruthy();
    expect(within(bar).getByText("Sat 28 Nov")).toBeTruthy();
    expect(within(bar).getByRole("link", { name: "Earlier week, Sat 21 Nov" })).toHaveAttribute(
      "href",
      "/leagues/league-a/weeks/week-2026-11-21/fantasy",
    );
    const next = within(bar).getByRole("link", { name: "Next week, Sat 5 Dec, Fantasy open" });
    expect(next).toHaveAttribute("href", "/leagues/league-a/weeks/week-2026-12-05/fantasy");
    expect(within(next).getByTestId("next-week-dot")).toBeTruthy();
  });

  it("keeps Home and the archive at either end of the bar", () => {
    const bar = renderHeader("2026-11-28");
    expect(within(bar).getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
    expect(within(bar).getByRole("link", { name: "Game archive" })).toHaveAttribute(
      "href",
      "/leagues/league-a/games",
    );
  });

  it("switches Group and Fantasy within the week on screen", () => {
    renderHeader("2026-11-28");
    const games = screen.getByRole("navigation", { name: "Game switch" });
    const group = within(games).getByRole("link", { name: /Group/ });
    expect(group).toHaveAttribute("href", "/leagues/league-a/weeks/week-2026-11-28/group");
    expect(group).toHaveTextContent("Results");
    expect(within(games).getByRole("link", { name: /Fantasy/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("names a past week as results and next week as next, with no arrow past the last", () => {
    const past = renderHeader("2026-11-21");
    expect(within(past).getByText("Results")).toBeTruthy();
    expect(within(past).queryByRole("link", { name: /^Earlier week/ })).toBeNull();
  });

  it("names next week as next week, with nothing announced after it", () => {
    const next = renderHeader("2026-12-05", "group");
    expect(within(next).getByText("Next week")).toBeTruthy();
    expect(within(next).queryByRole("link", { name: /^Next week/ })).toBeNull();
    expect(within(next).getByRole("link", { name: "Earlier week, Sat 28 Nov" })).toHaveAttribute(
      "href",
      "/leagues/league-a/weeks/week-2026-11-28/group",
    );
  });

  it("still names the week, with Home and the archive, when the summary does not list the league", () => {
    nav.leagues = [];
    const bar = renderHeader("2026-11-28");
    expect(within(bar).getByText("Sat 28 Nov")).toBeTruthy();
    expect(within(bar).getByRole("link", { name: "Home" })).toBeTruthy();
    expect(within(bar).getByRole("link", { name: "Game archive" })).toBeTruthy();
    expect(within(bar).queryByRole("link", { name: /week,/ })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Game switch" })).toBeNull();
  });
});

describe("the rules line", () => {
  it("keeps the full rule text one tap away", () => {
    render(
      <GameRules summary="Up to six picks.">
        <p>Partial entries count.</p>
      </GameRules>,
    );
    expect(screen.queryByText("Partial entries count.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "How it works" }));
    expect(screen.getByRole("dialog", { name: "How it works" })).toHaveTextContent(
      "Partial entries count.",
    );
  });
});
