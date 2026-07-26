import type { Coupon, CouponLeg, PickStatus } from '../lib/types';
import { Badge } from './ui/badge';
import { EmptyState } from './EmptyState';
import { formatOdds, marketTag, outcomeLabel, pickStatusLabel } from '../lib/coupon';
import { cn } from '../lib/utils';

const STATUS_VARIANT: Record<PickStatus, 'success' | 'error' | 'muted' | 'default'> = {
  won: 'success',
  lost: 'error',
  void: 'muted',
  pending: 'default',
};

/**
 * The combined per-leaderboard accumulator for a gameweek: every member's one
 * pick stacked into a single acca to reference on a real book. Presentation
 * only — the caller fetches GET /leagues/{slug}/coupon.
 */
export function CombinedAccaView({ coupon }: { coupon: Coupon }) {
  if (coupon.leg_count === 0) {
    return (
      <EmptyState
        title="No picks in yet"
        description="Once members start grabbing selections, they stack up here into one combined coupon."
      />
    );
  }

  const settled = coupon.status === 'settled';

  return (
    <div className="flex flex-col gap-4">
      {/* Summary card */}
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
              {coupon.leg_count}-fold accumulator
            </p>
            <p className="mt-1 text-3xl font-semibold tabular-nums text-text-primary">
              {formatOdds(coupon.combined_odds)}
            </p>
            <p className="mt-0.5 text-xs font-sans text-text-muted">combined odds</p>
          </div>
          {settled && coupon.all_won !== null && (
            <Badge variant={coupon.all_won ? 'success' : 'muted'}>
              {coupon.all_won ? 'All legs won 🎉' : 'Not all legs landed'}
            </Badge>
          )}
        </div>
      </div>

      {/* Legs */}
      <ol className="flex flex-col gap-2">
        {coupon.legs.map((leg, i) => (
          <LegRow key={`${leg.player_id}-${leg.fixture_id}`} leg={leg} index={i} settled={settled} />
        ))}
      </ol>
    </div>
  );
}

function LegRow({ leg, index, settled }: { leg: CouponLeg; index: number; settled: boolean }) {
  const selection = outcomeLabel(leg.market, leg.outcome, leg.home, leg.away);
  return (
    <li
      className={cn(
        'flex items-center gap-3 rounded-lg border border-border bg-surface p-3',
        settled && leg.status === 'lost' && 'opacity-60',
      )}
      data-testid={`acca-leg-${index}`}
    >
      <span className="w-5 shrink-0 text-center font-mono text-xs text-text-muted tabular-nums">
        {index + 1}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-sans font-medium text-text-primary">{selection}</p>
          <Badge variant="muted">{marketTag(leg.market)}</Badge>
        </div>
        <p className="truncate text-xs font-sans text-text-muted">
          {leg.home} v {leg.away} · {leg.player_name}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5">
        <span className="font-mono text-sm tabular-nums text-text-primary">{formatOdds(leg.odds)}</span>
        {settled && (
          <Badge variant={STATUS_VARIANT[leg.status]}>{pickStatusLabel(leg.status)}</Badge>
        )}
      </div>
    </li>
  );
}
