import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GamesHome } from '../components/GamesHome';
import { PickFormLine } from '../components/PickFormLine';
import { PlayerProfilePage } from '../pages/PlayerProfilePage';
import { AuthProvider } from '../contexts/AuthContext';
import type { GameCard, LeagueGames, LegacyGameCard } from '../lib/twoGameTypes';
import type { PlayerProfile, SettledPick } from '../lib/types';

const legacy: LegacyGameCard = {
  format: 'legacy', league_id: 'league', week_id: 'w0',
  destination: '/leagues/retained/predictions?gw=w0#coupon',
  starts_on: '2026-11-14', week_number: '1', status: 'open',
  picks_open_at: '2026-11-09T00:00:00Z', locks_at: '2026-11-14T14:30:00Z',
  can_pick: true, archived: false, picked_count: 1,
  my_pick: { id: 'pick', player_id: 'alice', fixture_id: 'fixture', runner_name: 'Legacy Away', market: 'MATCH_ODDS', outcome: 'AWAY', odds: '4.00', result: 'pending', points: null },
  fee: { entry_fee_pence: 100, round_due_pence: 100, owed_pence: 0, owed_rounds: [], credit_pence: 0, adult_confirmed: false, has_payment_link: true, payment_link_url: 'https://synthetic.invalid/pay' },
};
const future: GameCard = {
  league_id: 'league', week_id: 'w1', game_id: 'fantasy', game_kind: 'fantasy',
  week_label: '2026-11-21', week_number: '2',
  destination: '/leagues/league/weeks/w1/fantasy',
  opens_at: '2026-11-14T12:00:00Z', locks_at: '2026-11-21T12:00:00Z',
  entry_state: 'open', purpose: 'entry', archived: false, coverage_state: 'complete', result_version: 0,
  progress: { slots_filled: 0 }, result: { final: false, weekly_points: 0 },
  fee: { league_id: 'league', week_id: 'w1', week_label: '2026-11-21', billing_starts_at: '2026-11-16T00:00:00Z', billing_ends_at: '2026-11-23T00:00:00Z', obligation_pence: 100, amount_owed_pence: 100, paid_through: false, pooled_credit_pence: 0, payment_url: 'https://synthetic.invalid/pay', destination: '/leagues/league/weeks/w1/fantasy#payment', obligations: [] },
};
function home(card: LegacyGameCard = legacy) {
  const league: LeagueGames = { league_id: 'league', slug: 'retained', name: 'Mixed league', two_games_enabled: true, suspended: false, server_now: '2026-11-14T12:05:00Z', games: [future], legacy_rounds: [card], next_cursor: null, next_game_state: 'known', next_game_opens_at: null, season_stats: null, weekly_form: [] };
  return render(<MemoryRouter><GamesHome leagues={[league]} /></MemoryRouter>);
}

beforeEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

describe('owner corrections: mixed Home', () => {
  it('retains paid W0 frozen selection and fee independently beside unpaid open W1', () => {
    home();
    const oldLink = screen.getByRole('link', { name: 'Legacy round · 14 Nov' });
    const old = within(oldLink.closest('li')!);
    const nextLink = screen.getByRole('link', { name: 'Fantasy · 21 Nov' });
    const next = within(nextLink.closest('li')!);
    expect(oldLink).toHaveAttribute('href', legacy.destination);
    expect(nextLink).toHaveAttribute('href', future.destination);
    expect(old.getByText(/Your pick: Legacy Away.*Frozen odds 4.00/)).toBeVisible();
    expect(old.getByText('£1.00 per legacy round · Paid through this round')).toBeVisible();
    expect(old.getByText('Entry open')).toBeVisible();
    expect(old.getByText('Locks Sat 14 Nov 14:30 London.')).toBeVisible();
    expect(next.getByText('Entry open')).toBeVisible();
    expect(next.getByRole('link', { name: '£1.00 owed through this week' })).toHaveAttribute('href', future.fee.destination);
  });
  it('labels a scheduled legacy round before its opening without claiming it is locked', () => {
    home({ ...legacy, status: 'scheduled', can_pick: false, picks_open_at: '2026-11-14T13:00:00Z' });
    const old = within(screen.getByRole('link', { name: 'Legacy round · 14 Nov' }).closest('li')!);
    expect(old.getByText('Entry has not opened')).toBeVisible();
    expect(old.getByText('Opens Sat 14 Nov 13:00 London.')).toBeVisible();
    expect(old.queryByText('Locked results')).toBeNull();
  });
  it('keeps unpaid legacy arrears separate from the future weekly fee', () => {
    home({ ...legacy, fee: { ...legacy.fee!, owed_pence: 250 } });
    expect(screen.getByText('£1.00 per legacy round · £2.50 owed through this round')).toBeVisible();
    expect(screen.getByText('£1.00 owed through this week')).toBeVisible();
  });
  it('preserves a fee-free locked legacy round without inventing a payment', () => {
    home({ ...legacy, status: 'locked', can_pick: false, fee: null });
    expect(screen.getByText('No legacy entry fee required.')).toBeVisible();
    expect(screen.getByText('Locked results')).toBeVisible();
  });
});

