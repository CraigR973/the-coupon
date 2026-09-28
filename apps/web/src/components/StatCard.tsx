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
        compact ? 'gap-1 px-3 py-2.5' : 'gap-2 p-4',
        className,
      )}
    >
      <Label className="truncate font-mono text-caption uppercase tracking-[0.25em] text-text-muted">
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
