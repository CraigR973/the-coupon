import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useLeague } from '../contexts/LeagueContext';
import { predictionsPath, type PredictionsSection } from '../lib/leagues';
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
  children,
}: {
  section: PredictionsSection;
  children: ReactNode;
}) {
  const { activeSlug, hasLeagues, isLoading } = useLeague();
  const { search } = useLocation();

  if (isLoading) return <RouteFallback />;
  if (!hasLeagues) return <>{children}</>;
  return <Navigate to={`${predictionsPath(activeSlug, section)}${search}`} replace />;
}
