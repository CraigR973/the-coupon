import { useEffect, useRef } from 'react';
import { Toaster, useSonner } from 'sonner';
import { useTheme } from '@/contexts/ThemeContext';

/**
 * Sonner's toasts, announced with the urgency each one has earned.
 *
 * UX-17. Sonner publishes every toast through **one** live region — a single
 * `<section aria-live="polite">` wrapping the whole stack — so a failed pick is
 * announced no more urgently than a successful one, and a screen reader finishes
 * whatever it is saying before mentioning that a pick did not land. That matters
 * more since Batch 139: a lost claim race is now a warning the member has to act
 * on, and politeness puts it at the back of the queue.
 *
 * Sonner has no per-toast `aria-live`, so the region is taken over rather than
 * configured: its own is turned off and two of ours replace it, holding the same
 * text for a screen reader while the visible toasts are left exactly as they are.
 * Two regions, not one with a changing `aria-live` — a live region's politeness is
 * read when content is inserted, so flipping it on an existing region is a race.
 */
export function AppToaster() {
  const { toasts } = useSonner();
  const { resolved } = useTheme();
  const region = useRef<HTMLElement>(null);

  // Re-applied on every change rather than once on mount: React only writes an
  // attribute when the rendered value changes, and sonner always renders "polite",
  // so a remount would silently restore it and nothing would look wrong.
  useEffect(() => {
    region.current?.setAttribute('aria-live', 'off');
  });

  const spoken = toasts
    .filter((entry) => !entry.delete && typeof entry.title === 'string')
    .map((entry) => ({ id: entry.id, type: entry.type, title: entry.title as string }));
  const urgent = spoken.filter((entry) => entry.type === 'error' || entry.type === 'warning');
  const calm = spoken.filter((entry) => entry.type !== 'error' && entry.type !== 'warning');

  return (
    <>
      <Toaster
        ref={region}
        position="bottom-right"
        theme={resolved}
        closeButton
        className="coupon-toaster"
        mobileOffset={{ bottom: 'calc(var(--tabbar-height) + var(--safe-bottom) + 1rem)' }}
        toastOptions={{
          classNames: {
            toast: 'bg-surface-overlay border-border border-l-[3px] shadow-lg rounded-md',
            title: 'text-text-primary font-semibold',
            description: 'text-text-secondary',
            actionButton: 'bg-primary text-on-primary hover:bg-primary-dark',
            closeButton: 'border-border bg-surface-overlay text-text-muted hover:text-text-primary',
            success: 'border-l-[var(--success-ink)] [&_[data-icon]]:text-success',
            warning: 'border-l-[var(--warning-ink)] [&_[data-icon]]:text-warning',
            error: 'border-l-[var(--error-ink)] [&_[data-icon]]:text-error',
            info: 'border-l-[var(--primary-ink)] [&_[data-icon]]:text-primary',
            default: 'border-l-[var(--primary-ink)] [&_[data-icon]]:text-primary',
          },
        }}
      />
      {/* `role="alert"` is assertive by definition, and carrying it on the element
          that is always present — rather than on the message — is what makes an
          insertion into it an announcement. */}
      <div role="alert" aria-atomic="false" className="sr-only" data-testid="toast-alerts">
        {urgent.map((entry) => (
          <p key={entry.id}>{entry.title}</p>
        ))}
      </div>
      <div
        role="status"
        aria-live="polite"
        aria-atomic="false"
        className="sr-only"
        data-testid="toast-status"
      >
        {calm.map((entry) => (
          <p key={entry.id}>{entry.title}</p>
        ))}
      </div>
    </>
  );
}
