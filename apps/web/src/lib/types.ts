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
/** `scheduled` (Batch 27) is a round that exists but whose picks have not opened yet. */
export type GameweekStatus = 'scheduled' | 'open' | 'locked' | 'settled';
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
  /**
   * When the holder claimed it. Naive UTC, like `kickoff_utc` and `locks_at_utc`.
   * Optional because the web app deploys ahead of the API — a slate served by an
   * API from before Batch 38 carries no such field.
   */
  taken_at?: string | null;
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

/**
 * Where a match stands, in The Coupon's vocabulary rather than a provider's (Batch 110).
 *
 * `postponed` and `cancelled` are separate because they mean different things to a
 * reader: one will be played on some other night and one will not.
 */
export type MatchState = 'scheduled' | 'live' | 'finished' | 'postponed' | 'cancelled';

/** One match on a club's season, from that club's point of view (Batch 110). */
export interface TeamSeasonMatch {
  match_id: string;
  kickoff_utc: string;
  opponent: string;
  opponent_team_id: string;
  /** True when this club is at home — the one thing a scoreline cannot be read without. */
  home: boolean;
  state: MatchState;
  /** The provider's own words: "FT", "PP", a live minute. Display text, not a filter. */
  status: string;
  /** Null until there is a score. An unplayed fixture is not a nil-nil. */
  goals_for: number | null;
  goals_against: number | null;
  /** Null until the match has a final score to derive it from. */
  result: FormResult | null;
}

/** A club's complete season in one competition (Batch 110). */
export interface TeamSeason {
  team_id: string;
  team: string;
  competition_id: string;
  competition: string;
  season: number;
  /** Chronological, oldest first — the order the season is played. */
  matches: TeamSeasonMatch[];
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
  /** Most recent **last**, e.g. `"LWWDW"` — the order every football table prints. */
  form: string;
  /**
   * The matches behind the form line, most recent **first** (Batch 53).
   *
   * Optional, unlike `TeamContext.recent`: Vercel deploys this app from `main` on merge
   * while the API waits for `/ship-prod`, so for that window the table arrives without
   * it. Absent and empty mean the same thing here — pips that do not open.
   */
  recent?: FormMatch[];
}

/** One competition's table — GET /football/tables. */
export interface CompetitionTable {
  competition_id: string;
  competition: string;
  season: number;
  /** When this table was last ingested. Shown as "as of": stored data, not live. */
  updated_at: string | null;
  rows: TableEntry[];
}

/** One finished match — GET /football/results. */
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
  /** When picks open; null when the league announces no opening. */
  picks_open_at_utc: string | null;
  /**
   * What members call this round — "Gameweek 12". Optional and nullable: the web app
   * deploys ahead of the API, and a round discovered before Batch 41 has no number.
   * Absent means label the round by its date alone.
   */
  number?: number | null;
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
  /** When picks open; null when the league announces no opening. */
  picks_open_at_utc: string | null;
  /** What members call this round — "Gameweek 12". Absent means label by date alone. */
  number?: number | null;
  fixtures: FixtureSlate[];
  members: GameweekMember[];
  members_missing_picks: number;
  /** The league's claim rule, so the UI can explain why a whole game is gone. */
  pick_scope: PickScope;
  /**
   * True when the prices came out of a *failed* refresh — last known values, or none at
   * all — so the screen can say "prices may be out of date" instead of presenting stale
   * numbers as current. Optional: the web app deploys ahead of the API, and a response
   * from before Batch 48 simply omits it, which reads as "not degraded".
   */
  odds_degraded?: boolean;
}

// ── Pick — POST /leagues/{slug}/picks · GET .../gameweeks/{id}/pick ─────────

