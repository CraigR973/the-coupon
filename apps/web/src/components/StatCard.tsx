/**
 * One headline figure on a profile.
 *
 * Shared by the league-scoped profile and the career one so the two read as the
 * same object seen at two altitudes — they answer the same question about the
 * same member, and a member who has just tapped through from one to the other
 * should not have to re-learn the layout.
 */
export function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
      <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
        {label}
      </span>
      <span className="font-mono text-2xl font-semibold leading-none tabular-nums text-primary">
        {value}
      </span>
    </div>
  );
}
