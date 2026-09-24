/**
 * One place that decides what a cached thing is called.
 *
 * Batch 165. Keys were ad-hoc string arrays written at each call site, and the two
 * failures that causes had both already happened:
 *
 * * **An invalidation that matched nothing.** `LeagueActionsMenu` cleared
 *   `['leaderboard', slug]` after leaving a league. No query has ever been keyed
 *   `leaderboard` — the tables are keyed `standings` — so that call did nothing, silently.
 *   React Query cannot warn about it, because a key matching no query is an ordinary
 *   thing for a key to do.
 * * **The same data cached twice.** `MyLeaguesPage` asked for `['standings', slug]` and
 *   `LeaderboardPage` for `['standings', slug, season]`. With no season chosen those are
 *   one request under two names, fetched twice and expiring independently.
 *
 * The rule this enforces is that **a key names every input the request depends on**.
 * `standings` takes the season because the URL does; omitting it is how two seasons come
 * to share one entry.
 *
 * **The key shapes below are the ones already in use, deliberately.** Naming them is this
 * batch's job; reshaping them is not. `['league', slug]` in particular is both the detail
 * query's own key and the prefix its children hang off, and `LeagueAdminInvitesPage`
 * writes to it with `setQueryData`, which matches exactly rather than by prefix. Members
 * and seasons still live under their own roots for the same reason. A later batch can
 * bring them under `league` — with the factory in place that becomes one edit here rather
 * than a search for string literals.
 */

export const keys = {
  league: {
    /** The league itself. Also the prefix for anything nested under it. */
    detail: (slug: string) => ['league', slug] as const,
    competitions: (slug: string) => ['league', slug, 'competitions'] as const,
    /** Its own root today — see the note above. */
    members: (slug: string) => ['league-members', slug] as const,
    /** Its own root today — see the note above. */
    seasons: (slug: string) => ['seasons', slug] as const,
  },

  standings: {
    /** Every season's table for one league. A prefix of `forSeason`, so it clears all. */
    all: (slug: string) => ['standings', slug] as const,
    /**
     * One season's table.
     *
     * `null` means "whichever season the API considers current". That is a different
     * request from any named season and so must be a different key — not an absent one.
     * Spelled `'current'` rather than left as `null` so the key reads in devtools the way
     * the request reads.
     */
    forSeason: (slug: string, season: number | null) =>
      ['standings', slug, season ?? 'current'] as const,
  },

  leagues: {
    /** Every league the signed-in member belongs to. */
    mine: () => ['leagues', 'mine'] as const,
  },
} as const;
