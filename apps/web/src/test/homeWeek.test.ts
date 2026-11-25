import { describe, it, expect } from 'vitest';
import { homeWeek } from '@/lib/home';
import type { GameCard, LeagueGames } from '@/lib/twoGameTypes';

/**
 * Batch 243 (owner, 25 Nov 2026): Home shows one football week at a time. The week on the
 * card is the earliest one whose results are not final, so Saturday afternoon keeps this
 * week's results on screen while next week's Fantasy, open from Saturday noon, is one line;
 * a legacy round still in play on a league that has switched comes first the same way.
 */
function card(week: string, kind: GameCard['game_kind'], extra: Partial<GameCard> = {}): GameCard {
  return {
    league_id: 'league',
    week_id: week,
    game_id: `${week}-${kind}`,
    game_kind: kind,
    week_label: week,
    week_number: '1',
    destination: `/leagues/league/weeks/${week}/${kind}`,
    opens_at: '2026-11-23T12:00:00Z',
    locks_at: '2026-11-28T12:00:00Z',
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
    server_now: '2026-11-28T13:00:00Z',
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

const locked = { entry_state: 'locked', purpose: 'results' } as const;

describe('homeWeek', () => {
  it("keeps this week while its results are open, with next week's Fantasy as the one line", () => {
    const result = homeWeek(
      league([
        card('2026-11-28', 'fantasy', { ...locked, result: { final: false, weekly_points: 15 } }),
        card('2026-11-28', 'group'),
        card('2026-12-05', 'fantasy'),
        card('2026-12-05', 'group', { entry_state: 'not_open', purpose: 'upcoming' }),
      ]),
    );
    expect(result.week?.weekLabel).toBe('2026-11-28');
    expect(result.week?.fantasy?.game_id).toBe('2026-11-28-fantasy');
    expect(result.week?.group?.game_id).toBe('2026-11-28-group');
    expect(result.nextFantasy?.game_id).toBe('2026-12-05-fantasy');
    expect(result.legacyInPlay).toBe(false);
  });

  it("moves on by itself once a week's results are final", () => {
    const result = homeWeek(
      league([
        card('2026-11-28', 'fantasy', { ...locked, result: { final: true } }),
        card('2026-11-28', 'group', { ...locked, result: { final: true, status: 'lost' } }),
        card('2026-12-05', 'fantasy'),
        card('2026-12-05', 'group', { entry_state: 'not_open', purpose: 'upcoming' }),
      ]),
    );
    expect(result.week?.weekLabel).toBe('2026-12-05');
    expect(result.nextFantasy).toBeNull();
  });

  it('puts a legacy round still in play first, and the first two-game week on the line', () => {
    const result = homeWeek(
      league([card('2026-11-28', 'fantasy')], {
        legacy_rounds: [
          {
            format: 'legacy',
            league_id: 'league',
            week_id: 'legacy-21',
            destination: '/leagues/league/predictions',
            starts_on: '2026-11-21',
            week_number: '16',
            status: 'open',
            locks_at: '2026-11-21T14:30:00Z',
            can_pick: true,
            archived: false,
            picks_open_at: null,
            picked_count: 4,
            my_pick: null,
            fee: null,
          },
        ],
      } as Partial<LeagueGames>),
    );
    expect(result.legacyInPlay).toBe(true);
    expect(result.week).toBeNull();
    expect(result.nextFantasy?.game_id).toBe('2026-11-28-fantasy');
  });

  it('shows no week when every game is archived or cancelled', () => {
    const result = homeWeek(
      league([
        card('2026-11-21', 'fantasy', { ...locked, archived: true, result: { final: true } }),
        card('2026-11-28', 'group', { entry_state: 'cancelled' }),
      ]),
    );
    expect(result.week).toBeNull();
    expect(result.nextFantasy).toBeNull();
  });
});
