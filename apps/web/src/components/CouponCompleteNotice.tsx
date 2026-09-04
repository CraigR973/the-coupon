import { CheckCircle2, X } from 'lucide-react';

/**
 * The hand-off the member who fills the coupon gets, and nobody else. Batch 108.
 *
 * **Why it is a notice and not a toast.** Every other outcome of a submission is news —
 * you grabbed it, someone beat you, it did not send — and news is what a toast is for.
 * This one is a *job*: the round is now worth copying and placing, and the person who
 * completed it is the one holding the phone. A message that disappears after four seconds
 * would be the wrong shape for the only moment in the week when there is something to do
 * next, so this stays until it is taken or dismissed. `OutstandingPickNotice` is the same
 * argument about a different state.
 *
 * **It does not touch the clipboard.** The action opens the round's copy section and
 * leaves the copying to the control that lives there, which the member presses
 * themselves. Writing to the clipboard off the back of a pick would mean a submission
 * silently replacing whatever they had copied — and browsers are right to require a
 * gesture for it. The label says "open and copy" because that is the errand; the opening
 * is this button's half of it.
 *
 * The wording leads with the same four words as the push Batch 107 sends
 * (`… — all picks are in`), so a member who sees both does not have to work out that they
 * are about the same event.
 */
export function CouponCompleteNotice({
  memberCount,
  onOpen,
  onDismiss,
}: {
  /** Both halves of the `12/12` the league's push quotes, when it is worth printing. */
  memberCount: number;
  /** Open the completed round's copy section. Must not write to the clipboard. */
  onOpen: () => void;
  onDismiss: () => void;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="coupon-complete-notice"
      className="flex flex-col gap-2 rounded-lg border border-success/50 bg-success/10 p-3 text-text-primary sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="flex items-start gap-2 text-xs font-sans">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
        <span>
          <strong className="font-medium">All picks are in.</strong> You were the last to
          pick{memberCount > 0 ? ` — that’s ${memberCount}/${memberCount}` : ''}, so the
          coupon is complete and ready to place.
        </span>
      </p>
      <span className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={onOpen}
          data-testid="coupon-complete-open"
          className="rounded-md border border-success/60 px-3 py-1.5 text-xs font-sans font-medium tap-target hover:bg-success/20 focus-visible:outline-none focus-visible:shadow-glow"
        >
          All picks are in — open and copy coupon
        </button>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          data-testid="coupon-complete-dismiss"
          className="rounded-md p-1.5 tap-target text-text-muted hover:text-text-primary focus-visible:outline-none focus-visible:shadow-glow"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </span>
    </div>
  );
}
