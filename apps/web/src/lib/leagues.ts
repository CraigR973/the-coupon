/**
 * Shared league helpers — privacy labels, etc.
 * Single source of truth: update here, both pages stay in sync.
 */

import type { QueryClient } from '@tanstack/react-query';

/** The real enum values the API serialises on league.privacy. */
export type LeaguePrivacy = 'public_open' | 'public_request' | 'private';

/**
 * What each privacy value actually does, as the API implements it today.
 *
 * `private` is the default: since Batch 63 opened self-registration, "public" no longer
 * means "people the creator already knows" — it means anyone who has signed up. The
 * least-private option should not be what someone gets by not touching this dropdown.
 *
 * Sources: `routers/leagues.py` — discover filters to the two public values; joining a
 * private league by slug is refused `PRIVATE_LEAGUE`; `public_open` joins instantly and
 * `public_request` creates a request the admin approves. The join code admits anyone who
 * holds it regardless of privacy (`routers/league_memberships.py::join_league_by_code`).
 */
export const PRIVACY_OPTIONS: readonly {
  value: LeaguePrivacy;
  label: string;
  help: string;
}[] = [
  {
    value: 'private',
    label: 'Private — invite only',
    help: 'Hidden from Discover. Only people you send the join code to can get in.',
  },
  {
    value: 'public_request',
    label: 'Public — anyone can ask to join',
    help: 'Listed in Discover. Anyone with an account can request to join, and you approve or decline each request.',
  },
  {
    value: 'public_open',
    label: 'Public — anyone can join instantly',
    help: 'Listed in Discover. Anyone with an account can join without asking you, including people you have never met.',
  },
];

/**
 * Human-readable label for a league privacy value.
 * Returns an empty string for any unrecognised value so callers can
 * detect a missing label rather than showing "undefined".
 */
export const PRIVACY_LABELS: Record<LeaguePrivacy, string> = {
  public_open: 'Public',
  public_request: 'Public · request to join',
  private: 'Private',
};

/** Convenience helper — returns '' for unknown values. */
export function privacyLabel(privacy: string): string {
  return PRIVACY_LABELS[privacy as LeaguePrivacy] ?? '';
}

/**
 * The coupon's destinations, as the suffix each adds to a league's predictions path.
 *
 * Two of them are destinations since Batch 105 — the current round and the season behind
 * it. `/coupon` is the third address this surface used to answer at, kept in the union
 * because it is still *reachable*: every notification tap, bookmark and shared link
 * minted before that batch points at it, and it now redirects to the current round's
 * copy section rather than 404ing.
 */
export type PredictionsSection = '' | '/coupon' | '/results';

const PREDICTIONS_SECTIONS: readonly string[] = ['', '/coupon', '/results'];

/**
 * Where the current round's coupon — the fold, the frozen combined price and the control
 * that copies it — answers on the page.
 *
 * An id rather than a route because Batch 105 merged the combined coupon into the current
 * round, and a section of a page is addressed by a fragment. Exported as one constant so
 * the anchor, the redirect that targets it, and the links that deep-link into it cannot
 * drift apart; Batch 107's all-picked notification is the next caller.
 */
export const COUPON_SECTION_ID = 'coupon';

/** The fragment form of :data:`COUPON_SECTION_ID`. */
export const COUPON_SECTION_HASH = `#${COUPON_SECTION_ID}`;

/**
 * A link straight to one round's copy section.
 *
 * The gameweek id is league-scoped, so both halves of the address matter: it only
 * resolves against the league it came from.
 */
export function couponSectionPath(slug: string | null, gameweekId?: string | null): string {
  const query = gameweekId ? `?gw=${encodeURIComponent(gameweekId)}` : '';
  return `${predictionsPath(slug)}${query}${COUPON_SECTION_HASH}`;
}

/**
 * Football Stats, which is not one of them.
 *
 * It sat at `/leagues/:slug/predictions/football` until Batch 51 and narrowed to the
 * competitions that league played — the subset of football the reader's own coupon
 * happened to cover, which was never what the screen was for. Untied, it has no slug
 * to be addressed at and no league to switch between, so it is a top-level route.
 */
export const FOOTBALL_PATH = '/football';

/** `/leagues/:slug/predictions[/section]`, and the slug-less paths it replaced. */
const PREDICTIONS_PATH = /^(?:\/leagues\/[^/]+)?\/predictions(\/[^/]+)?$/;

