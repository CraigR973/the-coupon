import { useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "./ui/button";
import { formatCalendarDate, formatInstant } from "../lib/time";
import type { WeekFee } from "../lib/twoGameTypes";
const money = (pence: number) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(
    pence / 100,
  );
/**
 * The week's payment as a strip at the top of both game screens (Batch 238): what is
 * owed, the payment link and a status check stay in view, and the detail folds away.
 * A `#payment` link opens the detail, scrolls the strip into view and focuses it.
 */
export function WeekFeePanel({
  fee,
  onRefresh,
}: {
  fee: WeekFee;
  onRefresh: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  const location = useLocation();
  const [open, setOpen] = useState(location.hash === "#payment");
  useEffect(() => {
    if (location.hash === "#payment") {
      setOpen(true);
      panel.current?.scrollIntoView?.({ block: "start" });
      panel.current?.focus({ preventScroll: true });
    }
  }, [location.hash, location.key, fee.week_id]);
  const owed = !fee.paid_through;
  return (
    <section
      ref={panel}
      id="payment"
      tabIndex={-1}
      aria-labelledby="week-payment-heading"
      className="rounded-xl border border-border bg-surface px-4 py-3 space-y-3 scroll-mt-20"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 space-y-0.5">
          <h2 id="week-payment-heading" className="text-sm font-semibold">
            Payment for {formatCalendarDate(fee.week_label, "d MMM")}
          </h2>
          <p role="status" className="font-sans text-sm">
            {owed
              ? `${money(fee.amount_owed_pence)} owed through this week`
              : "Paid through this week"}
          </p>
          <p className="font-sans text-xs text-text-secondary">
            One £1 a week covers both games.
          </p>
        </div>
        {/* transition-none: the strip leads the screen, and a theme flip must not leave a
            button mid-fade (Batch 238; the accessibility scan catches the in-between colour). */}
        <div className="flex flex-wrap items-center gap-2">
          {fee.payment_url && owed && (
            <Button asChild className="transition-none">
              <a href={fee.payment_url} target="_blank" rel="noopener noreferrer">
                {fee.amount_owed_pence === 100
                  ? "Pay £1"
                  : `Pay ${money(fee.amount_owed_pence)}`}
              </a>
            </Button>
          )}
          <Button variant="outline" onClick={onRefresh} className="transition-none">
            Check payment status
          </Button>
          <Button
            variant="ghost"
            aria-expanded={open}
            aria-controls="week-payment-details"
            onClick={() => setOpen((value) => !value)}
            className="transition-none"
          >
            Details
            <ChevronDown
              aria-hidden="true"
              className={`size-4 transition-transform ${open ? "rotate-180" : ""}`}
            />
          </Button>
        </div>
      </div>
      <div id="week-payment-details" hidden={!open} className="space-y-3">
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
      </div>
    </section>
  );
}
