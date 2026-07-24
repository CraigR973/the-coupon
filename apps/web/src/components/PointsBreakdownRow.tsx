export function PointsBreakdownRow({
  breakdown,
}: {
  breakdown: {
    result: number;
    goals: number;
    exact: number;
    total: number;
    // Knockout advancement (who-progresses) points. Omit for group matches so
    // the chip is hidden; pass it (even 0) on knockout matches to show it.
    advancement?: number;
  };
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {(
        [
          { label: 'Result', val: breakdown.result },
          { label: 'Goals', val: breakdown.goals },
          { label: 'Exact', val: breakdown.exact },
          ...(breakdown.advancement !== undefined
            ? [{ label: 'Advancement', val: breakdown.advancement }]
            : []),
        ] as const
      ).map(({ label, val }) => (
        <span key={label} className="flex items-center gap-1 font-sans text-xs">
          <span className={val > 0 ? 'text-success' : 'text-text-muted'}>
            {val > 0 ? '✓' : '✗'}
          </span>
          <span className="text-text-muted">{label}</span>
          <span
            className={`font-mono tabular-nums font-medium ${val > 0 ? 'text-primary' : 'text-text-muted'}`}
          >
            {val > 0 ? `+${val}` : '—'}
          </span>
        </span>
      ))}
      <span className="font-mono text-xs font-semibold text-primary tabular-nums ml-auto">
        {breakdown.total} pts
      </span>
    </div>
  );
}
