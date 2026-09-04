import type { ReactNode } from 'react';
import { Navigate, useLocation, useParams } from 'react-router-dom';
import { useLeague } from '../contexts/LeagueContext';
import { COUPON_SECTION_HASH, predictionsPath, type PredictionsSection } from '../lib/leagues';
import { RouteFallback } from './RouteFallback';

/**
 * Keeps the slug-less coupon paths working by bouncing them through the bound
 * league, carrying the query string so a `?gw=` link survives the move.
 *
 * Every link, bookmark and reminder minted before Batch 30 points at one of these,
 * so they have to keep landing correctly — and they wait for the member's leagues
 * rather than redirecting at `DEFAULT_LEAGUE_SLUG`, which would send most readers
 * to a league they are not in before bouncing them again.
 *
 * A member in no league has no league URL to be sent to, so the surface answers
 * where it stands rather than at an address naming a league they do not play.
 */
export function PredictionsRedirect({
  section,
  hash,
  children,
}: {
  section: PredictionsSection;
  /** A fragment to land on, for a path whose replacement is a section of a page. */
  hash?: string;
  children: ReactNode;
}) {
  const { activeSlug, hasLeagues, isLoading } = useLeague();
  const location = useLocation();

  if (isLoading) return <RouteFallback />;
  if (!hasLeagues) return <>{children}</>;
  const fragment = location.hash || hash || '';
  return (
    <Navigate
      to={`${predictionsPath(activeSlug, section)}${location.search}${fragment}`}
      replace
    />
  );
}

/**
 * The combined coupon's old address, which is a section of the current round now.
 *
 * Batch 105 merged the two screens; this is the half of that merge members can see from
 * the outside. A saved link, a shared URL and every notification tap minted before the
 * merge point at `/leagues/:slug/predictions/coupon`, and each of them was asking for the
 * fold, the frozen combined price and the copy control — so they land on exactly that,
 * at `#coupon`, with `?gw=` intact so a link to *that* week still opens that week.
 *
 * An incoming fragment wins over the default, because a link that already names a section
 * of the page knows better than this redirect does.
 */
export function CombinedCouponRedirect() {
  const { slug } = useParams<{ slug: string }>();
  const location = useLocation();
  const fragment = location.hash || COUPON_SECTION_HASH;
  return (
    <Navigate
      to={`${predictionsPath(slug ?? null)}${location.search}${fragment}`}
      replace
    />
  );
}
