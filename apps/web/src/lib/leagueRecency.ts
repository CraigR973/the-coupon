import type { LeagueSummary } from './types';

export const LAST_VIEWED_LEAGUE_KEY = 'wc2026_last_viewed_league';

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
