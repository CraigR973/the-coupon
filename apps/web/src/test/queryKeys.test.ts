/**
 * Batch 165 — what a cached thing is called, and the two bugs that came of not deciding.
 *
 * These are about key *identity*, which React Query treats structurally: two keys are the
 * same entry if they serialise the same, and an invalidation matches a query when it is a
 * prefix of that query's key. Both bugs below are invisible at runtime — a key that
 * matches nothing clears nothing and says nothing about it.
 */

import { describe, it, expect } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { keys } from '@/lib/queryKeys';

function hash(key: readonly unknown[]): string {
  return JSON.stringify(key);
}

describe('the standings key', () => {
  it('gives two seasons two entries', () => {
    // The correctness bug: a key that omits the season it fetched means last season's
    // table is served for this season, from cache, with nothing to indicate it.
    expect(hash(keys.standings.forSeason('the-coupon', 2025))).not.toBe(
      hash(keys.standings.forSeason('the-coupon', 2026)),
    );
  });

  it('separates "the current season" from any named one', () => {
    // `null` is a different *request* — the URL carries no season parameter and the API
    // chooses — so it must be a different entry, not an absent one.
    const current = hash(keys.standings.forSeason('the-coupon', null));
    expect(current).not.toBe(hash(keys.standings.forSeason('the-coupon', 2026)));
    expect(current).not.toBe(hash(keys.standings.all('the-coupon')));
  });

  it('keeps two leagues apart', () => {
    expect(hash(keys.standings.forSeason('the-coupon', 2026))).not.toBe(
      hash(keys.standings.forSeason('work-league', 2026)),
    );
  });

  it('clears every season of a league from one invalidation', async () => {
    // The property that makes `standings.all` usable after a membership change: React
    // Query matches a shorter key as a prefix, so this must actually reach the entries.
    const client = new QueryClient();
    client.setQueryData(keys.standings.forSeason('the-coupon', 2025), ['a']);
    client.setQueryData(keys.standings.forSeason('the-coupon', 2026), ['b']);
    client.setQueryData(keys.standings.forSeason('work-league', 2026), ['c']);

    await client.invalidateQueries({ queryKey: keys.standings.all('the-coupon') });

    const stale = client
      .getQueryCache()
      .getAll()
      .filter((q) => q.isStale())
      .map((q) => hash(q.queryKey));

    expect(stale).toContain(hash(keys.standings.forSeason('the-coupon', 2025)));
    expect(stale).toContain(hash(keys.standings.forSeason('the-coupon', 2026)));
    expect(stale).not.toContain(hash(keys.standings.forSeason('work-league', 2026)));
  });

  it('is the key the leave-league flow actually invalidates', async () => {
    // The bug this batch found: `LeagueActionsMenu` cleared `['leaderboard', slug]`, and
    // no query has ever been keyed `leaderboard`. It matched nothing, silently, leaving a
    // member looking at the table of a league they had just left. Asserted as "the key
    // the menu uses reaches the key the pages use", because that is the relationship that
    // broke — not the spelling of either one.
    const client = new QueryClient();
    client.setQueryData(keys.standings.forSeason('the-coupon', null), ['table']);

    await client.invalidateQueries({ queryKey: ['leaderboard', 'the-coupon'] });
    expect(
      client.getQueryCache().getAll().every((q) => !q.isStale()),
      'the old key matched something — this test no longer proves anything',
    ).toBe(true);

    await client.invalidateQueries({ queryKey: keys.standings.all('the-coupon') });
    expect(client.getQueryCache().getAll().some((q) => q.isStale())).toBe(true);
  });
});

describe('the league keys', () => {
  it('nests competitions under the league so one invalidation covers both', async () => {
    const client = new QueryClient();
    client.setQueryData(keys.league.detail('the-coupon'), { slug: 'the-coupon' });
    client.setQueryData(keys.league.competitions('the-coupon'), []);

    await client.invalidateQueries({ queryKey: keys.league.detail('the-coupon') });

    expect(client.getQueryCache().getAll().every((q) => q.isStale())).toBe(true);
  });

  it('keeps members and seasons on their own roots, as the code still has them', () => {
    // Stated rather than assumed: `league.detail` is *not* a prefix of these two today.
    // A later batch can bring them under it; until then, anything invalidating after a
    // membership change has to name them, and `LeagueActionsMenu` does.
    expect(hash(keys.league.members('x')).startsWith('["league","x"')).toBe(false);
    expect(hash(keys.league.seasons('x')).startsWith('["league","x"')).toBe(false);
  });
});
