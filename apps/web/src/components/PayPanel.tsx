import { ExternalLink, PiggyBank, Wallet } from 'lucide-react';
import { roundName } from '@/lib/coupon';
import { formatPence } from '@/lib/money';
import { formatCalendarDate } from '@/lib/time';
import type { RoundFeeStatus } from '@/lib/types';
import { Button } from '@/components/ui/button';

/**
 * What a member owes before they can pick, and how to pay it (Batch 206, ADR 0009).
 *
 * A league that charges a fee refuses a pick from anyone who is not paid up — £1 a week,
 * owed whether they pick or not, so a missed week rolls over into the next. Without this
 * panel that refusal is a toast the member cannot act on. Three states:
 *
 * * **owed** — the amount owed now, every round behind it listed so a £2 is never a
 *   surprise (and any earlier charge that is not a round as one "Earlier balance" line,
 *   Batch 212), and the league's payment link as a button straight away. Batch 209 removed
 *   the "I'm 18 or over" step: under ADR 0009's amended fourth rule the owner, not the
 *   app, makes sure members are adults.
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
  gameweekId,
  fee,
}: {
  /** The round on screen, so its own line reads "This round" rather than a rolled-over week. */
  gameweekId: string;
  fee: RoundFeeStatus;
}) {
  if (fee.owed_pence > 0) {
    return <OwedPanel gameweekId={gameweekId} fee={fee} />;
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
  gameweekId,
  fee,
}: {
  gameweekId: string;
  fee: RoundFeeStatus;
}) {
  const rolledOver = fee.owed_rounds.filter((round) => round.gameweek_id !== gameweekId);
  const thisRound = fee.owed_rounds.find((round) => round.gameweek_id === gameweekId);
  const earlierBalance = fee.earlier_balance_pence ?? 0;

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
        {/* Batch 212. A charge that is not a round — what was owed before the app, say —
            is one line, so the lines add up to what the heading asks for. Never the
            organiser's note. */}
        {earlierBalance > 0 && (
          <li
            data-testid="pay-panel-earlier-balance"
            className="flex items-baseline justify-between gap-3"
          >
            <span>Earlier balance</span>
            <span className="shrink-0 font-mono tabular-nums">{formatPence(earlierBalance)}</span>
          </li>
        )}
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
