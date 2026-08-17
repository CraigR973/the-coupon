import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useLeague } from '../contexts/LeagueContext';

export interface RouteLeague {
  /** The league this screen is showing: the URL's slug, or the bound one for a slug-less entry. */
  slug: string;
  /** Its display name, once the member's leagues have loaded and the slug is one of them. */
  name: string | undefined;
}

/**
 * The league a screen is addressed at, with the context following the address.
 *
 * The URL is the source of truth: entering `/leagues/:slug/...` binds the league
 * context to that slug, so a slug-less entry afterwards — a bookmark of an old
 * path, a cold start, a notification carrying no url — resumes at the league the
 * member was last actually looking at. `activeSlug` is the default for an address
 * that names no league, not the thing addresses are derived from.
 *
 * `selectLeague` ignores a slug the member is not in, so following a link into
 * someone else's league cannot rebind them to it.
 */
export function useRouteLeague(): RouteLeague {
  const { slug: routeSlug } = useParams<{ slug: string }>();
  const { leagues, activeSlug, selectLeague } = useLeague();
  const slug = routeSlug ?? activeSlug;

  useEffect(() => {
    if (routeSlug) selectLeague(routeSlug);
  }, [routeSlug, selectLeague]);

  return { slug, name: leagues.find((league) => league.slug === slug)?.name };
}