export interface SubmitPickBody {
  fixture_id: string;
  market: PickMarket;
  outcome: PickOutcome;
  /**
   * The price this member was looking at when they tapped, exactly as the card rendered
   * it (Batch 114).
   *
   * The card may be up to half an hour old and the submit path prices the fixture afresh,
   * so what a member taps has never been quite what they are scored on. Sending it back
   * lets the API refuse with `PRICE_MOVED` and the new number instead of silently freezing
   * one they never saw.
   *
   * Optional because the two halves deploy apart — an API from before Batch 114 ignores
   * it, and omitting it simply skips the check.
   */
  odds?: number;
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

/**
 * What `POST .../picks` answers with — the pick, plus how full the coupon now is.
 *
 * Only the submit path carries these three (Batch 107). `GET .../gameweeks/{id}/pick`
 * answers "what did I pick", which is a question about one member and returns the plain
 * `PickResponse`, so the reconcile read in `usePickEditor` is deliberately typed without
 * them.
 *
 * They exist so the member who fills the coupon can be shown the completion state on the
 * same paint as their pick, rather than through a refetch racing the write that caused
 * it — and they are the same numbers the league's push quotes, read once server-side, so
 * the screen and the tray cannot disagree.
 */
export interface SubmitPickResponse extends PickResponse {
  /** Active members of the league holding a pick for this round, this one included. */
  picked_count: number;
  /** Active members of the league, whatever they have done with their notifications. */
  member_count: number;
  /** Whether the round's coupon is now full. False for an empty league. */
  all_picked: boolean;
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
  // ── Batch 67. All three optional, because Vercel deploys the web app on merge while
  // the API waits for /ship-prod: for that window the deployed API sends none of them.
  /** What this pick scored, once the round settled. */
  points_awarded?: number | null;
  /**
   * The score, on a settled round or a round being played, when the leg's fixture
   * resolved to a match carrying one. Both are null together, and null means *no score
   * to show* — never nil-nil. The join is name-based and fails open rather than
   * guessing (see `match_link.py`).
   */
  home_goals?: number | null;
  away_goals?: number | null;
  /**
   * Whether that score is the result or the state of play (Batch 72). Defaults to true
   * so a deployed API that predates it is read as final, which is what it always was.
   * A screen that renders a running score the same way it renders a final one tells a
   * member their pick has landed when it has not.
   */
  score_is_final?: boolean;
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
  /**
   * How many legs landed (Batch 79). Optional because the web app deploys ahead of the
   * API; absent means the row shows the coupon outcome alone, as it did before.
   */
  picks_won?: number;
}

// ── Seasons — GET /leagues/{slug}/seasons ─────────────────────────────────

/**
 * One season a league has a table for (Batch 96).
 *
 * `standings` used to aggregate every settled pick a league had ever played, so a league
 * running for three years read as one never-ending season. It is now bounded, and this is
 * the index the seasons on the far side of the boundary are reached through.
 *
 * `label` is the API's, not this app's: the heading over a table and the entry in the
 * archive selector then cannot drift into naming the same season two ways.
 */
export interface SeasonSummary {
  /** The season's starting year — August 2026 and February 2027 are both `2026`. */
  season: number;
  /** How it is written on screen: `2026/27`. */
  label: string;
  is_current: boolean;
  /** How many rounds it has settled. Zero for a current season nobody has played yet. */
  rounds_settled: number;
}

// ── Standings — GET /leagues/{slug}/standings ──────────────────────────────

/**
 * One settled round in a member's recent run (Batch 80).
 *
 * `status` is the pick's, so it is `won`, `lost` or **`void`** — never `draw`. A coupon
 * pick has no drawn state, and a void fixture never ran, which is not the same as a bet
 * that ran and lost. That is why this does not reuse `FormResult`, which is a football
 * club's W/D/L and means something else.
 */
export interface FormRound {
  gameweek_id: string;
  starts_on: string; // ISO date (yyyy-mm-dd)
  status: PickStatus;
  /** What the round scored — zero for anything that did not win. */
  points: number;
}

export interface Standing {
  player_id: string;
  display_name: string;
  total_points: number;
  picks_played: number;
  picks_won: number;
  rank: number;
  // ── Batch 70: what kind of picks this member is making ──────────────────────
  //
  // Every one optional, because Vercel deploys this app from `main` on merge while the
  // API waits for `/ship-prod` — for that window the figures simply are not there.
  //
  // **Two denominators, deliberately.** `picks_played` counts won, lost *and* void: a
  // member whose fixture was postponed took part in that round. The odds figures count
  // only `picks_priced` — won and lost — because a bet that never ran is not a price
  // they should be credited with. A screen showing both without saying so is lying
  // quietly, so every screen that shows them says so.
  /** Won and lost only: the picks that actually ran. */
  picks_priced?: number;
  /** The sum of the prices taken over `picks_priced`. A sum, not an accumulator. */
  cumulative_odds?: number;
  average_odds?: number | null;
  /** Points over `picks_played` — the same total from fewer rounds is a better record. */
  points_per_pick?: number | null;
  best_return?: number | null;
  /** How the priced picks split around `longshot_odds`. */
  longshot_picks?: number;
  favourite_picks?: number;
  /** The line the split was drawn at, carried so the label cannot drift from it. */
  longshot_odds?: number;
  /** Wins over `picks_played`. Computed by the API so every surface agrees. */
  win_rate_pct?: number | null;
  /**
   * The last five settled rounds, **most recent first** — the order every form payload
   * here is sent in, reversed by the component that draws it (Batch 80). Absent on an
   * API that predates it, which renders as no run at all rather than as an empty one.
   */
  recent_form?: FormRound[];
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
  // ── Batch 70: what kind of picks this member is making ──────────────────────
  //
  // Every one optional, because Vercel deploys this app from `main` on merge while the
  // API waits for `/ship-prod` — for that window the figures simply are not there.
  //
  // **Two denominators, deliberately.** `picks_played` counts won, lost *and* void: a
  // member whose fixture was postponed took part in that round. The odds figures count
  // only `picks_priced` — won and lost — because a bet that never ran is not a price
  // they should be credited with. A screen showing both without saying so is lying
  // quietly, so every screen that shows them says so.
  /** Won and lost only: the picks that actually ran. */
  picks_priced?: number;
  /** The sum of the prices taken over `picks_priced`. A sum, not an accumulator. */
  cumulative_odds?: number;
  average_odds?: number | null;
  /** Points over `picks_played` — the same total from fewer rounds is a better record. */
  points_per_pick?: number | null;
  best_return?: number | null;
  /** How the priced picks split around `longshot_odds`. */
  longshot_picks?: number;
  favourite_picks?: number;
  longshot_odds?: number;
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
  /**
   * What this pick scored, once the round settled (Batch 79). `null` while it is still
   * running, and on a lost or void pick — the difference between nothing and zero.
   * Optional because the web app deploys ahead of the API.
   */
  points_awarded?: number | null;
}

/**
 * The week just gone, as it concerns the caller (Batch 79).
 *
 * Carried separately from `current_round` because a settled round does not stay current:
 * on a league that announces no opening, next week's round outranks it the moment
 * discovery writes it, and the member would never see how their week went.
 */
export interface LastResult {
  gameweek_id: string;
  starts_on: string; // ISO date (yyyy-mm-dd)
  /** What members call the round; null on one discovered before Batch 41. */
  number: number | null;
  leg_count: number;
  /** How many legs landed. `all_won` alone cannot tell five of six from none of six. */
  picks_won: number;
  combined_odds: number;
  all_won: boolean | null;
  my_pick: MyPick | null;
  /** Places gained over this round — positive up, null when there was no table before. */
  rank_movement?: number | null;
}

/** A league's latest round as it concerns the caller — a home card's body. */
export interface CurrentRound {
  gameweek_id: string;
  /** The date this league's window opens. Not necessarily a Saturday. */
  starts_on: string; // ISO date (yyyy-mm-dd)
  status: GameweekStatus;
  locks_at_utc: string;
  /** When picks open; null when the league announces no opening. */
  picks_open_at_utc: string | null;
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
  // ── Batch 70: what kind of picks this member is making ──────────────────────
  //
  // Every one optional, because Vercel deploys this app from `main` on merge while the
  // API waits for `/ship-prod` — for that window the figures simply are not there.
  //
  // **Two denominators, deliberately.** `picks_played` counts won, lost *and* void: a
  // member whose fixture was postponed took part in that round. The odds figures count
  // only `picks_priced` — won and lost — because a bet that never ran is not a price
  // they should be credited with. A screen showing both without saying so is lying
  // quietly, so every screen that shows them says so.
  /** Won and lost only: the picks that actually ran. */
  picks_priced?: number;
  /** The sum of the prices taken over `picks_priced`. A sum, not an accumulator. */
  cumulative_odds?: number;
  average_odds?: number | null;
  /** Points over `picks_played` — the same total from fewer rounds is a better record. */
  points_per_pick?: number | null;
  best_return?: number | null;
  /** How the priced picks split around `longshot_odds`. */
  longshot_picks?: number;
  favourite_picks?: number;
  /**
   * The last five settled rounds, most recent first (Batch 81). Read off the league's own
   * season table, so home and the leaderboard can never draw different runs for the same
   * member. Absent on an API that predates it, which renders as no run at all.
   */
  recent_form?: FormRound[];
  // ── Batch 79, both optional for the same deploy gap ─────────────────────────
  /** The week just gone, whether or not it is still the current round. */
  last_result?: LastResult | null;
  /**
   * When this league next starts accepting picks, if that instant is still ahead.
   * `null` when no future round announces an opening — including the ordinary case of a
   * league that announces none, whose next round is claimable from discovery.
   */
  next_opens_at_utc?: string | null;
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
  // ── Batch 70: what kind of picks this member is making ──────────────────────
  //
  // Every one optional, because Vercel deploys this app from `main` on merge while the
  // API waits for `/ship-prod` — for that window the figures simply are not there.
  //
  // **Two denominators, deliberately.** `picks_played` counts won, lost *and* void: a
  // member whose fixture was postponed took part in that round. The odds figures count
  // only `picks_priced` — won and lost — because a bet that never ran is not a price
  // they should be credited with. A screen showing both without saying so is lying
  // quietly, so every screen that shows them says so.
  /** Won and lost only: the picks that actually ran. */
  picks_priced?: number;
  /** The sum of the prices taken over `picks_priced`. A sum, not an accumulator. */
  cumulative_odds?: number;
  average_odds?: number | null;
  /** Points over `picks_played` — the same total from fewer rounds is a better record. */
  points_per_pick?: number | null;
  best_return?: number | null;
  /** How the priced picks split around `longshot_odds`. */
  longshot_picks?: number;
  favourite_picks?: number;
  longshot_odds?: number;
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
  /**
   * Minutes before the window opens that picks *open* (Batch 27) — the far end of the
   * claim period whose near end is `lock_offset_minutes`, measured from the same
   * anchor. `null` means the league announces no opening and a round is claimable as
   * soon as it is published.
   */
  pick_open_offset_minutes: number | null;
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
  /** When picks open; null when the league announces no opening. */
  picks_open_at_utc: string | null;
  /**
   * What members call this round — "Gameweek 12". Optional and nullable: the web app
   * deploys ahead of the API, and a round discovered before Batch 41 has no number.
   * Absent means label the round by its date alone.
   */
  number?: number | null;
  fixture_count: number;
  /** True when this call created the round; false when it refreshed an existing one. */
  created: boolean;
}

/** One round in a `POST /leagues/{slug}/gameweeks/refresh` result. */
export interface RefreshedRound {
  gameweek_id: string;
  starts_on: string;
  status: GameweekStatus;
  /** What members call this round — "Gameweek 12"; null on rounds predating Batch 41. */
  number?: number | null;
  fixture_count: number;
  /** True when this call created the round; false when it topped up an existing one. */
  created: boolean;
}

/**
 * POST /leagues/{slug}/gameweeks/refresh — rebuild the league's cadence rounds now
 * instead of waiting for the 06:00 discovery run (Batch 47).
 */
export interface RefreshRoundsResult {
  rounds: RefreshedRound[];
  /** Dates the shared fixture pool could not serve, so they cost a provider sweep. */
  fetched_dates: string[];
  /** Dates left for the daily run: the pool was empty and no sweep was available. */
  deferred_dates: string[];
  /** Dates whose round is already locked or settled — nothing a rebuild may change. */
  skipped_dates: string[];
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

/** One row of a league's admin trail. Batch 94. */
export interface LeagueAuditEntry {
  id: string;
  actor_name: string | null;
  action_type: string;
  target_table: string;
  target_id: string | null;
  /** The writer's payload — who was removed, what a setting became. May be absent. */
  changes: Record<string, unknown> | null;
  timestamp: string;
}

export interface LeagueAuditLogResponse {
  entries: LeagueAuditEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface LeagueInvite {
  id: string;
  token: string;
  created_by_display_name: string;
  created_at: string;
  expires_at: string | null;
  used_at: string | null;
}

// ── Site admin console (Batch 66) ──────────────────────────────────────────────
//
// Site admin, not league admin: these read across every league, including ones the
// caller is not a member of. `/api/v1/admin/*` refuses anyone whose profile role is
// not `admin`, so every screen behind them is gated on the same flag.

export interface AdminPlayer {
  id: string;
  display_name: string;
  role: 'player' | 'admin';
  is_active: boolean;
  /**
   * False between an admin clearing this member's PIN and the member choosing a new
   * one. It is the difference between "cannot remember their PIN" and "has already
   * been reset and has not come back yet", which look identical otherwise.
   */
  pin_set: boolean;
  failed_login_count: number;
  locked_until: string | null;
  deleted_at: string | null;
  league_count: number;
  created_at: string;
}

export interface AdminInvite {
  id: string;
  token: string;
  display_name_hint: string | null;
  league_id: string;
  league_name: string;
  league_slug: string;
  created_by_name: string | null;
  claimed_by_name: string | null;
  claimed_at: string | null;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
}

export interface AdminLeague {
  id: string;
  slug: string;
  name: string;
  privacy: 'public_open' | 'public_request' | 'private';
  join_code: string | null;
  member_count: number;
  max_members: number;
  created_at: string;
  deleted_at: string | null;
}

/**
 * What a PIN reset did. `temp_pin` is deliberately absent: no temporary PIN is minted
 * and nothing passes through the admin — the member chooses their own at `/set-pin`.
 */
export interface AdminResetPinResult {
  pin_cleared: boolean;
  sessions_revoked: number;
}

// ── Site admin: the operational half (Batch 69) ────────────────────────────────

export interface AdminUpcomingLock {
  league_slug: string;
  league_name: string;
  gameweek_id: string;
  starts_on: string;
  locks_at_utc: string;
  picks_in: number;
  members: number;
}

/**
 * A round past its lock that has not settled. The shape that hangs forever: the odds
 * provider never resolved the fixtures, so the picks stay pending and the settle sweep
 * finds nothing to do three times a day.
 */
export interface AdminStuckRound {
  league_slug: string;
  league_name: string;
  gameweek_id: string;
  starts_on: string;
  locks_at_utc: string;
  pending_picks: number;
}

export interface AdminAuditEntry {
  id: string;
  actor_name: string | null;
  action_type: string;
  target_table: string;
  target_id: string | null;
  timestamp: string;
}

export interface AdminSchedulerState {
  /** What the settings ask for. */
  enabled: boolean;
  /** What the running container actually has. The two come apart, which is the point. */
  running: boolean;
  jobs: Array<{ id: string; next_run_utc: string | null }>;
}

/**
 * What the odds provider's plan has left, as the API process has counted it (Batch 114).
 *
 * An estimate rather than the provider's own accounting: it counts what that process sent
 * and knows nothing of another instance or of what the plan thought before it started.
 * That is still the difference between seeing a quota run down and finding out from a
 * member that it has gone — which is how 2026-09-05's outage was discovered.
 */
export interface AdminOddsBudget {
  /** False when no provider session has been established since the process started. */
  live: boolean;
  hour_used: number;
  hour_limit: number;
  hour_remaining: number;
  day_used: number;
  day_limit: number;
  day_remaining: number;
  /** Seconds left on the `429` cooldown, or null when upstream is not suppressed. */
  rate_limited_for: number | null;
}

export interface AdminDashboard {
  active_members: number;
  members_awaiting_pin: number;
  leagues: number;
  upcoming_locks: AdminUpcomingLock[];
  stuck_rounds: AdminStuckRound[];
  recent_audit: AdminAuditEntry[];
  scheduler: AdminSchedulerState;
  /**
   * Optional because the web app deploys from `main` while the API waits for
   * `/ship-prod`, so this screen has to render against an API that predates Batch 114.
   */
  odds_budget?: AdminOddsBudget;
}

export interface AdminSyncJob {
  key: string;
  label: string;
  summary: string;
  /** Estimated calls against odds-api.io's metered plan. 0 is free. */
  provider_requests: number;
  spends_budget: boolean;
  /** Hits against the shared bucket one press costs — the bucket counts slate walks. */
  budget_units: number;
  next_run_utc: string | null;
}

export interface AdminSyncJobs {
  jobs: AdminSyncJob[];
  hourly_budget: number;
  budget_limit: string;
}

export interface AdminPendingFixture {
  fixture_id: string;
  provider_event_id: string;
  home: string;
  away: string;
  competition: string;
  kickoff_utc: string;
  pending_picks: number;
}

export interface AdminPendingRound {
  league_slug: string;
  league_name: string;
  gameweek_id: string;
  starts_on: string;
  status: GameweekStatus;
  locks_at_utc: string;
  fixtures: AdminPendingFixture[];
}
