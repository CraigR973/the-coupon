import { homeWeek } from "./home";
import type { GameCard, GameKind, LeagueGames, LegacyGameCard } from "./twoGameTypes";

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

/** One football week as the game screens step through it (Batch 244). */
export interface WeekStop {
  weekId: string;
  /** The week's Saturday, `yyyy-mm-dd`. */
  label: string;
  group: GameCard | null;
  fantasy: GameCard | null;
  /** A legacy round, which is a week of its own on the old coupon screen. */
  legacy: LegacyGameCard | null;
}

/**
 * Every week the summary lists for one league, oldest first (Batch 244): each two-game week
 * with its games, finished or not, and each legacy round. The summary carries the live weeks
 * and the five most recent finished ones, so that is how far the arrows step; the archive
 * lists the rest. A week whose games were all cancelled is left out.
 */
export function weekStops(league: LeagueGames): WeekStop[] {
  const stops = new Map<string, WeekStop>();
  for (const card of league.games) {
    const stop = stops.get(card.week_id) ?? {
      weekId: card.week_id,
      label: card.week_label,
      group: null,
      fantasy: null,
      legacy: null,
    };
    stop[card.game_kind] = card;
    stops.set(card.week_id, stop);
  }
  for (const round of league.legacy_rounds) {
    if (round.status === "cancelled" || stops.has(round.week_id)) continue;
    stops.set(round.week_id, {
      weekId: round.week_id,
      label: round.starts_on,
      group: null,
      fantasy: null,
      legacy: round,
    });
  }
  return [...stops.values()]
    .filter(
      (stop) =>
        stop.legacy ||
        [stop.group, stop.fantasy].some((card) => card && card.entry_state !== "cancelled"),
    )
    .sort((a, b) => a.label.localeCompare(b.label) || a.weekId.localeCompare(b.weekId));
}

/** Where a week takes one game's screen: that game, else the week's other one, else its round. */
export function stopDestination(stop: WeekStop, kind: GameKind): string {
  const other = kind === "group" ? stop.fantasy : stop.group;
  return (stop[kind] ?? other)?.destination ?? stop.legacy?.destination ?? "";
}

/** How a week relates to the one Home shows (Batch 243's rule). */
export type WeekRelation = "this" | "next" | "past";

export interface WeekStep {
  previous: { destination: string; label: string } | null;
  /** `fantasyOpen` puts the dot on the arrow: next week's Fantasy is already open. */
  next: { destination: string; label: string; fantasyOpen: boolean } | null;
  relation: WeekRelation;
}

/**
 * The arrows either side of the week a game screen shows (Batch 244), and what that week is
 * to the member. The week is placed by its date, so a week older than the summary's window,
 * reached from the archive, still gets an arrow back towards the present.
 */
export function weekStep(
  league: LeagueGames,
  week: { weekId: string; label: string },
  kind: GameKind,
): WeekStep {
  const others = weekStops(league).filter((stop) => stop.weekId !== week.weekId);
  const previous = [...others].reverse().find((stop) => stop.label < week.label) ?? null;
  const next = others.find((stop) => stop.label > week.label) ?? null;
  const home = homeWeek(league);
  const legacyLabel = home.legacyInPlay
    ? league.legacy_rounds.find(
        (round) => !round.archived && round.status !== "cancelled" && round.status !== "settled",
      )?.starts_on
    : undefined;
  const thisWeek = home.week?.weekLabel ?? legacyLabel;
  const relation: WeekRelation =
    thisWeek === undefined || week.label < thisWeek
      ? "past"
      : week.label === thisWeek
        ? "this"
        : "next";
  return {
    previous: previous
      ? { destination: stopDestination(previous, kind), label: previous.label }
      : null,
    next: next
      ? {
          destination: stopDestination(next, kind),
          label: next.label,
          fantasyOpen: next.fantasy?.purpose === "entry" && next.fantasy.entry_state === "open",
        }
      : null,
    relation,
  };
}

/**
 * The switch segment for one game while a week is on screen: that week's game when it has
 * one, so Group and Fantasy flip within the week; otherwise the game's own current week.
 */
export function switchTarget(
  league: LeagueGames,
  kind: GameKind,
  weekId: string,
): GameCard | undefined {
  return (
    league.games.find((card) => card.week_id === weekId && card.game_kind === kind) ??
    switchCard(league, kind)
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

const byLock = (a: GameCard, b: GameCard) => Date.parse(a.locks_at) - Date.parse(b.locks_at);

/**
 * Where the Games tab takes a member of a two-game league.
 *
 * Batch 244 (owner, 25 Nov 2026): the week is Home's (243), this week until its results are
 * final, so Saturday afternoon opens this week's results and next week's Fantasy waits behind
 * the arrow with its dot. Within the week, the open game they have not touched that locks
 * soonest, else any open game by lock, else the week's Fantasy, else its Group. With no such
 * week (a legacy round still in play, or nothing announced), the open game they have not
 * touched, else any open game, else the current fantasy or group week, and only when there is
 * none of those, the archive.
 */
export function gamesTabDestination(league: LeagueGames): string {
  const { week } = homeWeek(league);
  if (week) {
    const games = [week.group, week.fantasy].filter((card): card is GameCard => !!card);
    const open = games.filter(isOpen).sort(byLock);
    const card = open.find(untouched) ?? open[0] ?? week.fantasy ?? week.group;
    if (card) return card.destination;
  }
  const open = league.games.filter((card) => !card.archived && isOpen(card)).sort(byLock);
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
