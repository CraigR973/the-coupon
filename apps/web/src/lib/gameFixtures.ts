import { competitionRank } from "./competitions";

/**
 * Two-game fixtures grouped the way the old coupon groups its slate (Batch 232).
 *
 * The two-game fixtures carry the provider's competition slug and not its display name,
 * so until Batch 234 sends the names the heading is the slug made readable. Grouping and
 * order key off the slug either way, exactly as `CurrentRoundPage` does.
 */

/** The eight divisions the shared order names, as members know them. */
const KNOWN: Record<string, string> = {
  "england-premier-league": "Premier League",
  "england-championship": "Championship",
  "england-league-one": "League One",
  "england-league-two": "League Two",
  "scotland-premiership": "Scottish Premiership",
  "scotland-championship": "Scottish Championship",
  "scotland-league-one": "Scottish League One",
  "scotland-league-two": "Scottish League Two",
};

const titleCase = (words: string) =>
  words
    .split("-")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");

export function competitionName(competitionId: string): string {
  const known = KNOWN[competitionId];
  if (known) return known;
  if (competitionId.startsWith("england-"))
    return titleCase(competitionId.slice("england-".length));
  if (competitionId.startsWith("scotland-"))
    return `Scottish ${titleCase(competitionId.slice("scotland-".length))}`;
  return titleCase(competitionId) || competitionId;
}

export interface FixtureGroup<F> {
  competition_id: string;
  competition: string;
  fixtures: F[];
}

/** Grouped by slug, each group by kick-off, groups in the shared order then the fuller card. */
export function groupByCompetition<
  F extends { competition_id: string; kickoff_at: string; fixture_id: string },
>(fixtures: readonly F[]): FixtureGroup<F>[] {
  const groups = new Map<string, F[]>();
  for (const fixture of fixtures) {
    const bucket = groups.get(fixture.competition_id) ?? [];
    bucket.push(fixture);
    groups.set(fixture.competition_id, bucket);
  }
  return [...groups.entries()]
    .map(([competition_id, grouped]) => ({
      competition_id,
      competition: competitionName(competition_id),
      fixtures: [...grouped].sort(
        (a, b) =>
          Date.parse(a.kickoff_at) - Date.parse(b.kickoff_at) ||
          a.fixture_id.localeCompare(b.fixture_id),
      ),
    }))
    .sort((a, b) => {
      const ar = competitionRank(a.competition_id);
      const br = competitionRank(b.competition_id);
      return (
        ar[0] - br[0] ||
        ar[1] - br[1] ||
        b.fixtures.length - a.fixtures.length ||
        a.competition.localeCompare(b.competition) ||
        ar[2].localeCompare(br[2])
      );
    });
}
