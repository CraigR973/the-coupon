import { formatInTimeZone } from 'date-fns-tz';
import { Check, Loader2 } from 'lucide-react';
import type { FixtureSlate, PickMarket, PickOutcome, SelectionOption } from '../lib/types';
import { Badge } from './ui/badge';
import {
  formatOdds,
  marketLabel,
  outcomeLabel,
  potentialPoints,
  selectionKey,
} from '../lib/coupon';
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

export interface PickCardProps {
  fixture: FixtureSlate;
  timezone: string;
  /** Gameweek is closed (locked/settled) or the deadline has passed. */
  locked: boolean;
  /** `${fixtureId}:${market}:${outcome}` currently being submitted. */
  pendingKey: string | null;
  /** A grab is in flight somewhere — disable every button to avoid double-grabs. */
  busy: boolean;
  onGrab: (fixtureId: string, market: PickMarket, outcome: PickOutcome) => void;
}

/**
 * One fixture on the weekly Coupon slate: its Betfair-priced selections as
 * grabbable buttons. A selection the caller holds is highlighted; one held by
 * another member is shown unavailable ("taken by …"); the rest are one tap to
 * grab. Presentation only — the grab mutation lives in usePickEditor.
 */
export function PickCard({ fixture, timezone, locked, pendingKey, busy, onGrab }: PickCardProps) {
  const kickoffLocal = formatInTimeZone(new Date(fixture.kickoff_utc), timezone, 'EEE d MMM, HH:mm');

  const byMarket = new Map<PickMarket, SelectionOption[]>();
  for (const sel of fixture.selections) {
    const bucket = byMarket.get(sel.market) ?? [];
    bucket.push(sel);
    byMarket.set(sel.market, bucket);
  }
  const markets = MARKET_ORDER.filter((m) => byMarket.has(m));

  return (
    <div
      className="flex flex-col rounded-lg border border-border bg-surface p-4"
      data-testid={`pick-card-${fixture.fixture_id}`}
    >
      {/* Eyebrow: competition + kickoff */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <Badge variant="muted">{fixture.competition}</Badge>
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
          {kickoffLocal}
        </span>
      </div>

      {/* Teams */}
      <p className="mb-3 text-sm font-sans text-text-primary">
        <span className="font-medium">{fixture.home}</span>
        <span className="mx-1.5 text-text-muted">v</span>
        <span className="font-medium">{fixture.away}</span>
      </p>

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
  onGrab,
}: {
  fixture: FixtureSlate;
  sel: SelectionOption;
  locked: boolean;
  busy: boolean;
  pending: boolean;
  onGrab: (fixtureId: string, market: PickMarket, outcome: PickOutcome) => void;
}) {
  const label = outcomeLabel(sel.market, sel.outcome, fixture.home, fixture.away);
  const takenByOther = sel.taken_by_player_id !== null && !sel.mine;
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
          <span className="shrink-0 font-mono text-xs tabular-nums">{formatOdds(sel.odds)}</span>
        )}
      </span>
      <span className="text-[10px] font-mono uppercase tracking-wide text-text-muted">
        {takenByOther ? (
          <>taken by {firstName(sel.taken_by_name ?? 'someone')}</>
        ) : sel.mine ? (
          'your pick'
        ) : (
          <>win {potentialPoints(sel.odds)} pts</>
        )}
      </span>
    </button>
  );
}
