import { useLocation } from "react-router-dom";
import { useEffect, useRef } from "react";
import { Button } from "./ui/button";
import { formatCalendarDate, formatInstant } from "../lib/time";
import type { WeekFee } from "../lib/twoGameTypes";
const money = (pence: number) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(
    pence / 100,
  );
export function WeekFeePanel({
  fee,
  onRefresh,
}: {
  fee: WeekFee;
  onRefresh: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  const location = useLocation();
  useEffect(() => {
    if (location.hash === "#payment") {
      panel.current?.scrollIntoView({ block: "start" });
      panel.current?.focus({ preventScroll: true });
    }
  }, [location.hash, location.key, fee.week_id]);
  return (
    <section
      ref={panel}
      id="payment"
      tabIndex={-1}
      aria-labelledby="week-payment-heading"
      className="rounded-xl border border-border bg-surface p-4 space-y-3 scroll-mt-20"
    >
      <h2 id="week-payment-heading" className="text-lg font-semibold">
        Payment for {formatCalendarDate(fee.week_label, "d MMM")}
      </h2>
      <p role="status">
        {fee.paid_through
          ? "Paid through this week"
          : `${money(fee.amount_owed_pence)} owed through this week`}
      </p>
      <p className="text-sm text-text-secondary">
        £1 is owed each Monday-to-Monday London week, regardless of
        participation, fixtures or suspension. Payments clear the oldest fees
        first.
      </p>
      <p className="text-sm">
        {formatInstant(fee.billing_starts_at, "Europe/London", "d MMM HH:mm")}{" "}
        to {formatInstant(fee.billing_ends_at, "Europe/London", "d MMM HH:mm")}{" "}
        London time.
      </p>
      {fee.obligations.length > 0 && (
        <ul className="space-y-1">
          {fee.obligations.map((due, index) => (
            <li key={`${due.week_label ?? "earlier"}-${index}`}>
              {due.week_label
                ? formatCalendarDate(due.week_label, "d MMM")
                : "Earlier balance"}
              : {money(due.remaining_pence)}
            </li>
          ))}
        </ul>
      )}
      <p className="text-sm">
        Pooled credit after recorded fees: {money(fee.pooled_credit_pence)}.
      </p>
      <div className="flex flex-wrap gap-3">
        {fee.payment_url && !fee.paid_through && (
          <Button asChild>
            <a href={fee.payment_url} target="_blank" rel="noopener noreferrer">
              Open league payment link
            </a>
          </Button>
        )}
        <Button variant="outline" onClick={onRefresh}>
          Check payment status
        </Button>
      </div>
    </section>
  );
}
