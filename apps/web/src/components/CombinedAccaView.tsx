import type { Coupon, CouponLeg, PickStatus } from '../lib/types';
import { Copy } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { EmptyState } from './EmptyState';
import { formatOdds, marketTag, outcomeLabel, pickStatusLabel } from '../lib/coupon';
import { useOddsFormat } from '../hooks/useOddsFormat';
import { cn } from '../lib/utils';

const STATUS_VARIANT: Record<PickStatus, 'success' | 'error' | 'muted' | 'default'> = {
  won: 'success',
  lost: 'error',
  void: 'muted',
  pending: 'default',
};

export function buildCouponShareText(coupon: Coupon): string {
  const lines = [
    `The Coupon: ${coupon.leg_count}-fold accumulator`,
    `Frozen combined odds: ${formatOdds(coupon.combined_odds)} (historical, from pick time)`,
    '',
    ...coupon.legs.map((leg, i) => {
      const selection = outcomeLabel(leg.market, leg.outcome, leg.home, leg.away);
      return `${i + 1}. ${selection} @ ${formatOdds(leg.odds)} - ${leg.home} v ${leg.away} (${leg.competition}, ${marketTag(leg.market)}) - ${leg.player_name}`;
    }),
    '',
    'Prices were frozen when each member picked. Check your book for current odds before placing anything.',
  ];
  return lines.join('\n');
}

/**
 * The combined per-leaderboard accumulator for a gameweek: every member's one
 * pick stacked into a single acca to reference on a real book. Presentation
 * only — the caller fetches GET /leagues/{slug}/coupon.
 */
export function CombinedAccaView({ coupon }: { coupon: Coupon }) {
  const oddsFormat = useOddsFormat();

  if (coupon.leg_count === 0) {
    return (
      <EmptyState
        title="No picks in yet"
        description="Once members start grabbing selections, they stack up here into one combined coupon."
      />
    );
  }

  const settled = coupon.status === 'settled';

  async function copyCouponText() {
    try {
      await navigator.clipboard.writeText(buildCouponShareText(coupon));
      toast.success('Coupon copied');
    } catch {
      toast.error('Could not copy coupon');
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Summary card */}
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
              {coupon.leg_count}-fold accumulator
            </p>
            <p className="mt-1 text-3xl font-semibold tabular-nums text-text-primary">
              {formatOdds(coupon.combined_odds, oddsFormat)}
            </p>
            <p className="mt-0.5 text-xs font-sans text-text-muted">
              frozen combined odds from pick time
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {settled && coupon.all_won !== null && (
              <Badge variant={coupon.all_won ? 'success' : 'muted'}>
                {coupon.all_won ? 'All legs won 🎉' : 'Not all legs landed'}
              </Badge>
            )}
            <Button type="button" variant="outline" size="sm" onClick={copyCouponText}>
              <Copy className="h-3.5 w-3.5" aria-hidden />
              Copy text
            </Button>
          </div>
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
  const oddsFormat = useOddsFormat();
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
          {leg.competition} · {leg.home} v {leg.away} · {leg.player_name}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5">
        <span className="font-mono text-sm tabular-nums text-text-primary">{formatOdds(leg.odds, oddsFormat)}</span>
        {settled && (
          <Badge variant={STATUS_VARIANT[leg.status]}>{pickStatusLabel(leg.status)}</Badge>
        )}
      </div>
    </li>
  );
}
