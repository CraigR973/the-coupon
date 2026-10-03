/**
 * One headline figure on a profile.
 *
 * Shared by the league-scoped profile and the career one so the two read as the
 * same object seen at two altitudes — they answer the same question about the
 * same member, and a member who has just tapped through from one to the other
 * should not have to re-learn the layout.
 */
import { cn } from '../lib/utils';

interface StatCardProps {
  label: string;
  value: string | number;
  compact?: boolean;
  definition?: boolean;
  className?: string;
  valueClassName?: string;
}

export function StatCard({
  label,
  value,
  compact = false,
  definition = false,
  className,
  valueClassName,
}: StatCardProps) {
  const Label = definition ? 'dt' : 'span';
  const Value = definition ? 'dd' : 'span';

  return (
    <div
      className={cn(
        'flex flex-col rounded-lg border border-border bg-surface',
        // Compact cards sit three to a phone-width hero: labels may wrap, so the figures
        // are held to the bottom edge and stay level whichever label takes two lines.
        compact ? 'justify-between gap-1 px-2.5 py-2.5 sm:px-3' : 'gap-2 p-4',
        className,
      )}
    >
      <Label
        className={cn(
          'font-mono text-caption uppercase text-text-muted',
          // Batch 170. `truncate` cut "Picks won" and "Win rate" at 390 and even "Points" at
          // 320. Compact labels wrap instead, and below `sm` they track at the WCAG
          // text-spacing value (0.12em), so the longest single word fits at 320 with or
          // without that override.
          compact ? 'tracking-[0.12em] sm:tracking-[0.25em]' : 'truncate tracking-[0.25em]',
        )}
      >
        {label}
      </Label>
      <Value
        className={cn(
          'font-mono font-semibold leading-none tabular-nums',
          compact ? 'text-xl' : 'text-2xl',
          valueClassName ?? 'text-primary',
        )}
      >
        {value}
      </Value>
    </div>
  );
}
