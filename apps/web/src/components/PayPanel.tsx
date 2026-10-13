import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ExternalLink, PiggyBank, Wallet } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { keys } from '@/lib/queryKeys';
import { roundName } from '@/lib/coupon';
import { formatPence } from '@/lib/money';
import { formatCalendarDate } from '@/lib/time';
import type { AdultConfirmation, RoundFeeStatus } from '@/lib/types';
import { Button } from '@/components/ui/button';

/**
 * What a member owes before they can pick, and how to pay it (Batch 206, ADR 0009).
 *
 * A league that charges a fee refuses a pick from anyone who is not paid up — £1 a week,
 * owed whether they pick or not, so a missed week rolls over into the next. Without this
 * panel that refusal is a toast the member cannot act on. Three states:
 *
 * * **owed** — the amount owed now, every round behind it listed so a £2 is never a
 *   surprise, and the league's payment link as a button. The link waits for the one-time
 *   "I'm 18 or over" confirmation (ADR 0009's fourth rule); the API withholds it until
 *   then, so this is the screen asking, not the screen hiding it.
 * * **credit** — paid up with money left over, which covers the weeks ahead.
 * * **paid** — paid up exactly.
 *
 * The money itself moves outside the app. The organiser records it, and the next read of
 * the round says the member is paid up — so the panel says that too, rather than leaving
 * someone who has just paid wondering why they still cannot pick.
 *
 * Rendered only when the round carries a fee status, so a league without a fee shows
 * exactly what it did before.
 */
export function PayPanel({
  slug,
  gameweekId,
  fee,
}: {
  slug: string;
  /** The round on screen, so its own line reads "This round" rather than a rolled-over week. */
  gameweekId: string;
  fee: RoundFeeStatus;
}) {
  if (fee.owed_pence > 0) {
    return <OwedPanel slug={slug} gameweekId={gameweekId} fee={fee} />;
  }
  if (fee.credit_pence > 0) {
    return (
      <div
        role="status"
        data-testid="pay-panel"
        data-state="credit"
        className="mb-4 flex items-start gap-2 rounded-lg border border-border bg-surface px-4 py-3 text-sm font-sans text-text-primary"
      >
        <PiggyBank className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
        <p>
          <strong className="font-semibold">You’re paid up, with {formatPence(fee.credit_pence)} in credit.</strong>{' '}
          <span className="text-text-secondary">It goes towards the weeks ahead.</span>
        </p>
      </div>
    );
  }
  return (
    <div
      role="status"
      data-testid="pay-panel"
      data-state="paid"
      className="mb-4 flex items-start gap-2 rounded-lg border border-border bg-surface px-4 py-3 text-sm font-sans text-text-primary"
    >
      <Wallet className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
      <p>You’re paid up for this round.</p>
    </div>
  );
}

function OwedPanel({
  slug,
  gameweekId,
  fee,
}: {
  slug: string;
  gameweekId: string;
  fee: RoundFeeStatus;
}) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const rolledOver = fee.owed_rounds.filter((round) => round.gameweek_id !== gameweekId);
  const thisRound = fee.owed_rounds.find((round) => round.gameweek_id === gameweekId);

  async function confirmAdult() {
    setConfirming(true);
    try {
      await apiFetch<AdultConfirmation>(`/api/v1/leagues/${slug}/adult-confirmation`, {
        method: 'POST',
      });
      // The link rides on the round payload and appears only once the API knows; re-read
      // every round of this league so the button below has something to open.
      await queryClient.invalidateQueries({ queryKey: keys.gameweek.all(slug) });
    } catch (err) {
      toast.error('Could not confirm', {
        description: err instanceof Error && err.message ? err.message : 'Try again shortly.',
      });
    } finally {
      setConfirming(false);
    }
  }

  return (
    <section
      aria-labelledby="pay-panel-heading"
      data-testid="pay-panel"
      data-state="owed"
      className="mb-4 rounded-lg border border-warning/30 bg-warning/[0.08] dark:bg-warning/15 px-4 py-3 font-sans text-text-primary"
    >
      <h2 id="pay-panel-heading" className="text-sm font-semibold">
        Pay <span data-testid="pay-panel-owed">{formatPence(fee.owed_pence)}</span> to pick this
        round
      </h2>
      <p className="mt-1 text-xs text-text-secondary">
        This league is {formatPence(fee.entry_fee_pence)} a week, owed every week whether you
        pick or not, and you need to be paid up to pick.
      </p>

      <ul className="mt-2 flex flex-col gap-1 text-xs sm:max-w-sm" data-testid="pay-panel-rounds">
        {rolledOver.map((round) => (
          <li
            key={round.gameweek_id}
            data-testid="pay-panel-rolled-over"
            className="flex items-baseline justify-between gap-3"
          >
            <span className="min-w-0 truncate">
              {roundName(
                round.number,
                formatCalendarDate(round.starts_on, 'EEE d MMM'),
                round.season_week,
              )}
              <span className="text-text-muted"> · rolled over</span>
            </span>
            <span className="shrink-0 font-mono tabular-nums">{formatPence(round.amount_pence)}</span>
          </li>
        ))}
        {thisRound && (
          <li className="flex items-baseline justify-between gap-3">
            <span>This round</span>
            <span className="shrink-0 font-mono tabular-nums">
              {formatPence(thisRound.amount_pence)}
            </span>
          </li>
        )}
      </ul>

      <div className="mt-3">
        {!fee.has_payment_link ? (
          <p className="text-xs text-text-secondary" data-testid="pay-panel-no-link">
            There’s no payment link for this league yet — ask the organiser how to pay.
          </p>
        ) : !fee.adult_confirmed ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-text-secondary">
              Before we show the payment link, confirm you’re 18 or over. You only do this
              once.
            </p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="shrink-0"
              disabled={confirming}
              onClick={() => void confirmAdult()}
            >
              {confirming ? 'Confirming…' : 'I’m 18 or over'}
            </Button>
          </div>
        ) : fee.payment_link_url ? (
          <Button asChild size="sm" className="w-full sm:w-auto">
            <a href={fee.payment_link_url} target="_blank" rel="noopener noreferrer">
              Pay {formatPence(fee.owed_pence)}
              <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          </Button>
        ) : null}
      </div>
      <p className="mt-2 text-caption text-text-muted">
        Paying opens the league’s payment page outside the app. You can pick once the
        organiser has recorded it.
      </p>
    </section>
  );
}
