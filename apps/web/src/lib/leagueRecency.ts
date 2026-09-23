import type { LeagueSummary } from './types';

export const LAST_VIEWED_LEAGUE_KEY = 'coupon_last_viewed_league';

/**
 * Where the league switcher remembers how far it was scrolled. Session-scoped, and
 * declared here rather than in the component so `forgetLeagueContext` below can reach
 * it without importing a component into `lib/`.
 */
export const LEAGUE_SWITCH_SCROLL_KEY = 'coupon_league_switch_scroll';

/**
 * Drop everything this device remembers about which league was being looked at.
 *
 * Batch 143. `clearTokens()` removed the access, refresh and player keys only, so a
 * private league's slug **and name** survived a logout on a shared browser and
 * pre-selected itself for whoever signed in next. The names of the leagues someone
 * belongs to are not public, and on a shared device the next person is by definition
 * not that someone.
 *
 * Safe to call when nothing is stored, and safe when storage is unavailable at all —
 * a private window, blocked site data, or a browser that throws on access.
 */
export function forgetLeagueContext(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(LAST_VIEWED_LEAGUE_KEY);
  } catch {
    /* storage unavailable — nothing to forget */
  }
  try {
    window.sessionStorage.removeItem(LEAGUE_SWITCH_SCROLL_KEY);
  } catch {
    /* as above */
  }
}

export interface LastViewedLeague {
  slug: string;
  name: string;
}

function isValid(value: unknown): value is LastViewedLeague {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return typeof record.slug === 'string' && typeof record.name === 'string';
}

export function getLastViewedLeague(): LastViewedLeague | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(LAST_VIEWED_LEAGUE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    return isValid(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function setLastViewedLeague(league: LastViewedLeague): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(LAST_VIEWED_LEAGUE_KEY, JSON.stringify(league));
}

export function sortLeaguesByLastViewed(
  leagues: LeagueSummary[],
  lastViewedSlug: string | null,
): LeagueSummary[] {
  if (!lastViewedSlug) return leagues;
  const idx = leagues.findIndex((league) => league.slug === lastViewedSlug);
  if (idx <= 0) return leagues;
  return [leagues[idx], ...leagues.slice(0, idx), ...leagues.slice(idx + 1)];
}