describe('owner corrections: Fantasy weekly form', () => {
  it('shows one weekly points aggregate rather than a legacy win marker', () => {
    render(<PickFormLine player="Alice" form={[{ gameweek_id: 'w1', starts_on: '2026-11-21', status: 'scored', points: 132, format: 'two_game', game_kind: 'fantasy', slots_filled: 6, destination: future.destination }, { gameweek_id: 'w0', starts_on: '2026-11-14', status: 'won', points: 20 }]} />);
    const form = screen.getByTestId('pick-form');
    expect(form.textContent).toBe('W20F132');
    expect(form).toHaveAccessibleName("Alice's last rounds, oldest first: won 20 points, Fantasy week scored 132 points");
    expect(within(form).queryByRole('link')).toBeNull();
  });
  it('keeps no-entry, all-void and scored-zero weeks distinct', () => {
    render(<PickFormLine form={['scored', 'all_void', 'no_entry'].map((status, i) => ({ gameweek_id: `w${i}`, starts_on: '2026-11-21', status: status as 'scored' | 'all_void' | 'no_entry', points: 0 }))} />);
    expect(screen.getByTestId('pick-form').textContent).toBe('NVF');
    expect(screen.getByTestId('pick-form')).toHaveAccessibleName('Last rounds, oldest first: Fantasy week no entry, Fantasy week all void, Fantasy week scored 0 points');
  });
});

const leg: SettledPick = { gameweek_id: 'w1', starts_on: '2026-11-21', fixture_id: 'fx1', home: 'Fantasy Home', away: 'Fantasy Away', competition: 'Synthetic', market: 'MATCH_ODDS', outcome: 'HOME', runner_name: 'Fantasy Home', odds: 2.15, frozen_odds: '2.1500', status: 'won', points_awarded: 22, format: 'two_game', game_kind: 'fantasy', game_id: 'fantasy', slot: 1, destination: future.destination };
function profile(history: SettledPick[]) {
  localStorage.setItem('coupon_access', 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSIsImV4cCI6OTk5OTk5OTk5OX0.fake');
  localStorage.setItem('coupon_player', JSON.stringify({ id: 'alice', displayName: 'Alice', role: 'player', timezone: 'Europe/London' }));
  const body: PlayerProfile = { player_id: 'alice', display_name: 'Alice', total_points: history.reduce((n, pick) => n + (pick.points_awarded ?? 0), 0), picks_played: history.length, picks_won: history.length, rank: 1, win_rate_pct: 100, history };
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => body })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/leagues/retained/players/alice']}><AuthProvider><Routes><Route path="/leagues/:slug/players/:playerId" element={<PlayerProfilePage />} /></Routes></AuthProvider></MemoryRouter></QueryClientProvider>);
}
describe('owner corrections: profile history', () => {
  it('shows the real winning leg behind Fantasy-only points and counts', async () => {
    profile([leg]);
    const history = await screen.findByTestId('profile-history');
    expect(within(screen.getByTestId('profile-stats')).getByText('22')).toBeVisible();
    expect(within(screen.getByTestId('profile-stats')).getByText('1/1')).toBeVisible();
    expect(within(history).getByTestId('history-fx1')).toHaveTextContent('Fantasy Home');
    expect(within(history).getByTestId('history-fx1')).toHaveTextContent('2.15');
    expect(within(history).getByRole('link', { name: 'Fantasy slot 1 · 21 Nov 2026' })).toHaveAttribute('href', future.destination);
    expect(screen.queryByText('No settled picks yet')).toBeNull();
  });
  it('retains legacy entries and their exact route beside Fantasy legs', async () => {
    profile([leg, { ...leg, gameweek_id: 'w0', starts_on: '2026-11-14', fixture_id: 'fx0', format: 'legacy', game_kind: 'legacy', game_id: null, slot: null, frozen_odds: null, odds: 4, points_awarded: 40, destination: legacy.destination }]);
    const history = await screen.findByTestId('profile-history');
    expect(within(history).getAllByRole('listitem')).toHaveLength(2);
    expect(within(history).getByTestId('history-fx0')).toHaveTextContent('4.00');
    expect(within(history).getByRole('link', { name: 'Legacy round · 14 Nov 2026' })).toHaveAttribute('href', legacy.destination);
    expect(within(history).getByRole('link', { name: 'Fantasy slot 1 · 21 Nov 2026' })).toHaveAttribute('href', future.destination);
  });
});
