import { CloudOff, HelpCircle } from 'lucide-react';
import type { OutstandingPick } from '@/hooks/usePickEditor';

/**
 * The one claim this device is holding that the server has not confirmed (Batch 90).
 *
 * A toast says a thing once and then it is gone, which is the wrong shape for a state the
 * member has to *act* on — and in the hour before lock, "did my pick land?" is the only
 * question that matters. This stays on screen until the answer is known.
 *
 * The two states get different words and a different action, because the difference is
 * the entire point. A `queued` pick is known not to have reached the server, so the
 * button sends it. An `unconfirmed` one may already be the member's claim, so the button
 * *checks* — offering "send again" here would be offering to overwrite a selection they
 * may have already moved on from.
 *
 * Neither is the "someone else got there first" case. A lost race is an answer from the
 * server: it clears the held intent, so this notice is not rendered at all, and the
 * member reads a toast that names the member who beat them.
 */
export function OutstandingPickNotice({
  outstanding,
  onResolve,
  onDiscard,
  disabled = false,
}: {
  outstanding: OutstandingPick;
  onResolve: () => void;
  onDiscard: () => void;
  /** The round shut underneath it — the intent can no longer be sent, only dropped. */
  disabled?: boolean;
}) {
  const queued = outstanding.state === 'queued';
  const Icon = queued ? CloudOff : HelpCircle;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="outstanding-pick-notice"
      data-state={outstanding.state}
      className="flex flex-col gap-2 rounded-lg border border-amber-700/60 bg-amber-900/25 p-3 text-amber-100 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="flex items-start gap-2 text-xs font-sans">
        <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>
          {queued ? (
            <>
              <strong className="font-medium">Your pick hasn’t been sent yet.</strong> We’ll
              send it as soon as you’re back online — keep this screen open.
            </>
          ) : (
            <>
              <strong className="font-medium">Your claim is unconfirmed.</strong> We didn’t
              hear back, so it may or may not have landed. Check before picking again.
            </>
          )}
        </span>
      </p>
      <span className="flex shrink-0 gap-2">
        <button
          type="button"
          onClick={onResolve}
          disabled={disabled}
          data-testid="outstanding-pick-resolve"
          className="rounded-md border border-amber-500/70 px-3 py-1.5 text-xs font-sans font-medium tap-target hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:shadow-glow"
        >
          {queued ? 'Send now' : 'Check my pick'}
        </button>
        <button
          type="button"
          onClick={onDiscard}
          data-testid="outstanding-pick-discard"
          className="rounded-md px-3 py-1.5 text-xs font-sans text-amber-200/80 tap-target hover:text-amber-100 focus-visible:outline-none focus-visible:shadow-glow"
        >
          Dismiss
        </button>
      </span>
    </div>
  );
}
