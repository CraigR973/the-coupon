/**
 * Which built chunks the service worker should *not* download in advance.
 *
 * Batch 163. The app splits its routes properly — 67 emitted chunks — and then the
 * service worker precached all 82 manifest entries, 979 KiB, on install. That undoes the
 * splitting for everyone and spends a member's data on two admin consoles that
 * `requireAdmin` and the per-league guards will never let most of them open.
 *
 * The routes still work; they load on demand, like any other lazy route. What they no
 * longer do is arrive uninvited.
 *
 * Lives here rather than inline in `sw.ts` so the rule has one definition and a test can
 * hold it against the routes it claims to describe — see `precacheFilter.test.ts`, which
 * fails if an admin route is added whose chunk this would still precache.
 */

/**
 * The site-admin console, `src/pages/admin/*`.
 *
 * Matched by prefix, which is why those files are all named `Admin*`. Before Batch 163
 * two of them were `DashboardPage.tsx` and `ResultsPage.tsx` — the same basenames as the
 * member-facing pages, and therefore the same chunk names. A filter written against that
 * layout would have stopped precaching **home**.
 */
const SITE_ADMIN = /(^|\/)Admin[A-Za-z]*(Page|Nav)-[A-Za-z0-9_-]+\.js$/;

/**
 * The per-league admin console, `/leagues/:slug/admin/*`.
 *
 * Named individually because these pages live beside member-facing ones in `src/pages/`
 * and share no prefix. The test keeps this list honest against `App.tsx`.
 */
export const LEAGUE_ADMIN_PAGES = [
  'LeagueMembersPage',
  'LeagueSettingsPage',
  'LeagueJoinRequestsPage',
  'LeagueAdminInvitesPage',
  'LeagueAuditLogPage',
] as const;

const LEAGUE_ADMIN = new RegExp(
  `(^|/)(${LEAGUE_ADMIN_PAGES.join('|')})-[A-Za-z0-9_-]+\\.js$`,
);

/** True when this manifest entry belongs to a console most members cannot open. */
export function isRoleGatedChunk(url: string): boolean {
  return SITE_ADMIN.test(url) || LEAGUE_ADMIN.test(url);
}
