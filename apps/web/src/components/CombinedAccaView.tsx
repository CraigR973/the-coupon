import type { Coupon } from '../lib/types';
import { Copy } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { EmptyState } from './EmptyState';
import { entriesFromLegs, isLive, PickRow } from './PickRow';
import { formatOdds, marketTag, outcomeLabel } from '../lib/coupon';
import { useOddsFormat } from '../hooks/useOddsFormat';

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
 *
 * On a **settled** round this is the result rather than the coupon (Batch 67): each leg
 * shows the scoreline its fixture finished, the points it scored, and the reader's own
 * leg is marked, so "how the week went" and "how I did" are one glance rather than two
 * screens. `myPlayerId` is a prop rather than a `useAuth()` call so this stays a pure
 * presentation component.
 *
 * Batch 78 moved the leg itself into `PickRow`, which the pick screen's roster also
 * draws. What is left here is what a *coupon* is and a roster is not: the fold, the
 * combined price, and the text somebody pastes into a bookmaker.
 */
export function CombinedAccaView({ coupon, myPlayerId }: { coupon: Coupon; myPlayerId?: string }) {
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
  const entries = entriesFromLegs(coupon.legs, myPlayerId);
  // A round being played carries scores that are not results. The API decides which —
  // it evaluates the same `in_play` rule the round ordering uses — and says so per leg,
  // so this reads the legs rather than second-guessing the status.
  const live = !settled && entries.some(isLive);

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
      {live && (
        <p className="font-sans text-xs text-text-muted">
          Scores are from matches still being played and are not results. Points are
          awarded when the round settles.
        </p>
      )}

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
        {entries.map((entry, i) => (
          <PickRow
            key={`${entry.player_id}-${i}`}
            entry={entry}
            oddsFormat={oddsFormat}
            lead="selection"
            index={i}
            showScore={settled || live}
            settled={settled}
            testId={`acca-leg-${i}`}
          />
        ))}
      </ol>
    </div>
  );
}
