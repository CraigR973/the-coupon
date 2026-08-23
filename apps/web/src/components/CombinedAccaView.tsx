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

/** A leg's scoreline, or null when there is none to show. */
function scoreline(leg: CouponLeg): string | null {
  if (leg.home_goals == null || leg.away_goals == null) return null;
  return `${leg.home_goals}–${leg.away_goals}`;
}

/**
 * True when this leg's score is the state of play rather than the result (Batch 72).
 *
 * Defaults to *final*, so a deployed API that predates the field is read the way it has
 * always meant — Vercel ships this app on merge while the API waits for `/ship-prod`.
 */
function isLive(leg: CouponLeg): boolean {
  return leg.score_is_final === false;
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
  // A round being played carries scores that are not results. The API decides which —
  // it evaluates the same `in_play` rule the round ordering uses — and says so per leg,
  // so this reads the legs rather than second-guessing the status.
  const live = !settled && coupon.legs.some(isLive);

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
        {coupon.legs.map((leg, i) => (
          <LegRow
            key={`${leg.player_id}-${leg.fixture_id}`}
            leg={leg}
            index={i}
            settled={settled}
            showScore={settled || live}
            isMine={leg.player_id === myPlayerId}
          />
        ))}
      </ol>
    </div>
  );
}

function LegRow({
  leg,
  index,
  settled,
  showScore,
  isMine,
}: {
  leg: CouponLeg;
  index: number;
  settled: boolean;
  showScore: boolean;
  isMine: boolean;
}) {
  const oddsFormat = useOddsFormat();
  const selection = outcomeLabel(leg.market, leg.outcome, leg.home, leg.away);
  const score = showScore ? scoreline(leg) : null;
  const running = isLive(leg);
  return (
    <li
      className={cn(
        'flex items-center gap-3 rounded-lg border border-border bg-surface p-3',
        settled && leg.status === 'lost' && 'opacity-60',
        isMine && 'border-primary',
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
          {isMine && <Badge variant="accent">You</Badge>}
        </div>
        <p className="truncate text-xs font-sans text-text-muted">
          {leg.competition} · {leg.home} v {leg.away} · {leg.player_name}
        </p>
        {/* The result, not the outcome. Absent when the leg's fixture could not be
            resolved to a played match — the join fails open rather than guessing, so
            there is simply nothing here rather than a wrong scoreline. */}
        {score && (
          // A div rather than a paragraph: `Badge` renders a block, and a block inside a
          // <p> is invalid markup the browser silently rewrites.
          <div className="mt-0.5 flex items-center gap-2">
            <span className="font-mono text-xs tabular-nums text-text-secondary">
              <span className="sr-only">{running ? 'Score so far: ' : 'Final score: '}</span>
              {leg.home} {score} {leg.away}
            </span>
            {/* Said in words as well as colour: 2-1 at half time and 2-1 at full time
                are opposite news to somebody holding that pick. */}
            {running && <Badge variant="live">Live</Badge>}
          </div>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5">
        <span className="font-mono text-sm tabular-nums text-text-primary">{formatOdds(leg.odds, oddsFormat)}</span>
        {settled && (
          <Badge variant={STATUS_VARIANT[leg.status]}>{pickStatusLabel(leg.status)}</Badge>
        )}
        {settled && leg.points_awarded != null && (
          <span className="font-mono text-[11px] tabular-nums text-text-muted">
            {leg.points_awarded} pts
          </span>
        )}
      </div>
    </li>
  );
}
