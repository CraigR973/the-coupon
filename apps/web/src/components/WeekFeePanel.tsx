import { useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, ChevronDown, RefreshCw } from "lucide-react";
import { Button } from "./ui/button";
import { formatCalendarDate, formatInstant } from "../lib/time";
import type { WeekFee } from "../lib/twoGameTypes";
import { cn } from "../lib/utils";
const money = (pence: number) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(
    pence / 100,
  );
/**
 * The week's payment as a strip at the top of both game screens (Batch 238): what is
 * owed, the payment link and a status check stay in view, and the detail folds away.
 * A `#payment` link opens the detail, scrolls the strip into view and focuses it.
 *
 * Batch 247 (owner, 25 Nov 2026). A paid week is one line: a tick, the status, and the
 * status check and Details as icon buttons; the heading and the £1 note show with the
 * detail. Owed, the text stacks above its buttons on a phone. The strip used to be one
 * wrapping row whose text column had a zero flex basis, so once the Pay button went the
 * row never wrapped and the text shrank to about 40px, a word a line.
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
  const heading = `Payment for ${formatCalendarDate(fee.week_label, "d MMM")}`;
  const note = (
    <p className="font-sans text-xs text-text-secondary">
      One £1 a week covers both games.
    </p>
  );
  // transition-none on every button: the strip leads the screen, and a theme flip must not
  // leave a button mid-fade (Batch 238; the accessibility scan catches the in-between colour).
  const toggle = (
    <Button
      variant="ghost"
      size={owed ? "default" : "icon"}
      aria-label={owed ? undefined : "Details"}
      aria-expanded={open}
      aria-controls="week-payment-details"
      onClick={() => setOpen((value) => !value)}
      className="transition-none"
    >
      {owed && "Details"}
      <ChevronDown
        aria-hidden="true"
        className={`size-4 transition-transform ${open ? "rotate-180" : ""}`}
      />
    </Button>
  );
  return (
    <section
      ref={panel}
      id="payment"
      tabIndex={-1}
      aria-labelledby="week-payment-heading"
      className={cn(
        "rounded-xl border border-border bg-surface px-4 scroll-mt-20",
        owed ? "py-3" : "py-1",
      )}
    >
      {owed ? (
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4 sm:gap-y-2">
          <div className="min-w-0 space-y-0.5 sm:flex-[1_1_14rem]">
            <h2 id="week-payment-heading" className="text-sm font-semibold">
              {heading}
            </h2>
            <p role="status" className="font-sans text-sm">
              {`${money(fee.amount_owed_pence)} owed through this week`}
            </p>
            {note}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {fee.payment_url && (
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
            {toggle}
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <h2
              id="week-payment-heading"
              className={open ? "pt-1.5 text-sm font-semibold" : "sr-only"}
            >
              {heading}
            </h2>
            <p role="status" className="font-sans text-sm">
              Paid through this week
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Check payment status"
            title="Check payment status"
            onClick={onRefresh}
            className="transition-none"
          >
            <RefreshCw aria-hidden="true" className="size-4" />
          </Button>
          {toggle}
        </div>
      )}
      <div
        id="week-payment-details"
        hidden={!open}
        className={cn("space-y-3", owed ? "mt-3" : "mb-2 mt-1")}
      >
        {!owed && note}
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
