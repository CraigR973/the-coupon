import { parseInstant } from './time';
import type { GameCard, LeagueGames } from './twoGameTypes';

/**
 * What one league card on home is *about* right now.
 *
 * Batch 106. A card used to be assembled from whatever fields happened to be present, so
 * a settled round with a future opening printed the previous round's pick, fold and
 * combined odds directly beside `Next opens in 2d` — two different rounds, one paragraph,
 * neither labelled. The fix is to name the state first and let it decide what the primary
 * part of the card is allowed to say.
 *
 * The four are the whole space, and each one has exactly one next action:
 *
 * - `pick_required` — this league is waiting on the member. The deadline is the news.
 * - `pick_submitted` — they are in; the deadline and how many others are still out.
 * - `round_in_progress` — claiming has stopped and settlement has not happened. The
 *   coupon is frozen, so this is the one state where the fold and the combined price are
 *   a fact about now rather than a volatile number.
 * - `between_rounds` — nothing to claim: the round settled, or has not opened, or the
 *   league has no round at all. The next *opening* is the news, and everything about the
 *   round just gone belongs under `Last result`.
 *
 * Each league answers from its own summary. Nothing here reads a clock the league did not
 * supply, because the Saturday-at-14:30 default is one league's configuration and not the
 * product's rule.
 */
export type HomeCardState =
  | 'pick_required'
  | 'pick_submitted'
  | 'round_in_progress'
  | 'between_rounds';

export interface HomeRoundFacts {
  /** False when the league has published no round at all. */
  hasRound: boolean;
  settled: boolean;
  /** The round's claim window has not opened yet. */
  notOpenYet: boolean;
  /** Claiming has stopped — the deadline passed, or the round left the pickable states. */
  claimingShut: boolean;
  /** Whether the member holds a selection on this round. */
  mine: boolean;
}

export function homeCardState(facts: HomeRoundFacts): HomeCardState {
  if (!facts.hasRound || facts.settled || facts.notOpenYet) return 'between_rounds';
  if (facts.claimingShut) return 'round_in_progress';
  return facts.mine ? 'pick_submitted' : 'pick_required';
}

/** The chip each state carries. Colour supports the word; it never replaces it. */
export const HOME_CARD_STATE: Record<
  HomeCardState,
  { label: string; variant: 'warning' | 'success' | 'default' | 'muted' }
> = {
  pick_required: { label: 'Pick required', variant: 'warning' },
  pick_submitted: { label: 'Pick submitted', variant: 'success' },
  round_in_progress: { label: 'Round in progress', variant: 'default' },
  between_rounds: { label: 'Between rounds', variant: 'muted' },
};

/**
 * Whether the round's own coupon figures may appear in the primary part of the card.
 *
 * Only once the round is frozen. While picks are open the fold changes every time anybody
 * claims anything, so it competes with the deadline for attention and loses the member
 * nothing when it is left out; once claiming has stopped it is the round.
 */
export function showsCouponFigures(state: HomeCardState): boolean {
  return state === 'round_in_progress';
}

/** One entry inside a two-game league, as home counts it: when it locks and where it is. */
export interface TwoGameEntry {
  locksAt: string;
  destination: string;
}

/**
 * Where a two-game league stands for the member right now (Batch 239), from `/me/games`.
 *
 * The cross-league summary cannot answer this: it reads legacy rounds only, so on a
 * two-game league its `current_round` is the last legacy round, not this week. The
 * league's own cards can. A game is open only while the API said so *and* its lock is
 * still ahead on this device's clock, so a card read a minute before the lock stops
 * prompting at the lock rather than at the next refetch. A legacy round still in play
 * on the same league (the week before the switch) counts exactly as it does elsewhere.
 */
