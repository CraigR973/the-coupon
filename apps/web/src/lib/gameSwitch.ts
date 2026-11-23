import type { GameCard, GameKind, LeagueGames } from "./twoGameTypes";

/**
 * Which week of each game the coupon screen's switch and the Games tab open (Batch 232).
 *
 * Read from the home summary (`GET /me/games`), which already lists every game a member
 * can act on or is waiting on, so neither needs a request of its own.
 */

/** Open entry first, then results still coming in, then the next opening. */
const PURPOSE_ORDER: Record<string, number> = { entry: 0, results: 1, upcoming: 2 };
const order = (card: GameCard) => PURPOSE_ORDER[card.purpose] ?? 3;

function current(league: LeagueGames, kind: GameKind): GameCard[] {
  return league.games.filter((card) => card.game_kind === kind && !card.archived);
}

/**
 * The week a game's switch segment opens.
 *
 * Within results the newest week comes first (the one being played); within an opening
 * the soonest. On a Saturday afternoon that sends Fantasy to next week's open card while
 * this week's results stay one tap away in the week strip.
 */
export function switchCard(
  league: LeagueGames,
  kind: GameKind,
): GameCard | undefined {
  return [...current(league, kind)].sort((a, b) => {
    const byPurpose = order(a) - order(b);
    if (byPurpose !== 0) return byPurpose;
    return order(a) === 1
      ? b.week_label.localeCompare(a.week_label)
      : a.week_label.localeCompare(b.week_label);
  })[0];
}

/** Every current week of one game, oldest first, for the week strip. */
export function currentWeeks(league: LeagueGames, kind: GameKind): GameCard[] {
  return [...current(league, kind)].sort((a, b) =>
    a.week_label.localeCompare(b.week_label),
  );
}

const isOpen = (card: GameCard) =>
  card.purpose === "entry" && card.entry_state === "open";

/** An open game the member has put nothing into yet. */
function untouched(card: GameCard): boolean {
  if (!isOpen(card)) return false;
  return card.game_kind === "group"
    ? !card.my_entry?.pick
    : (card.progress.slots_filled ?? 0) === 0;
}

/**
 * Where the Games tab takes a member of a two-game league: the open game they have not
 * touched that locks soonest, else any open game by lock, else the current fantasy or
 * group week, and only when there is none of those, the archive.
 */
export function gamesTabDestination(league: LeagueGames): string {
  const open = league.games
    .filter((card) => !card.archived && isOpen(card))
    .sort((a, b) => Date.parse(a.locks_at) - Date.parse(b.locks_at));
  const card =
    open.find(untouched) ??
    open[0] ??
    switchCard(league, "fantasy") ??
    switchCard(league, "group");
  return card?.destination ?? `/leagues/${league.league_id}/games`;
}

/** The league a path belongs to, for the tab bar: the addressed one, else the active one. */
export function leagueForGames(
  leagues: readonly LeagueGames[],
  addressedArchive: string | undefined,
  activeSlug: string | null,
): LeagueGames | undefined {
  const addressedId = addressedArchive?.split("/")[2];
  return addressedId
    ? leagues.find((league) => league.league_id === addressedId)
    : leagues.find((league) => league.slug === activeSlug);
}
