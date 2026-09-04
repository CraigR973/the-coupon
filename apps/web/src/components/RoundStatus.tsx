import { Clock, Lock } from 'lucide-react';
import type { OddsFormat } from '../lib/types';
import { formatOdds, type RoundPhase } from '../lib/coupon';
import { Badge } from './ui/badge';
import { cn } from '../lib/utils';

/** The reader's own claim on this round, already reduced to words by the caller. */
export interface MyClaim {
  /** What they took — "Draw", "Arsenal", "Both teams score". */
  selection: string;
  /** The fixture context that selection does not already carry. */
  context: string;
  competition: string | null;
  odds: number;
}

export interface RoundStatusProps {
  phase: RoundPhase;
  /** The live clock line — "Picks lock in 1h 59m". Empty when the round has no clock. */
  clock: string;
  pickedCount: number;
  memberCount: number;
  mine: MyClaim | null;
  oddsFormat: OddsFormat;
  /** True while a different selection could still be taken. */
  canSwitch: boolean;
}

/**
 * Chip word and accent per phase. Colour is never the only carrier — the word is there.
 *
 * These words describe *the coupon and the reader*, deliberately, because `GameweekNav`'s
 * badge already describes the claim window a few pixels away and two chips reading `Open`
 * on one screen is the repetition this batch was sent to remove. `Pick required` is also
 * the vocabulary the league cards use, so a member reads the same four words about the
 * same round on home and here.
 */
const PHASE: Record<RoundPhase, { label: string; variant: 'success' | 'warning' | 'muted' }> = {
  not_open: { label: 'Not open yet', variant: 'muted' },
  open: { label: 'Pick required', variant: 'warning' },
  submitted: { label: 'Pick submitted', variant: 'success' },
  complete: { label: 'Coupon complete', variant: 'success' },
  locked_incomplete: { label: 'Incomplete coupon', variant: 'warning' },
  settled: { label: 'Round settled', variant: 'muted' },
};

/**
 * What this round is doing, how far through it the league is, and where the reader stands.
 *
 * Batch 105 folded three separate blocks into this one. The countdown banner, the
 * "Your pick" card and the roster's `n of m picked` header each answered one third of
 * "what is happening and what do I have to do", stacked in that order down the screen,
 * and two of them repeated the round's name on the way past. They are one question, so
 * they are one card, and it is the first thing under the header on every phase.
 */
export function RoundStatus({
  phase,
  clock,
  pickedCount,
  memberCount,
  mine,
  oddsFormat,
  canSwitch,
}: RoundStatusProps) {
  const { label, variant } = PHASE[phase];
  const missing = memberCount - pickedCount;
  const shut = phase === 'locked_incomplete' || phase === 'settled' || phase === 'not_open';

  return (
    <section
      className={cn(
        'mb-4 rounded-lg border bg-surface p-4',
        variant === 'success' && 'border-success/40',
        variant === 'warning' && 'border-warning/40',
        variant === 'muted' && 'border-border',
      )}
      data-testid="round-status"
      aria-label="Round status"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge variant={variant}>{label}</Badge>
        {clock && (
          <span
            className="flex items-center gap-1.5 font-mono text-sm tabular-nums text-text-secondary"
            data-testid="round-clock"
          >
            {shut ? (
              <Lock className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <Clock className="h-3.5 w-3.5" aria-hidden />
            )}
            {clock}
          </span>
        )}
      </div>

      {memberCount > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="round-progress">
          <span className="font-sans text-sm font-medium text-text-primary">
            {pickedCount} of {memberCount} picked
          </span>
          {missing > 0 && (
            <Badge variant="warning">
              {phase === 'locked_incomplete' ? `${missing} never picked` : `${missing} to go`}
            </Badge>
          )}
        </div>
      )}

      <div className="mt-3 border-t border-border pt-3" data-testid="my-pick-summary">
        {mine ? (
          <>
            <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
              Your pick
            </p>
            <p className="mt-1 break-words font-sans text-sm font-medium text-text-primary">
              {mine.selection}
              <span className="mx-1.5 text-text-muted">·</span>
              <span className="font-mono tabular-nums">{formatOdds(mine.odds, oddsFormat)}</span>
            </p>
            <p className="break-words font-sans text-xs text-text-muted">
              {[mine.context, mine.competition].filter(Boolean).join(' · ')}
            </p>
            {canSwitch && (
              <p className="mt-1 font-sans text-xs text-text-muted">
                Tap another selection below to switch.
              </p>
            )}
          </>
        ) : (
          <p className="font-sans text-sm text-text-secondary">
            {phase === 'not_open'
              ? "You haven't picked yet — this round isn't open."
              : canSwitch
                ? "You haven't picked yet — grab a selection below."
                : 'You did not pick this round.'}
          </p>
        )}
      </div>
    </section>
  );
}
