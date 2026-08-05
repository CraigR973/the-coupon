// ---------------------------------------------------------------------------
// The Coupon — API response types.
//
// The picks / gameweek / coupon / standings routers serialise **snake_case**
// (no camelCase alias generator), so these interfaces mirror the wire shape
// verbatim. See apps/api/src/routers/{gameweek,picks,coupon}.py.
// ---------------------------------------------------------------------------

// ── Enums (values mirror the odds-provider / Pick model codes) ─────────────

export type PickMarket = 'MATCH_ODDS' | 'BOTH_TEAMS_TO_SCORE';
export type PickOutcome = 'HOME' | 'DRAW' | 'AWAY' | 'YES' | 'NO';
export type GameweekStatus = 'open' | 'locked' | 'settled';
export type PickStatus = 'pending' | 'won' | 'lost' | 'void';
/** How a member reads prices. Display only — scoring is always decimal. */
export type OddsFormat = 'decimal' | 'fractional';
/**
 * How much of a fixture one claim takes. `selection` is the original rule;
 * `fixture` makes claiming any market on a game take the whole game.
 */
export type PickScope = 'selection' | 'fixture';

// ── Gameweek slate — GET /leagues/{slug}/gameweek/current ──────────────────

export interface SelectionOption {
  market: PickMarket;
  outcome: PickOutcome;
  runner_name: string;
  odds: number;
  /** Who holds this selection in the league (null = still available). */
  taken_by_player_id: string | null;
  taken_by_name: string | null;
  /** True when the caller is the holder. */
  mine: boolean;
}

export interface FixtureSlate {
  fixture_id: string;
  provider_event_id: string;
  home: string;
  away: string;
  competition: string;
  kickoff_utc: string;
  selections: SelectionOption[];
  /**
   * Members holding any selection on this fixture — the fixture-level "already
   * picked" marker. A list rather than a flag because the selection-level rule
   * lets several members share one game.
   */
  taken_by_names: string[];
  /** True when the caller holds a selection on this fixture. */
  mine: boolean;
}

/** One member's standing on a gameweek, including those yet to pick. */
export interface GameweekMember {
  player_id: string;
  display_name: string;
  has_picked: boolean;
  fixture_id: string | null;
  home: string | null;
  away: string | null;
  market: PickMarket | null;
  outcome: PickOutcome | null;
  runner_name: string | null;
  odds: number | null;
}

/** One row of the season's history — GET /leagues/{slug}/gameweeks. */
export interface GameweekSummary {
  gameweek_id: string;
  saturday_date: string; // ISO date (yyyy-mm-dd)
  status: GameweekStatus;
  locks_at_utc: string;
  fixture_count: number;
  /** Picks made in *this* league, so the same week reads differently per league. */
  pick_count: number;
}

export interface GameweekSlate {
  gameweek_id: string;
  saturday_date: string; // ISO date (yyyy-mm-dd)
  status: GameweekStatus;
  locks_at_utc: string;
  fixtures: FixtureSlate[];
  members: GameweekMember[];
  members_missing_picks: number;
  /** The league's claim rule, so the UI can explain why a whole game is gone. */
  pick_scope: PickScope;
}

// ── Pick — POST /leagues/{slug}/picks · GET .../gameweeks/{id}/pick ─────────

export interface SubmitPickBody {
  fixture_id: string;
  market: PickMarket;
  outcome: PickOutcome;
}

export interface PickResponse {
  id: string;
  league_id: string;
  gameweek_id: string;
  fixture_id: string;
  home: string;
  away: string;
  competition: string;
  market: PickMarket;
  outcome: PickOutcome;
  runner_name: string;
  odds: number;
  status: PickStatus;
  points_awarded: number | null;
}

// ── Combined coupon — GET /leagues/{slug}/coupon ───────────────────────────

export interface CouponLeg {
  player_id: string;
  player_name: string;
  fixture_id: string;
  home: string;
  away: string;
  competition: string;
  market: PickMarket;
  outcome: PickOutcome;
  runner_name: string;
  odds: number;
  status: PickStatus;
}

export interface Coupon {
  gameweek_id: string;
  status: GameweekStatus;
  leg_count: number;
  combined_odds: number;
  legs: CouponLeg[];
  /** null until the gameweek settles, then true only if every leg won. */
  all_won: boolean | null;
}

// ── Standings — GET /leagues/{slug}/standings ──────────────────────────────

export interface Standing {
  player_id: string;
  display_name: string;
  total_points: number;
  picks_played: number;
  picks_won: number;
  rank: number;
}

// ---------------------------------------------------------------------------
// Leagues (the social "leaderboard" layer — kept from the shared spine).
// ---------------------------------------------------------------------------

export interface LeagueSummary {
  slug: string;
  name: string;
  description: string | null;
  privacy: 'public_open' | 'public_request' | 'private';
  member_count: number;
  max_members: number | null;
  pick_scope: PickScope;
  created_at: string;
}

/** Shape returned by GET /api/v1/leagues/{slug} — includes member list with roles. */
export interface LeagueDetail extends LeagueSummary {
  id: string;
  created_by: string;
  join_code: string | null;
  members: Array<{
    id: string;
    display_name: string;
    role: 'player' | 'admin';
    joined_at: string;
    avatar_url?: string | null;
  }> | null;
}

export interface LeagueMember {
  id: string;
  display_name: string;
  role: 'player' | 'admin';
  joined_at: string;
  avatar_url?: string | null;
}

export interface JoinRequest {
  id: string;
  player_id: string;
  display_name: string;
  requested_at: string;
  status: 'pending' | 'approved' | 'rejected';
  note: string | null;
}

export interface LeagueInvite {
  id: string;
  token: string;
  created_by_display_name: string;
  created_at: string;
  expires_at: string | null;
  used_at: string | null;
}
