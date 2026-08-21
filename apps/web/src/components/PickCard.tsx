import { Check, Loader2 } from 'lucide-react';
import type {
  FixtureSlate,
  OddsFormat,
  PickMarket,
  PickOutcome,
  SelectionOption,
  TeamContext,
} from '../lib/types';
import { Badge } from './ui/badge';
import { FormLine, ordinal } from './FormLine';
import {
  formatOdds,
  marketLabel,
  outcomeLabel,
  potentialPoints,
  selectionKey,
} from '../lib/coupon';
import { formatInstant } from '../lib/time';
import { cn } from '../lib/utils';

// Fixed display order within each market.
const OUTCOME_ORDER: Record<PickOutcome, number> = {
  HOME: 0,
  DRAW: 1,
  AWAY: 2,
  YES: 0,
  NO: 1,
};
const MARKET_ORDER: PickMarket[] = ['MATCH_ODDS', 'BOTH_TEAMS_TO_SCORE'];

function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] || name;
}

/**
 * When a selection was claimed, in the league's timezone.
 *
 * Absolute rather than relative ("2h ago"): the coupon is served from a cache, and a
 * relative label is wrong the moment it is re-read without a re-render. `d MMM, HH:mm`
 * is the kickoff line's format without the weekday — the same idiom rather than a second
 * one, and unambiguous across a pick window that can open weeks before the round.
 *
 * Returns `null` for a slate served by an API from before Batch 38, which carries no
 * `taken_at`, and for a value that does not parse.
 */
function takenAt(iso: string | null | undefined, timezone: string): string | null {
  return formatInstant(iso, timezone, 'd MMM, HH:mm');
}

/** A club is worth a context line once it has a table position or a run of form. */
function worthShowing(team: TeamContext | null | undefined): boolean {
  return team != null && (team.position !== null || team.form.length > 0);
}

/**
 * One club's position and form, sized to sit under its name on the card.
 *
 * The club is named only to screen readers: sighted readers get it from the column
 * (home left, away right, matching the line above), and repeating both names here
 * would double the card's text for no added meaning.
 */
function TeamContextLine({
  team,
  align = 'left',
}: {
  team: TeamContext | null;
  align?: 'left' | 'right';
}) {
  // An empty cell rather than nothing, so one club's missing data cannot slide the
  // other's under the wrong name.
  if (!worthShowing(team) || team === null) return <span aria-hidden />;

  return (
    <div
      className={cn('flex min-w-0 items-center gap-1.5', align === 'right' && 'justify-end')}
      data-testid={`team-context-${team.team_id}`}
    >
      {team.position !== null && (
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted">
          <span className="sr-only">{team.name}, </span>
          {ordinal(team.position)}
        </span>
      )}
      <FormLine form={team.form} team={team.name} />
    </div>
  );
}

export interface PickCardProps {
  fixture: FixtureSlate;
  timezone: string;
  /** Gameweek is closed (locked/settled) or the deadline has passed. */
  locked: boolean;
  /** `${fixtureId}:${market}:${outcome}` currently being submitted. */
  pendingKey: string | null;
  /** A grab is in flight somewhere — disable every button to avoid double-grabs. */
  busy: boolean;
  /** The member's odds notation. Display only. */
  oddsFormat: OddsFormat;
  onGrab: (fixtureId: string, market: PickMarket, outcome: PickOutcome) => void;
}

/**
 * One fixture on the weekly Coupon slate: its Betfair-priced selections as
 * grabbable buttons. A selection the caller holds is highlighted; one held by
 * another member is shown unavailable ("taken by …"); the rest are one tap to
 * grab. Presentation only — the grab mutation lives in usePickEditor.
 */
