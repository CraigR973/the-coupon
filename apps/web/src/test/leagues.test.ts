import { describe, it, expect } from 'vitest';
import {
  FOOTBALL_PATH,
  isCouponPath,
  isFootballPath,
  isLeagueHubPath,
  leagueSwitchPath,
  predictionsPath,
  privacyLabel,
  PRIVACY_LABELS,
} from '@/lib/leagues';

describe('privacyLabel helper', () => {
  it('returns "Public" for public_open', () => {
    expect(privacyLabel('public_open')).toBe('Public');
  });

  it('returns "Public · request to join" for public_request', () => {
    expect(privacyLabel('public_request')).toBe('Public · request to join');
  });

  it('returns "Private" for private', () => {
    expect(privacyLabel('private')).toBe('Private');
  });

  it('returns empty string for unknown / stale values (open, request)', () => {
    expect(privacyLabel('open')).toBe('');
    expect(privacyLabel('request')).toBe('');
    expect(privacyLabel('')).toBe('');
  });

  it('PRIVACY_LABELS covers all three real enum values', () => {
    const keys = Object.keys(PRIVACY_LABELS);
    expect(keys).toContain('public_open');
    expect(keys).toContain('public_request');
    expect(keys).toContain('private');
    expect(keys).toHaveLength(3);
  });
});

describe('predictionsPath', () => {
  it('names the league in every coupon address', () => {
    expect(predictionsPath('work-league')).toBe('/leagues/work-league/predictions');
    expect(predictionsPath('work-league', '/coupon')).toBe(
      '/leagues/work-league/predictions/coupon',
    );
    expect(predictionsPath('work-league', '/results')).toBe(
      '/leagues/work-league/predictions/results',
    );
  });

  it('falls back to the slug-less path when no league is bound yet', () => {
    expect(predictionsPath(null)).toBe('/predictions');
    expect(predictionsPath(null, '/coupon')).toBe('/predictions/coupon');
  });
});

describe('leagueSwitchPath', () => {
  it('keeps the reader on the coupon surface they are already on', () => {
    expect(leagueSwitchPath('friends', '/leagues/the-coupon/predictions')).toBe(
      '/leagues/friends/predictions',
    );
    expect(leagueSwitchPath('friends', '/leagues/the-coupon/predictions/coupon')).toBe(
      '/leagues/friends/predictions/coupon',
    );
    expect(leagueSwitchPath('friends', '/leagues/the-coupon/predictions/results')).toBe(
      '/leagues/friends/predictions/results',
    );
  });

  it('sends a switch from Football Stats to the front door — it has no per-league twin', () => {
    // Batch 51: the strip does not render there any more, but the helper is the one
    // place that decides, and a caller mounting it on `/football` must not be handed
    // `/leagues/friends/football`, which is not a route.
    expect(leagueSwitchPath('friends', FOOTBALL_PATH)).toBe('/leagues/friends/leaderboard');
  });

  it('sends every other surface to the target league’s front door', () => {
    expect(leagueSwitchPath('friends', '/leagues/the-coupon/leaderboard')).toBe(
      '/leagues/friends/leaderboard',
    );
    // Not the equivalent admin page: admin of one league is not admin of another.
    expect(leagueSwitchPath('friends', '/leagues/the-coupon/admin/settings')).toBe(
      '/leagues/friends/leaderboard',
    );
    // Not the equivalent player page either: the id belongs to the league being left.
    expect(leagueSwitchPath('friends', '/leagues/the-coupon/players/p1')).toBe(
      '/leagues/friends/leaderboard',
    );
  });

  it('switches correctly from a slug-less coupon path mid-redirect', () => {
    expect(leagueSwitchPath('friends', '/predictions/coupon')).toBe(
      '/leagues/friends/predictions/coupon',
    );
  });

  it('never returns a query string', () => {
    // A gameweek id is league-scoped and `resolve_gameweek` 404s on a foreign one, so
    // carrying `?gw=` across a switch would land on the empty state. The pathname is
    // all this takes, so there is nothing for a search string to leak through.
    expect(leagueSwitchPath('friends', '/leagues/the-coupon/predictions/coupon')).not.toContain(
      '?',
    );
  });
});

describe('navigation path predicates', () => {
  it('claims any league’s coupon for the Coupon tab', () => {
    expect(isCouponPath('/leagues/work-league/predictions')).toBe(true);
    expect(isCouponPath('/leagues/the-coupon/predictions/coupon')).toBe(true);
    expect(isCouponPath('/leagues/the-coupon/predictions/results')).toBe(true);
    // The slug-less paths still match, so the tab is lit during the redirect frame.
    expect(isCouponPath('/predictions')).toBe(true);
    expect(isCouponPath('/predictions/results')).toBe(true);
  });

  it('claims the one slug-less address Football Stats now has', () => {
    expect(isFootballPath(FOOTBALL_PATH)).toBe(true);
    expect(isFootballPath('/leagues/work-league/predictions')).toBe(false);
    // Batch 51 retired both of these; they redirect, and light no tab on the way.
    expect(isFootballPath('/leagues/work-league/predictions/football')).toBe(false);
    expect(isFootballPath('/predictions/football')).toBe(false);
  });

  it('leaves the Coupon tab dark on the football addresses it no longer owns', () => {
    expect(isCouponPath('/leagues/the-coupon/predictions/football')).toBe(false);
    expect(isCouponPath('/predictions/football')).toBe(false);
  });

  it('keeps the Leagues tab off the coupon, which now lives under /leagues too', () => {
    expect(isLeagueHubPath('/leagues')).toBe(true);
    expect(isLeagueHubPath('/leagues/discover')).toBe(true);
    expect(isLeagueHubPath('/leagues/work-league/leaderboard')).toBe(true);
    expect(isLeagueHubPath('/leagues/work-league/admin/members')).toBe(true);
    expect(isLeagueHubPath('/leagues/work-league/predictions')).toBe(false);
    expect(isLeagueHubPath('/leagues/work-league/predictions/coupon')).toBe(false);
    // Retired, and still not the Leagues tab's for the frame before it redirects.
    expect(isLeagueHubPath('/leagues/work-league/predictions/football')).toBe(false);
    expect(isLeagueHubPath(FOOTBALL_PATH)).toBe(false);
    expect(isLeagueHubPath('/')).toBe(false);
  });

  it('does not mistake a lookalike path for the coupon', () => {
    expect(isCouponPath('/leagues/a/b/predictions')).toBe(false);
    expect(isCouponPath('/predictions/coupon/extra')).toBe(false);
    expect(isCouponPath('/settings')).toBe(false);
  });
});
