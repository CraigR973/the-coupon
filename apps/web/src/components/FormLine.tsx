import type { FormMatch, FormResult } from '../lib/types';
import { formatInstant } from '../lib/time';
import { cn } from '../lib/utils';

const RESULT_STYLES: Record<FormResult, string> = {
  W: 'border-success/40 bg-success/20 text-success',
  D: 'border-border bg-surface-elevated text-text-muted',
  L: 'border-error/40 bg-error/20 text-error',
};

const RESULT_TEXT: Record<FormResult, string> = {
  W: 'text-success',
  D: 'text-text-secondary',
  L: 'text-error',
};

const RESULT_WORDS: Record<FormResult, string> = { W: 'won', D: 'drew', L: 'lost' };

function isFormResult(letter: string): letter is FormResult {
  return letter === 'W' || letter === 'D' || letter === 'L';
}

export interface FormLineProps {
  /** Most recent **last**, e.g. `"LWWDW"` — the order every football table prints. */
  form: string;
  /** Whose form this is, for the screen-reader label. */
  team?: string;
  className?: string;
  /**
   * Disclosure state, when the pips open onto the matches behind them (Batch 53).
   *
   * Passing `onToggle` is what turns the run into a control: without it the pips stay
   * the plain graphic they have always been, which is what a club with no stored
   * matches gets. The panel itself is `FormMatches`, placed by the caller — a pick card
   * opens it the full width of the card and a league table opens it across a row, and
   * neither fits inside the few pixels the pips occupy.
   */
  expanded?: boolean;
  onToggle?: () => void;
  /** `id` of the `FormMatches` panel this run controls. */
  controls?: string;
}

/**
 * A club's recent results as W/D/L pips, oldest on the left.
 *
 * Colour is not the only carrier — each pip keeps its letter — so the run is
 * still readable without distinguishing red from green.
 *
 * Renders nothing at all for an empty run rather than an empty box. A club can be
 * legitimately formless: newly promoted, early in a season, or simply not yet
 * reached by ingestion, and a placeholder on every one of those is noise.
 *
 * With `onToggle` it becomes a disclosure button. The accessible name does not change
 * shape when it does — it is the same sentence the graphic carried, because it names
 * the same thing — but it moves off a `role="img"` (which would swallow the pips and
 * leave nothing for `aria-expanded` to describe) onto the button itself.
 */
export function FormLine({
  form,
  team,
  className,
  expanded,
  onToggle,
  controls,
}: FormLineProps) {
  const results = [...form].filter(isFormResult);
  if (results.length === 0) return null;

  const spoken = results.map((result) => RESULT_WORDS[result]).join(', ');
  const label = team ? `${team} form, oldest first: ${spoken}` : `Form, oldest first: ${spoken}`;
  const pips = results.map((result, index) => (
    <span
      key={`${result}-${index}`}
      aria-hidden
      className={cn(
        'inline-flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border font-mono text-[9px] font-semibold leading-none',
        RESULT_STYLES[result],
      )}
    >
      {result}
    </span>
  ));

  if (!onToggle) {
    return (
      <span
        role="img"
        aria-label={label}
        className={cn('inline-flex items-center gap-0.5 align-middle', className)}
      >
        {pips}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={label}
      aria-expanded={expanded ?? false}
      aria-controls={controls}
      className={cn(
        '-mx-1 inline-flex items-center gap-0.5 rounded-[5px] px-1 py-1 align-middle transition-colors',
        'cursor-pointer hover:bg-surface-elevated focus-visible:outline-none focus-visible:shadow-glow',
        expanded && 'bg-surface-elevated',
        className,
      )}
    >
      {pips}
    </button>
  );
}

export interface FormMatchesProps {
  /** As the API sends them: most recent **first**. */
  matches: FormMatch[];
  /** Whose results these are, for the list's screen-reader label. */
  team?: string;
  timezone: string;
  /** Matches the controlling `FormLine`'s `controls`. */
  id?: string;
  className?: string;
}

/**
 * The matches a form line is made of — opponent, orientation, score and date.
 *
 * Printed **oldest first**, against the usual newest-first habit of a results list, so
 * that the nth row is the nth pip. The whole point of the panel is to say what a
 * particular pip was, and a reader who has to reverse one list against the other to
 * find out has been given a puzzle instead of an answer.
 *
 * Goals are for-and-against from this club's point of view, so `2–1` is a win whether
 * the club was at home or away; `H`/`A` says which. That keeps the score readable
 * without colour, which is the same rule the pips follow.
 */
export function FormMatches({ matches, team, timezone, id, className }: FormMatchesProps) {
  if (matches.length === 0) return null;
  const oldestFirst = [...matches].reverse();

  return (
    <ul
      id={id}
      role="list"
      aria-label={team ? `${team} recent results, oldest first` : 'Recent results, oldest first'}
      className={cn(
        'flex flex-col rounded-md border border-border bg-surface-elevated/60 px-2 py-1',
        className,
      )}
    >
      {oldestFirst.map((match) => (
        <li
          key={match.match_id}
          className="flex items-center gap-2 border-b border-border/40 py-1 text-xs font-sans last:border-0"
          data-testid={`form-match-${match.match_id}`}
        >
          <span className="w-14 shrink-0 font-mono text-[10px] uppercase tracking-wide text-text-muted">
            {formatInstant(match.kickoff_utc, timezone, 'd MMM') ?? ''}
          </span>
          <span
            aria-hidden
            className="w-3 shrink-0 font-mono text-[10px] font-semibold text-text-muted"
          >
            {match.home ? 'H' : 'A'}
          </span>
          <span className="sr-only">{match.home ? 'home to' : 'away to'}</span>
          <span className="min-w-0 flex-1 truncate text-text-primary">{match.opponent}</span>
          <span className="sr-only">{RESULT_WORDS[match.result]}</span>
          <span
            className={cn(
              'shrink-0 font-mono text-xs font-semibold tabular-nums',
              RESULT_TEXT[match.result],
            )}
          >
            {match.goals_for}–{match.goals_against}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** `1` → `1st`. Ordinals read faster than a bare number beside a club name. */
export function ordinal(position: number): string {
  const lastTwo = position % 100;
  if (lastTwo >= 11 && lastTwo <= 13) return `${position}th`;
  const suffix = { 1: 'st', 2: 'nd', 3: 'rd' }[position % 10] ?? 'th';
  return `${position}${suffix}`;
}
