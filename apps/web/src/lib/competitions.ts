/**
 * One reading order for British football, shared by every screen that lists
 * competitions.
 *
 * It started on the pick screen and stayed there, so Football Stats — the other
 * screen showing the same competitions — rendered them in whatever order the API
 * happened to return, which is the ingestion job's order and means nothing to a
 * reader. Two screens covering one set of divisions have to agree on how that set
 * is arranged, or the second one costs a search every time.
 *
 * Ordering keys off `competition_id`, the provider's stable slug, never the display
 * name: names carry sponsor text and have changed before.
 */

/** The eight divisions with a fixed, non-negotiable order, best first. */
const COMPETITION_ORDER = new Map(
  [
    'england-premier-league',
    'england-championship',
    'england-league-one',
    'england-league-two',
    'scotland-premiership',
    'scotland-championship',
    'scotland-league-one',
    'scotland-league-two',
  ].map((id, index) => [id, index] as const),
);

const ENGLAND_REMAINING_TIERS: Array<[RegExp, number]> = [
  [/^england-national-league$/, 0],
  [/^england-national-league-(north|south)$/, 1],
  [/^england-(northern-premier|southern|isthmian)-league$/, 2],
  [/^england-.*division-one/, 3],
];

const SCOTLAND_REMAINING_TIERS: Array<[RegExp, number]> = [
  [/^scotland-(highland|lowland)-league$/, 0],
  [/^scotland-.*division-one/, 1],
];

function remainingTier(competitionId: string, tiers: Array<[RegExp, number]>): number {
  return tiers.find(([pattern]) => pattern.test(competitionId))?.[1] ?? 99;
}

/**
 * A competition's sort key: `[bucket, tier, id]`.
 *
 * Bucket 0 is the named ladder above, then everything else English, then everything
 * else Scottish, then anything the slug does not place at all — a cup, or a country
 * the provider adds later. Within a bucket the pyramid tiers order what they match
 * and 99 sinks the rest, so an unrecognised division lands at the bottom of its own
 * country rather than in the middle of the league it sorts next to alphabetically.
 */
export function competitionRank(competitionId: string): [number, number, string] {
  const ordered = COMPETITION_ORDER.get(competitionId);
  if (ordered !== undefined) return [0, ordered, competitionId];
  if (competitionId.startsWith('england-')) {
    return [1, remainingTier(competitionId, ENGLAND_REMAINING_TIERS), competitionId];
  }
  if (competitionId.startsWith('scotland-')) {
    return [2, remainingTier(competitionId, SCOTLAND_REMAINING_TIERS), competitionId];
  }
  return [3, 0, competitionId];
}

/**
 * Compare two competitions by identity alone — the order Football Stats reads in.
 *
 * The pick screen adds one tiebreak this cannot: it puts the fuller card first among
 * competitions that rank equally, which is a property of that screen's slate rather
 * than of the competition. It composes this and then applies its own.
 */
export function compareCompetitions(
  a: { competition_id: string; competition: string },
  b: { competition_id: string; competition: string },
): number {
  const ar = competitionRank(a.competition_id);
  const br = competitionRank(b.competition_id);
  return (
    ar[0] - br[0] ||
    ar[1] - br[1] ||
    a.competition.localeCompare(b.competition) ||
    ar[2].localeCompare(br[2])
  );
}
