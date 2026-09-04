/** Plain-text clipboard payloads for the coupon and standings surfaces. */

import { formatOdds, pickStatusLabel, selectionSummary } from './coupon';
import type { Coupon, Standing } from './types';

/**
 * The one sentence about frozen prices, printed once per payload.
 *
 * It used to be printed twice — a parenthetical on the combined-odds line and a paragraph
 * under the legs — which is the repetition Batch 105 was asked to remove. The fact is
 * worth stating; stating it twice in eight lines is what made the text read as boilerplate
 * rather than as a warning.
 */
const FROZEN_ODDS_NOTE =
  'Odds were frozen when each member picked — check your book for current prices before placing anything.';

/** How the fold reads, and whether it is a whole coupon or a round the deadline caught. */
function foldLine(coupon: Coupon, memberCount?: number): string {
  const fold = `${coupon.leg_count}-fold accumulator @ ${formatOdds(coupon.combined_odds)}`;
  const missing = memberCount == null ? 0 : memberCount - coupon.leg_count;
  return missing > 0 ? `${fold} — incomplete, ${missing} of ${memberCount} never picked` : fold;
}

/**
 * One line per person: who, what they took, the context that disambiguates it, the price.
 *
 * Batch 105 took the competition and the market tag out. `Draw @ 3.50 - Forfar v Brechin
 * (Scottish League 2, 1X2)` said "this is a match-result market" three times over — once
 * in the word Draw, once in the fixture, once in the tag — and the competition
 * disambiguated nothing, because no two fixtures in one round carry the same two teams.
 */
function legLine(coupon: Coupon, index: number): string {
  const leg = coupon.legs[index];
  const selection = selectionSummary(leg.market, leg.outcome, leg.home, leg.away);
  return `${index + 1}. ${leg.player_name} — ${selection} @ ${formatOdds(leg.odds)}`;
}

export interface CouponShareContext {
  /** The round, as the surface names it — "Gameweek 12". Omitted when it has no name. */
  roundLabel?: string;
  /** How many members the league has, so an incomplete coupon can say so. */
  memberCount?: number;
}

export function buildCouponShareText(coupon: Coupon, context: CouponShareContext = {}): string {
  const heading = context.roundLabel ? `The Coupon — ${context.roundLabel}` : 'The Coupon';
  return [
    heading,
    foldLine(coupon, context.memberCount),
    '',
    ...coupon.legs.map((_, i) => legLine(coupon, i)),
    '',
    FROZEN_ODDS_NOTE,
  ].join('\n');
}

/**
 * The same pasteable coupon shape, after the round has become a result.
 *
 * The frozen prices still explain what everybody claimed, but the headline now says
 * what landed and each resolved fixture carries its final score, status and points.
 * A missing score is simply absent: the result join deliberately fails open, so share
 * text must not turn an unknown score into nil-nil.
 */
export function buildSettledResultShareText(
  coupon: Coupon,
  context: CouponShareContext = {},
): string {
  const landed = coupon.legs.filter((leg) => leg.status === 'won').length;
  const round = context.roundLabel ? ` — ${context.roundLabel}` : '';
  return [
    `The Coupon: Result${round} — ${landed} of ${coupon.leg_count} picks landed`,
    foldLine(coupon, context.memberCount),
    '',
    ...coupon.legs.map((leg, i) => {
      const score =
        leg.home_goals != null && leg.away_goals != null
          ? ` — ${leg.home} ${leg.home_goals}–${leg.away_goals} ${leg.away}`
          : '';
      const points = leg.points_awarded != null ? `, ${leg.points_awarded} pts` : '';
      return `${legLine(coupon, i)}${score} — ${pickStatusLabel(leg.status)}${points}`;
    }),
    '',
    FROZEN_ODDS_NOTE,
  ].join('\n');
}

/** Plain text for the table on screen — one league and one selected season. */
export function buildStandingsShareText(
  leagueName: string,
  seasonHeading: string,
  standings: Standing[],
): string {
  return [
    `The Coupon: ${leagueName} — ${seasonHeading}`,
    '',
    ...standings.map(
      (standing) =>
        `#${standing.rank} ${standing.display_name} - ${standing.total_points} pts - ${standing.picks_won}/${standing.picks_played} picks won`,
    ),
  ].join('\n');
}