export interface TwoGameEntryFacts {
  /** Open entries still missing the member's pick, soonest lock first. */
  needs: TwoGameEntry[];
  /** Open entries the member has made, soonest lock first. */
  ready: TwoGameEntry[];
  /** Something has locked and is not final yet. */
  inProgress: boolean;
  /** The next announced opening still ahead, and the entry it opens. */
  next: { opensAt: string; destination: string } | null;
}

export function twoGameEntryFacts(league: LeagueGames, now = Date.now()): TwoGameEntryFacts {
  const needs: TwoGameEntry[] = [];
  const ready: TwoGameEntry[] = [];
  let inProgress = false;
  for (const card of league.games) {
    if (card.archived || card.entry_state === 'cancelled') continue;
    const locksAt = parseInstant(card.locks_at).getTime();
    if (card.entry_state === 'open' && now < locksAt) {
      // Fantasy wants all six: an empty slot can only add points, never cost any.
      const done =
        card.game_kind === 'group'
          ? !!card.my_entry?.pick
          : (card.progress.slots_filled ?? 0) >= 6;
      (done ? ready : needs).push({ locksAt: card.locks_at, destination: card.destination });
    } else if (now >= locksAt && !card.result.final) {
      inProgress = true;
    }
  }
  for (const round of league.legacy_rounds) {
    if (round.archived || round.status === 'cancelled' || round.status === 'settled') continue;
    const locksAt = parseInstant(round.locks_at).getTime();
    const opensAt = round.picks_open_at ? parseInstant(round.picks_open_at).getTime() : null;
    if (now >= locksAt) inProgress = true;
    else if (round.can_pick && (opensAt === null || opensAt <= now)) {
      (round.my_pick ? ready : needs).push({
        locksAt: round.locks_at,
        destination: round.destination,
      });
    }
  }
  const soonest = (a: TwoGameEntry, b: TwoGameEntry) =>
    parseInstant(a.locksAt).getTime() - parseInstant(b.locksAt).getTime();
  needs.sort(soonest);
  ready.sort(soonest);
  const opensAt = league.next_game_opens_at;
  const upcoming =
    opensAt && parseInstant(opensAt).getTime() > now
      ? league.games.find((card) => card.game_kind === 'fantasy' && card.opens_at === opensAt)
      : undefined;
  return {
    needs,
    ready,
    inProgress,
    next:
      opensAt && parseInstant(opensAt).getTime() > now
        ? {
            opensAt,
            destination: upcoming?.destination ?? `/leagues/${league.league_id}/games`,
          }
        : null,
  };
}

/** A two-game week's own cards, as the `Last result` panel reports them. */
export interface TwoGameWeekResult {
  weekId: string;
  /** The week's Saturday, `yyyy-mm-dd`. */
  weekLabel: string;
  group: GameCard | null;
  fantasy: GameCard | null;
}

/**
 * The most recent two-game week whose results are final (Batch 239), or `null`.
 *
 * Final means every game that week is final or was cancelled, and at least one is final:
 * a week whose fantasy game is still provisional is still on the entry rows above as
 * 'Locked results', and the panel reports the week before it until it is done, as a
 * legacy round's `Last result` waits for settlement.
 */
export function lastTwoGameWeek(league: LeagueGames): TwoGameWeekResult | null {
  const weeks = new Map<string, GameCard[]>();
  for (const card of league.games) {
    weeks.set(card.week_id, [...(weeks.get(card.week_id) ?? []), card]);
  }
  let latest: TwoGameWeekResult | null = null;
  for (const [weekId, cards] of weeks) {
    const final =
      cards.some((card) => card.result.final) &&
      cards.every((card) => card.result.final || card.entry_state === 'cancelled');
    if (!final) continue;
    const weekLabel = cards[0]!.week_label;
    if (latest && latest.weekLabel >= weekLabel) continue;
    latest = {
      weekId,
      weekLabel,
      group: cards.find((card) => card.game_kind === 'group' && card.result.final) ?? null,
      fantasy: cards.find((card) => card.game_kind === 'fantasy' && card.result.final) ?? null,
    };
  }
  return latest;
}
