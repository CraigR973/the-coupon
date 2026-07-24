import { matchResultPhases, type MatchResultLike } from '../lib/matchResult';
import { cn } from '../lib/utils';

interface MatchResultProps {
  match: MatchResultLike;
  /** Applied to the score element (single-phase) or the stacked block (multi-phase). */
  className?: string;
}

/**
 * A completed match's scoreline. Decided inside 90 minutes → a bare "H – A", so
 * it drops into existing inline layouts unchanged. Went to extra time or
 * penalties → a small stacked block labelled 90' / AET / Pens. Renders nothing
 * when there is no result yet.
 */
export function MatchResult({ match, className }: MatchResultProps) {
  const phases = matchResultPhases(match);
  if (phases.length === 0) return null;

  if (phases.length === 1) {
    return (
      <span className={className}>
        {phases[0].home} – {phases[0].away}
      </span>
    );
  }

  return (
    <span
      className={cn('inline-flex flex-col items-center gap-0.5 leading-tight', className)}
      data-testid="match-result-phases"
    >
      {phases.map((p) => (
        <span key={p.label} className="flex items-baseline gap-1.5">
          <span className="w-8 shrink-0 text-right font-mono text-[0.7em] uppercase tracking-wide text-text-muted">
            {p.label}
          </span>
          <span>
            {p.home} – {p.away}
          </span>
        </span>
      ))}
    </span>
  );
}
