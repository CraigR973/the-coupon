import { describe, it, expect } from 'vitest';
import { lastTwoGameWeek, twoGameEntryFacts } from '@/lib/home';
import type { GameCard, LeagueGames } from '@/lib/twoGameTypes';

/**
 * Batch 239. A two-game league's home card answers from its own games, because the
 * cross-league summary reads legacy rounds only. These pin what counts as waiting on the
 * member, and which week is the last result.
 */
const NOW = Date.parse('2026-11-27T12:00:00Z');

function card(
  week: string,
  kind: GameCard['game_kind'],
  extra: Partial<GameCard> = {},
): GameCard {
  return {
    league_id: 'league',
    week_id: week,
    game_id: `${week}-${kind}`,
    game_kind: kind,
    week_label: week,
    week_number: '1',
    destination: `/leagues/league/weeks/${week}/${kind}`,
    opens_at: '2026-11-23T12:00:00Z',
    locks_at: kind === 'fantasy' ? '2026-11-28T12:00:00Z' : '2026-11-28T14:30:00Z',
    entry_state: 'open',
    purpose: 'entry',
    archived: false,
    coverage_state: 'complete',
    result_version: 0,
    progress: {},
    result: { final: false },
    fee: {
      league_id: 'league',
      week_id: week,
      week_label: week,
      billing_starts_at: '2026-11-23T00:00:00Z',
      billing_ends_at: '2026-11-30T00:00:00Z',
      obligation_pence: 100,
      amount_owed_pence: 0,
      paid_through: true,
      pooled_credit_pence: 0,
      payment_url: null,
      destination: `/leagues/league/weeks/${week}/${kind}#payment`,
      obligations: [],
    },
    ...extra,
  };
}

function league(games: GameCard[], extra: Partial<LeagueGames> = {}): LeagueGames {
  return {
    league_id: 'league',
    slug: 'league',
    name: 'League',
    two_games_enabled: true,
    suspended: false,
    server_now: new Date(NOW).toISOString(),
    games,
    legacy_rounds: [],
    next_cursor: null,
    next_game_state: 'known',
    next_game_opens_at: null,
    season_stats: null,
    weekly_form: [],
    ...extra,
  };
}

const PICK = {
  league_id: 'league',
  week_id: '2026-11-28',
  game_id: '2026-11-28-group',
  game_kind: 'group' as const,
  revision: 1,
  operation_id: null,
  pick: {
    id: 'pick',
    fixture_id: 'fixture',
    player_id: 'alice',
    market: 'MATCH_ODDS',
    outcome: 'HOME',
    runner_name: 'Hibernian',
    revision: 1,
    operation_id: 'op',
    result: 'pending',
  },
};

describe('twoGameEntryFacts', () => {
  it('waits on a missing group pick and on any empty fantasy slot, soonest lock first', () => {
    const facts = twoGameEntryFacts(
      league([
        card('2026-11-28', 'group'),
        card('2026-11-28', 'fantasy', { progress: { slots_filled: 5 } }),
      ]),
      NOW,
    );
    expect(facts.needs.map((entry) => entry.destination)).toEqual([
      '/leagues/league/weeks/2026-11-28/fantasy',
      '/leagues/league/weeks/2026-11-28/group',
    ]);
    expect(facts.ready).toEqual([]);
  });

  it('counts a group pick and six fantasy slots as made', () => {
    const facts = twoGameEntryFacts(
      league([
        card('2026-11-28', 'group', { my_entry: PICK }),
        card('2026-11-28', 'fantasy', { progress: { slots_filled: 6 } }),
      ]),
      NOW,
    );
    expect(facts.needs).toEqual([]);
    expect(facts.ready).toHaveLength(2);
  });

  it('stops asking at the lock on this device’s clock, and calls the week in progress', () => {
    const facts = twoGameEntryFacts(
      league([card('2026-11-28', 'group'), card('2026-11-28', 'fantasy')]),
      Date.parse('2026-11-28T15:00:00Z'),
    );
    expect(facts.needs).toEqual([]);
    expect(facts.inProgress).toBe(true);
  });

  it('asks nothing of a suspended league, and points the next opening at its entry', () => {
    const next = card('2026-12-05', 'fantasy', {
      opens_at: '2026-11-30T12:00:00Z',
      locks_at: '2026-12-05T12:00:00Z',
      entry_state: 'not_open',
      purpose: 'upcoming',
    });
    const facts = twoGameEntryFacts(
      league([card('2026-11-28', 'group', { entry_state: 'suspended' }), next], {
        suspended: true,
        next_game_opens_at: next.opens_at,
      }),
      NOW,
    );
    expect(facts.needs).toEqual([]);
    expect(facts.inProgress).toBe(false);
    expect(facts.next).toEqual({
      opensAt: '2026-11-30T12:00:00Z',
      destination: '/leagues/league/weeks/2026-12-05/fantasy',
    });
  });
});

describe('lastTwoGameWeek', () => {
  const final = { final: true };
  it('is the latest week whose games are all final, skipping a provisional one', () => {
    const week = lastTwoGameWeek(
      league([
        card('2026-11-21', 'group', { archived: true, result: { ...final, status: 'won' } }),
        card('2026-11-21', 'fantasy', { archived: true, result: { ...final, weekly_points: 22 } }),
        card('2026-11-28', 'group', { result: { ...final, status: 'lost' } }),
        card('2026-11-28', 'fantasy', { result: { final: false, provisional: true } }),
      ]),
    );
    expect(week?.weekLabel).toBe('2026-11-21');
    expect(week?.group?.result.status).toBe('won');
    expect(week?.fantasy?.result.weekly_points).toBe(22);
  });

  it('counts a week whose other game was cancelled, and is null before any week is final', () => {
    const cancelled = card('2026-11-28', 'group', { entry_state: 'cancelled' });
    const week = lastTwoGameWeek(
      league([cancelled, card('2026-11-28', 'fantasy', { result: final })]),
    );
    expect(week?.weekLabel).toBe('2026-11-28');
    expect(week?.group).toBeNull();
    expect(lastTwoGameWeek(league([card('2026-11-28', 'group')]))).toBeNull();
  });
});
