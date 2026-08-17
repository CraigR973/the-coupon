import { describe, it, expect } from 'vitest';
import {
  isCouponPath,
  isFootballPath,
  isLeagueHubPath,
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
    expect(predictionsPath('work-league', '/football')).toBe(
      '/leagues/work-league/predictions/football',
    );
  });

  it('falls back to the slug-less path when no league is bound yet', () => {
    expect(predictionsPath(null)).toBe('/predictions');
    expect(predictionsPath(null, '/football')).toBe('/predictions/football');
  });
});

describe('navigation path predicates', () => {
  it('claims any league’s coupon for the Coupon tab, football aside', () => {
    expect(isCouponPath('/leagues/work-league/predictions')).toBe(true);
    expect(isCouponPath('/leagues/the-coupon/predictions/coupon')).toBe(true);
    expect(isCouponPath('/leagues/the-coupon/predictions/results')).toBe(true);
    expect(isCouponPath('/leagues/the-coupon/predictions/football')).toBe(false);
    // The slug-less paths still match, so the tab is lit during the redirect frame.
    expect(isCouponPath('/predictions')).toBe(true);
    expect(isCouponPath('/predictions/results')).toBe(true);
  });

  it('claims football for the Football tab, at either address', () => {
    expect(isFootballPath('/leagues/work-league/predictions/football')).toBe(true);
    expect(isFootballPath('/predictions/football')).toBe(true);
    expect(isFootballPath('/leagues/work-league/predictions')).toBe(false);
  });

  it('keeps the Leagues tab off the coupon, which now lives under /leagues too', () => {
    expect(isLeagueHubPath('/leagues')).toBe(true);
    expect(isLeagueHubPath('/leagues/discover')).toBe(true);
    expect(isLeagueHubPath('/leagues/work-league/leaderboard')).toBe(true);
    expect(isLeagueHubPath('/leagues/work-league/admin/members')).toBe(true);
    expect(isLeagueHubPath('/leagues/work-league/predictions')).toBe(false);
    expect(isLeagueHubPath('/leagues/work-league/predictions/coupon')).toBe(false);
    expect(isLeagueHubPath('/')).toBe(false);
  });

  it('does not mistake a lookalike path for the coupon', () => {
    expect(isCouponPath('/leagues/a/b/predictions')).toBe(false);
    expect(isCouponPath('/predictions/coupon/extra')).toBe(false);
    expect(isCouponPath('/settings')).toBe(false);
  });
});
