import { Copy } from 'lucide-react';
import { toast } from 'sonner';
import type { Coupon, OddsFormat } from '../lib/types';
import { formatOdds, type RoundPhase } from '../lib/coupon';
import { COUPON_SECTION_ID } from '../lib/leagues';
import { buildCouponShareText, buildSettledResultShareText } from '../lib/share';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { EmptyState } from './EmptyState';
import { isLive, PickRow, type PickEntry } from './PickRow';

export interface CouponSectionProps {
  /** The round's combined coupon, or `undefined` while it has none to show. */
  coupon: Coupon | undefined;
  /** Everybody in the round — claims first, then the members still missing. */
  entries: PickEntry[];
  phase: RoundPhase;
  memberCount: number;
  /** What this round is called, for the heading and the pasted text. */
  roundLabel: string;
  oddsFormat: OddsFormat;
}

/**
 * The league's picks stacked into one coupon: the fold, the frozen combined price, the
 * text somebody pastes into a bookmaker, and every member's leg.
 *
 * This was its own screen — `Combined coupon` — until Batch 105, and being a screen is
 * what was wrong with it. It answers a question about the round the member is already
 * looking at, so it now answers it in place, at `#coupon`, and how loudly it speaks
 * depends on the round: a coupon still being filled in is a list of what has been taken,
 * a complete one is the thing you copy, and a settled one is the result.
 *
 * **A round the deadline caught says so.** `leg_count` alone cannot tell a three-member
 * league that took three picks from a four-member league that took three, and the second
 * one is not a complete coupon however much it looks like one on the screen.
 */
export function CouponSection({
  coupon,
  entries,
  phase,
  memberCount,
  roundLabel,
  oddsFormat,
}: CouponSectionProps) {
  const settled = phase === 'settled';
  const incomplete = phase === 'locked_incomplete';
  // A round being played carries scores that are not results. The API decides which —
  // it evaluates the same `in_play` rule the round ordering uses — and says so per leg,
  // so this reads the legs rather than second-guessing the status.
  const live = !settled && entries.some(isLive);
  const landed = coupon ? coupon.legs.filter((leg) => leg.status === 'won').length : 0;
  const missing = coupon ? memberCount - coupon.leg_count : 0;

  // The heading names the section; what state the round is in is `RoundStatus`'s job, a
  // few centimetres above. Saying "Coupon complete" in both places would be the same
  // duplication, on the same screen, that this batch exists to remove.
  const heading = settled ? 'Result' : 'The coupon';

  async function copyShareText() {
    if (!coupon) return;
    const context = { roundLabel, memberCount };
    try {
      await navigator.clipboard.writeText(
        settled
          ? buildSettledResultShareText(coupon, context)
          : buildCouponShareText(coupon, context),
      );
      toast.success(settled ? 'Result copied' : 'Coupon copied');
    } catch {
      toast.error(settled ? 'Could not copy result' : 'Could not copy coupon');
    }
  }

  return (
    <section
      id={COUPON_SECTION_ID}
      tabIndex={-1}
      aria-labelledby="coupon-section-heading"
      className="scroll-mt-4 focus-visible:outline-none focus-visible:shadow-glow"
      data-testid="coupon-section"
    >
      <h2
        id="coupon-section-heading"
        className="mb-2 font-mono text-[11px] uppercase tracking-[0.2em] text-text-primary"
      >
        {heading}
      </h2>

      {live && (
        <p className="mb-3 font-sans text-xs text-text-muted">
          Scores are from matches still being played and are not results. Points are awarded
          when the round settles.
        </p>
      )}

      {coupon && coupon.leg_count > 0 && (
        <div className="mb-3 rounded-lg border border-border bg-surface p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
                {settled
                  ? `${landed} of ${coupon.leg_count} landed`
                  : `${coupon.leg_count}-fold accumulator`}
              </p>
              <p className="mt-1 text-3xl font-semibold tabular-nums text-text-primary">
                {formatOdds(coupon.combined_odds, oddsFormat)}
              </p>
              {/* The one place this surface states it. The pasted text says it once too,
                  at the bottom, and nothing else on the screen repeats it. */}
              <p className="mt-0.5 break-words font-sans text-xs text-text-muted">
                {incomplete && missing > 0
                  ? `${missing} of ${memberCount} never picked · odds frozen at pick time`
                  : 'Combined odds, frozen at pick time'}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {settled && coupon.all_won !== null && (
                <Badge variant={coupon.all_won ? 'success' : 'muted'}>
                  {coupon.all_won ? 'All legs won 🎉' : 'Not all legs landed'}
                </Badge>
              )}
              <Button type="button" variant="outline" size="sm" onClick={copyShareText}>
                <Copy className="h-3.5 w-3.5" aria-hidden />
                {settled ? 'Copy result' : 'Copy text'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {entries.length === 0 ? (
        <EmptyState
          title="No picks in yet"
          description="Once members start grabbing selections, they stack up here into one combined coupon."
        />
      ) : (
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
      )}
    </section>
  );
}
