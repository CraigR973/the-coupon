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
  /** The odds provider's stable competition slug, matching fixtures.competition_id. */
  competition_id: string;
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
  /**
   * Both clubs' table position and recent form, or absent when the football
   * source has nothing for this game (Batch 16). Optional throughout: form is an
   * enhancement, not a precondition for picking, so every consumer has to render
   * the fixture without it.
   */
  context?: FixtureContext | null;
}

// ── Football data — tables, results and form (Batch 16) ────────────────────
//
// A second provider from the odds one: odds-api.io publishes no standings. All of
// this is read from the API's own `teams` / `matches` / `standings` tables, which a
// scheduled job fills — no screen here can cause an upstream request.

/** One match from a club's point of view — the letters a form line is made of. */
export type FormResult = 'W' | 'D' | 'L';

export interface FormMatch {
  match_id: string;
  kickoff_utc: string;
  opponent: string;
  home: boolean;
  goals_for: number;
  goals_against: number;
  result: FormResult;
}

/** A club's table line and recent form, as shown beside a fixture. */
export interface TeamContext {
  team_id: string;
  name: string;
  /** Null when the competition has no stored table — a cup, or a season not yet ingested. */
  position: number | null;
  played: number | null;
  points: number | null;
  goal_difference: number | null;
  /** Most recent **last**, e.g. `"LWWDW"` — the order every football table prints. */
  form: string;
  recent: FormMatch[];
}

/** Both clubs' context for one fixture. Either side may be unresolved. */
export interface FixtureContext {
  home: TeamContext | null;
  away: TeamContext | null;
}

export interface TableEntry {
  position: number;
  team_id: string;
  team: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
  form: string;
}

/** One competition's table — GET /leagues/{slug}/football/tables. */
export interface CompetitionTable {
  competition_id: string;
  competition: string;
  season: number;
  /** When this table was last ingested. Shown as "as of": stored data, not live. */
  updated_at: string | null;
  rows: TableEntry[];
}

/** One finished match — GET /leagues/{slug}/football/results. */
export interface ResultEntry {
  match_id: string;
  competition_id: string;
  competition: string;
  kickoff_utc: string;
  home: string;
  away: string;
  home_goals: number;
  away_goals: number;
}

/** One member's standing on a gameweek, including those yet to pick. */
export interface GameweekMember {
  player_id: string;
  display_name: string;
  has_picked: boolean;
  fixture_id: string | null;
  home: string | null;
  away: string | null;
  competition: string | null;
  market: PickMarket | null;
  outcome: PickOutcome | null;
  runner_name: string | null;
  odds: number | null;
}

/** One row of the season's history — GET /leagues/{slug}/gameweeks. */
export interface GameweekSummary {
  gameweek_id: string;
  /** The date this league's window opens. Not necessarily a Saturday. */
  starts_on: string; // ISO date (yyyy-mm-dd)
  status: GameweekStatus;
  locks_at_utc: string;
  fixture_count: number;
  /** Picks made in *this* league, so the same week reads differently per league. */
  pick_count: number;
}