/**
 * Where a coupon surface lives for `slug`.
 *
 * A `null` slug means no league is bound yet — a member in none, or one whose
 * leagues are still loading — and yields the slug-less path, which redirects
 * through the bound league as soon as there is one. Every other address names
 * its league, so a coupon can be linked, shared and reopened at the league it
 * came from rather than at whichever one the reader last viewed.
 */
export function predictionsPath(slug: string | null, section: PredictionsSection = ''): string {
  return slug ? `/leagues/${slug}/predictions${section}` : `/predictions${section}`;
}

/** Which coupon surface `pathname` addresses, or `null` when it addresses none. */
function predictionsSection(pathname: string): PredictionsSection | null {
  const match = PREDICTIONS_PATH.exec(pathname);
  if (!match) return null;
  const section = match[1] ?? '';
  return PREDICTIONS_SECTIONS.includes(section) ? (section as PredictionsSection) : null;
}

/**
 * Where `slug`'s equivalent of `pathname` lives — the destination of a league switch.
 *
 * A switch changes which league you are looking at, not what you are looking at: a
 * member comparing two leagues' combined coupons should land on the other league's
 * combined coupon. Until Batch 34 every entry in the switcher pointed at the
 * leaderboard, because the strip was written for that page and kept its destination
 * when Batch 29 mounted it on the four coupon surfaces.
 *
 * Anything that is not a coupon surface falls back to the leaderboard, which is the
 * league's front door — `LeagueHomeRedirect` sends bare `/leagues/:slug` there too.
 * That fallback is deliberate rather than lazy: swapping the slug segment of an
 * arbitrary path would carry a foreign player id into `/leagues/:slug/players/:id`
 * and assume admin of the target on `/admin/*`.
 *
 * Returns a path and never a search string. A gameweek id is league-scoped and
 * `resolve_gameweek` 404s on a foreign one, so carrying `?gw=` across a switch would
 * land the reader on "No coupon this week yet" — `GameweekNav` guards its own label
 * against that id, but nothing guards the query.
 */
export function leagueSwitchPath(slug: string, pathname: string): string {
  const section = predictionsSection(pathname);
  return section === null ? `/leagues/${slug}/leaderboard` : predictionsPath(slug, section);
}

/**
 * The three navigation predicates the bars share.
 *
 * Slug-agnostic on purpose: the Coupon tab highlights for *any* league's coupon,
 * including one the reader has just opened but which the league context has not
 * bound yet — a prefix built from the bound slug would flicker off for that frame.
 * `isLeagueHubPath` has to exclude them explicitly, because the coupon now lives
 * under `/leagues/` too and would otherwise light the Leagues tab as well.
 *
 * `isFootballPath` needs none of that since Batch 51: Football Stats has exactly
 * one address, and no league to be ahead of.
 */
export function isCouponPath(pathname: string): boolean {
  return predictionsSection(pathname) !== null;
}

export function isFootballPath(pathname: string): boolean {
  return pathname === FOOTBALL_PATH;
}

export function isLeagueHubPath(pathname: string): boolean {
  // Tested against the shape rather than the section list, so the addresses Batch 51
  // retired — `/leagues/:slug/predictions/football` and its slug-less twin — do not
  // light the Leagues tab for the frame before their redirect lands.
  if (PREDICTIONS_PATH.test(pathname)) return false;
  return pathname === '/leagues' || pathname.startsWith('/leagues/');
}

/**
 * Forget the cached membership list so the next read of it is the truth.
 *
 * Call after anything that changes which leagues the member is in — joining by
 * invite link or code, creating one. `LeagueContext` holds `['leagues', 'mine']`
 * for a minute, and every coupon surface gates its own query on the `hasLeagues`
 * derived from it, so a join that navigated straight to the new league arrived at
 * "You're not in a league yet" and stayed there until the entry went stale.
 *
 * `removeQueries` rather than `invalidateQueries`: invalidation leaves the stale
 * value in place to be served while the refetch is in flight, which is a list that
 * does not contain the league just joined — the empty state again, only briefly.
 * Dropping the entry outright makes the next read a genuine load, so the screen
 * shows its skeleton and then the coupon.
 */
export function dropStaleMemberships(queryClient: QueryClient): void {
  queryClient.removeQueries({ queryKey: ['leagues', 'mine'] });
}
