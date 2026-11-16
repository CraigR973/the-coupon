export type GameKind = "group" | "fantasy";
export interface GameTarget {
  league_id: string;
  week_id: string;
  game_kind: GameKind;
}
export interface WeekFee {
  league_id: string;
  week_id: string;
  week_label: string;
  billing_starts_at: string;
  billing_ends_at: string;
  obligation_pence: number;
  amount_owed_pence: number;
  paid_through: boolean;
  pooled_credit_pence: number;
  payment_url: string | null;
  destination: string;
  obligations: {
    week_id: string | null;
    week_label: string | null;
    remaining_pence: number;
  }[];
}
export interface GamePick {
  id: string;
  fixture_id: string;
  player_id: string;
  market: string;
  outcome: string;
  runner_name: string;
  revision: number;
  operation_id: string;
  result: string;
  frozen_odds?: string;
  points?: number;
}
export interface GameEntry {
  league_id: string;
  week_id: string;
  game_id: string;
  game_kind: GameKind;
  revision: number;
  operation_id: string | null;
  pick: GamePick | null;
  slot?: number;
}
export interface GameCard extends GameTarget {
  game_id: string;
  week_label: string;
  week_number: string;
  destination: string;
  opens_at: string;
  locks_at: string;
  entry_state: string;
  purpose: string;
  archived: boolean;
  fee: WeekFee;
  coverage_state: string;
  result_version: number;
  progress: {
    picked_count?: number;
    member_count?: number;
    missing_contributors?: number;
    slots_filled?: number;
  };
  result: {
    status?: string;
    entry_result?: string;
    final: boolean;
    provisional?: boolean;
    weekly_points?: number;
  };
  my_entry?: GameEntry;
  slots?: GameEntry[];
}
export interface LegacyGameCard {
  format: "legacy";
  league_id: string;
  week_id: string;
  destination: string;
  starts_on: string;
  week_number: string;
  status: string;
  locks_at: string;
  can_pick: boolean;
  archived: boolean;
}
export interface LeagueGames {
  league_id: string;
  slug: string;
  name: string;
  two_games_enabled: boolean;
  suspended: boolean;
  server_now: string;
  games: GameCard[];
  legacy_rounds: LegacyGameCard[];
  next_cursor: string | null;
  next_game_state: "known" | "pending";
  next_game_opens_at: string | null;
  season_stats: { total_points: number; rank: number } | null;
  weekly_form: {
    week_id: string;
    week_label: string;
    format: string;
    destination: string;
    status: string;
    weekly_points: number;
  }[];
}
export interface GroupFixture {
  fixture_id: string;
  home: string;
  away: string;
  competition_id: string;
  kickoff_at: string;
  status: string;
  eligible: boolean;
  allowed_markets: { market: string; outcomes: string[] }[];
  claim: {
    player_id: string;
    display_name: string;
    market: string;
    outcome: string;
    runner_name: string;
    result: string;
  } | null;
}
export interface GroupGame extends GameTarget {
  game_id: string;
  week_label: string;
  week_number: string;
  destination: string;
  opens_at: string;
  locks_at: string;
  entry_state: string;
  coverage_state: string;
  fixtures: GroupFixture[];
  my_entries: GamePick[];
  progress: { picked_count: number; member_count: number; all_picked: boolean };
  result: { status: string; final: boolean };
  fee: WeekFee;
}
export const gamePath = (target: GameTarget) =>
  `/api/v1/leagues/${target.league_id}/weeks/${target.week_id}/games/${target.game_kind}`;
export const gameQueryKey = (member: string, target: GameTarget) =>
  [
    "two-games",
    member,
    target.league_id,
    target.week_id,
    target.game_kind,
  ] as const;