export interface GameweekSlate {
  gameweek_id: string;
  /** The date this league's window opens. Not necessarily a Saturday. */
  starts_on: string; // ISO date (yyyy-mm-dd)
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

// ── Results — GET /leagues/{slug}/results ───────────────────────────────────

/** One settled round's headline — who won it and how the coupon landed. */
export interface GameweekResult {
  gameweek_id: string;
  /** The date this league's window opened. Not necessarily a Saturday. */
  starts_on: string; // ISO date (yyyy-mm-dd)
  /** Whoever's pick scored the most that round; more than one on a tie. */
  winner_names: string[];
  winner_points: number;
  leg_count: number;
  combined_odds: number;
  /** null when the round had no picks, true only if every leg won. */
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

// ── Player profile — GET /leagues/{slug}/players/{id}/profile ──────────────

/** One resolved pick — a row of a member's history. */
export interface SettledPick {
  gameweek_id: string;
  /** The date this league's window opens. Not necessarily a Saturday. */
  starts_on: string; // ISO date (yyyy-mm-dd)
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

/**
 * A member's record **within one league**. Picks are league-scoped, so a member
 * in three leagues has three of these.
 */
export interface PlayerProfile {
  player_id: string;
  display_name: string;
  total_points: number;
  picks_played: number;
  picks_won: number;
  rank: number;
  /** null until something settles — an untested record is not a bad one. */
  win_rate_pct: number | null;
  history: SettledPick[];
}

// ── Cross-league summary — GET /me/cross-league-summary ────────────────────

/** The caller's own selection in a league's latest round. */
export interface MyPick {
  fixture_id: string;
  home: string;
  away: string;
  market: PickMarket;
  outcome: PickOutcome;
  runner_name: string;
  odds: number;
  status: PickStatus;
}

/** A league's latest round as it concerns the caller — a home card's body. */
export interface CurrentRound {
  gameweek_id: string;
  /** The date this league's window opens. Not necessarily a Saturday. */
  starts_on: string; // ISO date (yyyy-mm-dd)
  status: GameweekStatus;
  locks_at_utc: string;
  /** The whole league's acca for the round, not just the caller's leg. */
  leg_count: number;
  combined_odds: number;
  /** null while the caller has yet to claim a selection this round. */
  my_pick: MyPick | null;
}

/** One league the caller belongs to, and their record in it. */
export interface PerLeagueSummary {
  slug: string;
  name: string;
  member_count: number;
  /** From the league's own season table, so it matches the leaderboard exactly. */
  rank: number | null;
  total_points: number;
  picks_played: number;
  picks_won: number;
  /** null when the league has no rounds yet. */
  current_round: CurrentRound | null;
}

/**
 * The caller's season across every league they play.
 *
 * Points and win rate aggregate honestly — every league scores `round(odds × 10)`
 * off the same scale. Rank does not, so `avg_rank` spans only leagues big enough
 * to rank against and `avg_rank_leagues` says how many that was.
 */
export interface CrossLeagueSummary {
  avg_rank: number | null;
  avg_rank_leagues: number;
  total_points: number;
  picks_played: number;
  picks_won: number;
  /** null until something settles — an untested record is not a bad one. */
  win_rate_pct: number | null;
  leagues_count: number;
  per_league: PerLeagueSummary[];
}

// ---------------------------------------------------------------------------
// Leagues (the social "leaderboard" layer — kept from the shared spine).
// ---------------------------------------------------------------------------

/** The weekly window a league plays — a range in Europe/London plus its lock offset. */
export interface SlateWindow {
  /** `date.weekday()`: Monday 0 … Sunday 6. */
  start_weekday: number;
  /** Minutes from local midnight. */
  start_minute: number;
  end_weekday: number;
  end_minute: number;
  lock_offset_minutes: number;
}

/** One competition a league plays, by the provider's slug plus a display name. */
export interface CompetitionRef {
  slug: string;
  name: string;
}

/** GET /leagues/{slug}/competitions — the admin's competition picker. */
export interface CompetitionCatalogue {
  /** True when the league is on the default group (every UK competition). */
  all_uk: boolean;
  /** Every UK competition the odds provider carries — the set to choose from. */
  available: CompetitionRef[];
  /** The league's explicit selection (empty when `all_uk`). */
  selected: CompetitionRef[];
}

/** POST /leagues/{slug}/gameweeks — the result of creating an ad-hoc round. */
export interface AdHocGameweekResult {
  gameweek_id: string;
  starts_on: string;
  status: GameweekStatus;
  locks_at_utc: string;
  fixture_count: number;
  /** True when this call created the round; false when it refreshed an existing one. */
  created: boolean;
}

export interface LeagueSummary {
  slug: string;
  name: string;
  description: string | null;
  privacy: 'public_open' | 'public_request' | 'private';
  member_count: number;
  max_members: number | null;
  pick_scope: PickScope;
  created_at: string;
  // Admin configuration (Batch 15). Present on the single-league read (GET /{slug}) and on
  // create/update responses; absent from the `/mine` summary, hence optional here.
  slate_window?: SlateWindow;
  /** null = the "all UK leagues" group; a list = an explicit selection. */
  competitions?: CompetitionRef[] | null;
  offered_markets?: PickMarket[];
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