export function PickCard({
  fixture,
  timezone,
  locked,
  pendingKey,
  busy,
  oddsFormat,
  onGrab,
}: PickCardProps) {
  const kickoffLocal = formatInstant(fixture.kickoff_utc, timezone, 'EEE d MMM, HH:mm') ?? '';

  const byMarket = new Map<PickMarket, SelectionOption[]>();
  for (const sel of fixture.selections) {
    const bucket = byMarket.get(sel.market) ?? [];
    bucket.push(sel);
    byMarket.set(sel.market, bucket);
  }
  const markets = MARKET_ORDER.filter((m) => byMarket.has(m));
  const claimed = fixture.taken_by_names.length > 0;
  // Either club may be unresolved, and a resolved one may have nothing worth showing
  // (a cup has no table; a promoted side starts a season with no form). Nothing to
  // show means no strip at all rather than an empty row.
  const hasContext = worthShowing(fixture.context?.home) || worthShowing(fixture.context?.away);

  return (
    <div
      className={cn(
        'flex flex-col rounded-lg border bg-surface p-4',
        fixture.mine ? 'border-success/60' : 'border-border',
      )}
      data-testid={`pick-card-${fixture.fixture_id}`}
    >
      {/* Eyebrow: competition + kickoff */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <Badge variant="muted">{fixture.competition}</Badge>
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
          {kickoffLocal}
        </span>
      </div>

      {/* Teams, with each club's table position and recent form beneath (Batch 16) */}
      <div
        className="relative mb-3 grid grid-cols-2 items-baseline gap-2"
        data-testid={`fixture-header-${fixture.fixture_id}`}
      >
        <p className="min-w-0 truncate pr-3 text-sm font-sans font-medium text-text-primary">
          {fixture.home}
        </p>
        <span className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2 text-sm text-text-muted">
          v
        </span>
        <p className="min-w-0 truncate pl-3 text-right text-sm font-sans font-medium text-text-primary">
          {fixture.away}
        </p>
        {hasContext && (
          <div className="contents" data-testid={`fixture-context-${fixture.fixture_id}`}>
            <TeamContextLine team={fixture.context?.home ?? null} />
            <TeamContextLine team={fixture.context?.away ?? null} align="right" />
          </div>
        )}
      </div>

      {/* Fixture-level marker: who has taken anything on this game */}
      {claimed && (
        <p
          className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted"
          data-testid={`fixture-claimed-${fixture.fixture_id}`}
        >
          {fixture.mine ? (
            <span className="text-success">Your game</span>
          ) : (
            <>Picked by {fixture.taken_by_names.map(firstName).join(', ')}</>
          )}
        </p>
      )}

      {fixture.selections.length === 0 ? (
        <p className="text-xs font-sans text-text-muted">Not priced yet — check back closer to kick-off.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {markets.map((market) => {
            const options = [...(byMarket.get(market) ?? [])].sort(
              (a, b) => OUTCOME_ORDER[a.outcome] - OUTCOME_ORDER[b.outcome],
            );
            return (
              <div key={market}>
                <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
                  {marketLabel(market)}
                </p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {options.map((sel) => (
                    <SelectionButton
                      key={selectionKey(sel.market, sel.outcome)}
                      fixture={fixture}
                      sel={sel}
                      locked={locked}
                      busy={busy}
                      pending={
                        pendingKey === `${fixture.fixture_id}:${selectionKey(sel.market, sel.outcome)}`
                      }
                      oddsFormat={oddsFormat}
                      timezone={timezone}
                      onGrab={onGrab}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SelectionButton({
  fixture,
  sel,
  locked,
  busy,
  pending,
  oddsFormat,
  timezone,
  onGrab,
}: {
  fixture: FixtureSlate;
  sel: SelectionOption;
  locked: boolean;
  busy: boolean;
  pending: boolean;
  oddsFormat: OddsFormat;
  timezone: string;
  onGrab: (fixtureId: string, market: PickMarket, outcome: PickOutcome) => void;
}) {
  const label = outcomeLabel(sel.market, sel.outcome, fixture.home, fixture.away);
  const takenByOther = sel.taken_by_player_id !== null && !sel.mine;
  const takenAtLabel = takenByOther ? takenAt(sel.taken_at, timezone) : null;
  const grabbable = !locked && !sel.mine && !takenByOther && !busy;

  return (
    <button
      type="button"
      disabled={!grabbable}
      onClick={() => onGrab(fixture.fixture_id, sel.market, sel.outcome)}
      aria-pressed={sel.mine}
      data-testid={`selection-${fixture.fixture_id}-${sel.market}-${sel.outcome}`}
      className={cn(
        'flex flex-col items-start gap-0.5 rounded-md px-2.5 py-2 text-left transition-colors',
        sel.mine
          ? 'border-2 border-success bg-success/20 text-success'
          : takenByOther
            ? 'cursor-not-allowed border border-border/50 bg-surface opacity-55'
            : grabbable
              ? 'border border-border bg-surface-elevated text-text-primary hover:border-primary/60 press-down cursor-pointer'
              : 'cursor-not-allowed border border-border/50 bg-surface opacity-60',
        'focus-visible:outline-none focus-visible:shadow-glow',
      )}
    >
      <span className="flex w-full items-center justify-between gap-1">
        <span className="truncate text-xs font-sans font-medium">
          {sel.mine && <Check className="mr-0.5 inline h-3 w-3" aria-hidden />}
          {label}
        </span>
        {pending ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
        ) : (
          <span className="shrink-0 font-mono text-xs tabular-nums">
            {formatOdds(sel.odds, oddsFormat)}
          </span>
        )}
      </span>
      <span className="text-[10px] font-mono uppercase tracking-wide text-text-muted">
        {takenByOther ? (
          <>
            taken by {firstName(sel.taken_by_name ?? 'someone')}
            {takenAtLabel ? <span className="normal-case"> · {takenAtLabel}</span> : null}
            {' · '}
            {potentialPoints(sel.odds)} pts
          </>
        ) : sel.mine ? (
          <>your pick · {potentialPoints(sel.odds)} pts</>
        ) : (
          <>win {potentialPoints(sel.odds)} pts</>
        )}
      </span>
    </button>
  );
}
