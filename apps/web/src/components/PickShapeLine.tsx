import type { Standing } from '@/lib/types';

/**
 * What kind of picks a member is making, in one line.
 *
 * Batch 70. The fields are optional because the API may not have shipped yet — Vercel
 * deploys this app from `main` on merge while the API waits for `/ship-prod` — so an
 * absent figure renders as nothing rather than as a zero.
 */
export interface PickShape {
  picks_played?: number;
  picks_priced?: number;
  cumulative_odds?: number;
  average_odds?: number | null;
  points_per_pick?: number | null;
  best_return?: number | null;
  longshot_picks?: number;
  favourite_picks?: number;
  longshot_odds?: number;
}

/** True when the API has sent enough of Batch 70's figures to be worth rendering. */
export function hasPickShape(shape: PickShape): boolean {
  return shape.average_odds != null || (shape.picks_priced ?? 0) > 0;
}

/**
 * **The denominators differ, and the reader has to be told.**
 *
 * `picks_played` counts void picks — a member whose fixture was postponed took part in
 * that round — and the odds figures do not, because a bet that never ran is not a price
 * they staked. A table that shows both without saying so is lying quietly, which is why
 * this note is a component rather than a comment: every surface that shows the figures
 * shows the note with them.
 */
export function VoidDenominatorNote({ shape }: { shape: PickShape }) {
  const played = shape.picks_played ?? 0;
  const priced = shape.picks_priced ?? 0;
  if (played === priced) return null;
  return (
    <p className="mt-1 font-sans text-[11px] text-text-muted">
      Odds figures cover the {priced} pick{priced === 1 ? '' : 's'} that ran; {played - priced}{' '}
      void {played - priced === 1 ? 'pick counts' : 'picks count'} as played but is not priced.
    </p>
  );
}

/**
 * The compact form: the one figure, named.
 *
 * Batch 73 dropped the longshot split this used to carry — `avg 2.67 · 0 at 3.00+` — on
 * the owner's call. Two figures in a line this size read as a ratio rather than as two
 * unrelated counts, and the second was usually zero, which made the first harder to read
 * for nothing. `avg` alone was also ambiguous on a table whose other columns are points:
 * naming it `avg odds selected` says which average it is.
 *
 * The split is not gone from the product — `PickShapeGrid` on the player profile still
 * carries `Longshots (n.nn+)` and `Favourites`, which is the surface with room to explain
 * them.
 */
export function PickShapeLine({ shape }: { shape: PickShape }) {
  if (!hasPickShape(shape)) return null;
  return (
    <span className="font-sans text-xs text-text-muted">
      avg odds selected {shape.average_odds?.toFixed(2) ?? '—'}
    </span>
  );
}

/** The full set, for the profile. */
export function PickShapeGrid({ shape }: { shape: Standing | PickShape }) {
  if (!hasPickShape(shape)) return null;
  const line = shape.longshot_odds ?? 3;
  return (
    <div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <Figure label="Cumulative odds" value={shape.cumulative_odds?.toFixed(2)} />
        <Figure label="Average odds" value={shape.average_odds?.toFixed(2)} />
        <Figure label="Points per pick" value={shape.points_per_pick?.toFixed(2)} />
        <Figure label="Best return" value={shape.best_return != null ? `${shape.best_return} pts` : undefined} />
        <Figure label={`Longshots (${line.toFixed(2)}+)`} value={shape.longshot_picks} />
        <Figure label="Favourites" value={shape.favourite_picks} />
      </dl>
      <VoidDenominatorNote shape={shape} />
    </div>
  );
}

function Figure({ label, value }: { label: string; value: string | number | undefined }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">{label}</dt>
      <dd className="font-mono text-sm tabular-nums text-text-primary">{value ?? '—'}</dd>
    </div>
  );
}
