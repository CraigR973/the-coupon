import { Bell, Smartphone } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePushSubscription } from '@/hooks/usePushSubscription';

const STORAGE_KEY = 'coupon_notif_prompt_seen';

function storageKey(playerId?: string): string {
  return playerId ? `${STORAGE_KEY}_${playerId}` : STORAGE_KEY;
}

export function markNotifPromptSeen(playerId?: string): void {
  try { localStorage.setItem(storageKey(playerId), '1'); } catch { /* ignore */ }
}

export function isNotifPromptSeen(playerId?: string): boolean {
  try {
    if (playerId) return localStorage.getItem(storageKey(playerId)) === '1';
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch { return false; }
}

function isStandalone(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    ('standalone' in navigator && (navigator as { standalone?: boolean }).standalone === true)
  );
}

interface Props {
  onClose: () => void;
  playerId?: string;
}

export function NotificationsPromptModal({ onClose, playerId }: Props) {
  const { subscribe, isLoading } = usePushSubscription();
  const standalone = isStandalone();

  async function handleEnable() {
    await subscribe();
    markNotifPromptSeen(playerId);
    onClose();
  }

  function handleLater() {
    markNotifPromptSeen(playerId);
    onClose();
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Notifications"
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-sm rounded-2xl bg-surface border border-border shadow-2xl p-6 space-y-5 animate-in slide-in-from-bottom-4 sm:slide-in-from-bottom-0 sm:zoom-in-95 duration-200">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="h-14 w-14 rounded-full bg-primary/10 flex items-center justify-center">
            <Bell className="h-7 w-7 text-primary" aria-hidden />
          </div>
          <h2 className="text-lg font-semibold text-text-primary font-sans">
            Turn on notifications
          </h2>
          <p className="text-sm font-sans text-text-secondary leading-relaxed">
            Your leagues will send you:
          </p>
        </div>

        {/* Batch 108: this list is the whole point of the screen, and every line on it is
            an event the application actually sends. It used to promise a reminder 30
            minutes before kickoff, alerts when results landed, and a nudge when the
            leaderboard shifted — none of which exist. The real reminder is keyed to the
            *lock*, not to kick-off, which is a different instant in every league. If an
            event is ever added or removed, this list moves with it. */}
        <ul className="space-y-2 text-sm font-sans text-text-secondary leading-relaxed">
          <li className="flex gap-2">
            <span aria-hidden className="text-text-muted">
              •
            </span>
            <span>when a round opens for picks</span>
          </li>
          <li className="flex gap-2">
            <span aria-hidden className="text-text-muted">
              •
            </span>
            <span>one reminder about three hours before picks lock, if you haven't picked</span>
          </li>
          <li className="flex gap-2">
            <span aria-hidden className="text-text-muted">
              •
            </span>
            <span>when someone else in the league picks, and how close the coupon is</span>
          </li>
          <li className="flex gap-2">
            <span aria-hidden className="text-text-muted">
              •
            </span>
            <span>when all picks are in and the coupon is ready to place</span>
          </li>
          <li className="flex gap-2">
            <span aria-hidden className="text-text-muted">
              •
            </span>
            <span>if a fixture is postponed and your pick is returned</span>
          </li>
        </ul>
        <p className="text-xs font-sans text-text-muted leading-relaxed">
          You can mute a single league, or all of them, in Settings.
        </p>

        {standalone ? (
          <div className="space-y-3">
            <Button
              className="w-full"
              onClick={handleEnable}
              disabled={isLoading}
            >
              {isLoading ? 'Enabling…' : 'Enable notifications'}
            </Button>
            <button
              onClick={handleLater}
              className="w-full text-center text-sm font-sans text-text-muted hover:text-text-primary transition-colors py-1"
            >
              Maybe later
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3 flex gap-2.5">
              <Smartphone className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" aria-hidden />
              <div>
                <p className="text-xs font-semibold text-amber-600 dark:text-amber-400 font-sans mb-0.5">
                  Add to Home Screen first
                </p>
                <p className="text-xs font-sans text-text-secondary leading-relaxed">
                  Notifications only work when the app is installed. Tap the share icon in your browser
                  and choose <strong className="text-text-primary">"Add to Home Screen"</strong>, then
                  open from there.
                </p>
              </div>
            </div>
            <button
              onClick={handleLater}
              className="w-full text-center text-sm font-sans text-text-muted hover:text-text-primary transition-colors py-1"
            >
              Got it, maybe later
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
