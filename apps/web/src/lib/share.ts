/** Plain-text clipboard payloads for the coupon and standings surfaces. */

import { formatOdds, marketTag, outcomeLabel, pickStatusLabel } from './coupon';
import type { Coupon, Standing } from './types';

export function buildCouponShareText(coupon: Coupon): string {
  const lines = [
    `The Coupon: ${coupon.leg_count}-fold accumulator`,
    `Frozen combined odds: ${formatOdds(coupon.combined_odds)} (historical, from pick time)`,
    '',
    ...coupon.legs.map((leg, i) => {
      const selection = outcomeLabel(leg.market, leg.outcome, leg.home, leg.away);
      return `${i + 1}. ${selection} @ ${formatOdds(leg.odds)} - ${leg.home} v ${leg.away} (${leg.competition}, ${marketTag(leg.market)}) - ${leg.player_name}`;
    }),
    '',
    'Prices were frozen when each member picked. Check your book for current odds before placing anything.',
  ];
  return lines.join('\n');
}

/**
 * The same pasteable coupon shape, after the round has become a result.
 *
 * The frozen prices still explain what everybody claimed, but the headline now says
 * what landed and each resolved fixture carries its final score, status and points.
 * A missing score remains `home v away`: the result join deliberately fails open, so
 * share text must not turn an unknown score into nil-nil.
 */
export function buildSettledResultShareText(coupon: Coupon): string {
  const landed = coupon.legs.filter((leg) => leg.status === 'won').length;
  const lines = [
    `The Coupon: Result — ${landed} of ${coupon.leg_count} picks landed`,
    `Frozen combined odds: ${formatOdds(coupon.combined_odds)} (historical, from pick time)`,
    '',
    ...coupon.legs.map((leg, i) => {
      const selection = outcomeLabel(leg.market, leg.outcome, leg.home, leg.away);
      const fixture =
        leg.home_goals != null && leg.away_goals != null
          ? `${leg.home} ${leg.home_goals}–${leg.away_goals} ${leg.away}`
          : `${leg.home} v ${leg.away}`;
      const points = leg.points_awarded != null ? `, ${leg.points_awarded} pts` : '';
      return `${i + 1}. ${selection} @ ${formatOdds(leg.odds)} - ${fixture} (${leg.competition}, ${marketTag(leg.market)}) - ${leg.player_name} - ${pickStatusLabel(leg.status)}${points}`;
    }),
    '',
    'Prices were frozen when each member picked. Check your book for current odds before placing anything.',
  ];
  return lines.join('\n');
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
