import type { FormRound } from '../lib/types';
import { cn } from '../lib/utils';

/**
 * Batch 80. A member's last five settled rounds, oldest on the left.
 *
 * **Not `FormLine`, and the difference is the point.** That component draws a football
 * club's W/D/L, and a coupon pick has no drawn state: it won, it lost, or its fixture
 * never ran. A void borrowing the draw's pip would erase the distinction the leaderboard's
 * two denominators exist to preserve — `picks_played` counts a void, the odds figures do
 * not — in the one place a reader would most likely take it at face value.
 *
 * **The points are shown because the letters cannot carry them.** A winner scores
 * `round(odds × 10)`, so one win at 5.00 outscores two at 2.00, and a run of five W's can
 * be worth less than a run of two. Football form is three letters because football points
 * are 3/1/0; these are not, and a run drawn as letters alone would flatter the member
 * taking short prices at the expense of the one taking long ones.
 *
 * Colour is never the only carrier: each round keeps its letter, and the accessible label
 * spells out the result and the score in words.
 */

const LETTER: Record<FormRound['status'], string> = {
  won: 'W',
  lost: 'L',
  void: 'V',
  pending: '·',
};

const WORD: Record<FormRound['status'], string> = {
  won: 'won',
  lost: 'lost',
  void: 'void',
  pending: 'not settled',
};

const PIP: Record<FormRound['status'], string> = {
  won: 'border-success/40 bg-success/20 text-success',
  lost: 'border-error/40 bg-error/20 text-error',
  void: 'border-border bg-surface-elevated text-text-muted',
  pending: 'border-border bg-surface-elevated text-text-muted',
};

export interface PickFormLineProps {
  /** As the API sends them: most recent **first**. Drawn oldest-first. */
  form: FormRound[] | undefined;
  /** Whose run this is, for the screen-reader label. */
  player?: string;
  className?: string;
}

export function PickFormLine({ form, player, className }: PickFormLineProps) {
  // Renders nothing at all for an empty run rather than an empty box. A member can be
  // legitimately formless — newly joined, or a league whose first round has yet to
  // settle — and a placeholder on every one of those is noise. An `undefined` run is the
  // deployed API predating this field, which reads the same way for the same reason.
  if (!form || form.length === 0) return null;
  const oldestFirst = [...form].reverse();

  const spoken = oldestFirst
    .map((round) =>
      round.status === 'won' ? `won ${round.points} points` : WORD[round.status],
    )
    .join(', ');

  return (
    <span
      role="img"
      aria-label={
        player ? `${player}'s last rounds, oldest first: ${spoken}` : `Last rounds, oldest first: ${spoken}`
      }
      className={cn('inline-flex items-start gap-1 align-middle', className)}
      data-testid="pick-form"
    >
      {oldestFirst.map((round) => (
        <span key={round.gameweek_id} aria-hidden className="flex w-5 flex-col items-center gap-0.5">
          <span
            className={cn(
              'inline-flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border font-mono text-[9px] font-semibold leading-none',
              PIP[round.status],
            )}
          >
            {LETTER[round.status]}
          </span>
          {/* Blank rather than `0` under a round that scored nothing: five zeroes down a
              leaderboard is a column of noise, and the pip has already said what happened. */}
          <span className="font-mono text-[9px] leading-none tabular-nums text-text-muted">
            {round.points > 0 ? round.points : ''}
          </span>
        </span>
      ))}
    </span>
  );
}
