import { describe, it, expect } from "vitest";
import {
  addressedGamesDestination,
  isAddressedGamePath,
  isLeagueHubPath,
  isCouponPath,
} from "../lib/leagues";
describe("addressed game navigation", () => {
  it.each([
    "/leagues/league-b/games",
    "/leagues/league-b/weeks/week-a/group",
    "/leagues/league-b/weeks/week-z/fantasy",
    "/leagues/former/games/",
  ])("owns only Games on %s", (path) => {
    expect(isAddressedGamePath(path)).toBe(true);
    expect(isLeagueHubPath(path)).toBe(false);
    expect(isCouponPath(path)).toBe(false);
    expect(addressedGamesDestination(path)).toBe(
      `/leagues/${path.split("/")[2]}/games`,
    );
  });
  it.each([
    "/leagues/league-b/gameweeks",
    "/leagues/league-b/weeks/week-a/group-extra",
    "/leagues/league-b/games/settings",
    "/leagues/league-b/weeks/week-a/unknown",
    "/football",
    "/leagues/league-b/predictions",
  ])("does not borrow a lookalike %s", (path) => {
    expect(isAddressedGamePath(path)).toBe(false);
    expect(addressedGamesDestination(path)).toBeUndefined();
  });
});
