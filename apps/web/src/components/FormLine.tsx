import type { FormResult } from '../lib/types';
import { cn } from '../lib/utils';

const RESULT_STYLES: Record<FormResult, string> = {
  W: 'border-success/40 bg-success/20 text-success',
  D: 'border-border bg-surface-elevated text-text-muted',
  L: 'border-error/40 bg-error/20 text-error',
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
 */
export function FormLine({ form, team, className }: FormLineProps) {
  const results = [...form].filter(isFormResult);
  if (results.length === 0) return null;

  const spoken = results.map((result) => RESULT_WORDS[result]).join(', ');
  const label = team ? `${team} form, oldest first: ${spoken}` : `Form, oldest first: ${spoken}`;

  return (
    <span
      role="img"
      aria-label={label}
      className={cn('inline-flex items-center gap-0.5 align-middle', className)}
    >
      {results.map((result, index) => (
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
      ))}
    </span>
  );
}

/** `1` → `1st`. Ordinals read faster than a bare number beside a club name. */
export function ordinal(position: number): string {
  const lastTwo = position % 100;
  if (lastTwo >= 11 && lastTwo <= 13) return `${position}th`;
  const suffix = { 1: 'st', 2: 'nd', 3: 'rd' }[position % 10] ?? 'th';
  return `${position}${suffix}`;
}
