import { useEffect, useRef, useState } from 'react';
import { Button, type ButtonProps } from './button';
import { cn } from '@/lib/utils';

export type SaveButtonState = 'idle' | 'saving' | 'saved';

export interface SaveButtonProps extends Omit<ButtonProps, 'children'> {
  state: SaveButtonState;
  idleLabel: string;
  savingLabel?: string;
  savedLabel?: string;
  /**
   * How long to hold the `saved` state visually. Default 1200 ms — matches
   * the U5 spec. The button does NOT change `state` itself; callers should
   * flip back to `idle` after this duration. The internal timing here is
   * only for the check-icon draw-in animation.
   */
  savedHoldMs?: number;
}

const CHECK_DRAW_MS = 280;
//: The `d` below is a 3-4-5 leg (5 units) plus a longer one (~10.6). Rounded up,
//: because a dash longer than the path still hides it completely and a dash shorter
//: than it would leave the tick visibly pre-drawn.
const CHECK_PATH_LENGTH = 16;

/**
 * Shared save CTA.
 *
 * Three states:
 *   - `idle`   → shows `idleLabel`
 *   - `saving` → shows `savingLabel` (defaults to "Saving…"), disabled
 *   - `saved`  → shows a checkmark that strokes itself in, then `savedLabel`
 *
 * The caller owns the state lifecycle (typically: set `saving`, await the
 * mutation, set `saved`, then setTimeout back to `idle`). The button itself
 * just animates the visual transitions.
 *
 * Honours `prefers-reduced-motion`: the check icon snaps in fully drawn
 * with no path animation and the label crossfade is replaced by an instant
 * swap.
 */
export function SaveButton({
  state,
  idleLabel,
  savingLabel = 'Saving…',
  savedLabel = 'Saved',
  savedHoldMs: _savedHoldMs = 1200,
  className,
  disabled,
  ...rest
}: SaveButtonProps) {
  // The check needs a fresh key each time we enter "saved" so the path
  // animation re-runs even when state transitions saved → idle → saved.
  const [checkKey, setCheckKey] = useState(0);
  const lastStateRef = useRef<SaveButtonState>(state);
  useEffect(() => {
    if (lastStateRef.current !== 'saved' && state === 'saved') {
      setCheckKey((k) => k + 1);
    }
    lastStateRef.current = state;
  }, [state]);

  const isSaving = state === 'saving';
  const isSaved = state === 'saved';

  return (
    <Button
      type={rest.type ?? 'submit'}
      aria-live="polite"
      disabled={disabled || isSaving || isSaved}
      className={cn('relative overflow-hidden', className)}
      {...rest}
    >
      {/* Invisible spacer ensures the button width never flickers between
          label widths. Picks the widest of the three labels. */}
      <span className="invisible whitespace-nowrap" aria-hidden>
        {[idleLabel, savingLabel, savedLabel].reduce(
          (a, b) => (b.length > a.length ? b : a),
          idleLabel,
        )}
      </span>

      {/* Batch 164. Was an `AnimatePresence` crossfade; the key change remounts the span
          and CSS animates it in. The outgoing label no longer slides away first — the two
          were never both visible under `mode="wait"` anyway, so what changed is that the
          swap takes 180ms rather than 360ms. The reduced-motion branch is gone with it:
          `index.css` collapses the animation for everyone who asks, which is one rule
          instead of a hook every component had to remember. */}
      <span className="absolute inset-0 flex items-center justify-center gap-1.5">
        <span key={state} className="animate-label-enter inline-flex items-center gap-1.5">
          {isSaved && <CheckMark key={checkKey} />}
          <span>{isSaving ? savingLabel : isSaved ? savedLabel : idleLabel}</span>
        </span>
      </span>
    </Button>
  );
}

/**
 * 16×16 check icon, drawing itself in over 280 ms.
 *
 * Batch 164 replaced framer-motion's animated `pathLength` with the CSS technique it is
 * built on: set `stroke-dasharray` to the path's length so the whole stroke is one dash,
 * then animate `stroke-dashoffset` from that length to zero. `CHECK_PATH_LENGTH` is the
 * measured length of the `d` below — a little over the 3-4-5 triangle's 5 units plus the
 * long stroke's ~10.6 — and it only has to be *at least* the true length, so it is
 * rounded up. Reduced motion is handled in `index.css` for everything at once.
 */
function CheckMark() {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className="shrink-0"
    >
      <path
        d="M3 8.5 L6.5 12 L13 4.5"
        className="animate-draw-check"
        style={
          {
            '--check-length': CHECK_PATH_LENGTH,
            '--check-duration': `${CHECK_DRAW_MS}ms`,
          } as React.CSSProperties
        }
      />
    </svg>
  );
}
