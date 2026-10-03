import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { formatInstant, parseInstant } from '@/lib/time';
import type { PinEvent, PinEvents } from '@/lib/types';
import { useOptionalAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const PIN_EVENTS_KEY = ['me', 'pin-events'] as const;

/** Where this device remembers the newest reset or set it has shown one member. */
function seenKey(playerId: string): string {
  return `coupon.pin-notice.seen.${playerId}`;
}

function readSeen(key: string): number {
  try {
    const stored = localStorage.getItem(key);
    const at = stored ? parseInstant(stored).getTime() : 0;
    return Number.isNaN(at) ? 0 : at;
  } catch {
    return 0;
  }
}

function writeSeen(key: string, at: string): void {
  try {
    localStorage.setItem(key, at);
  } catch {
    // Storage refused (a private window): it is shown again on the next load, never lost.
  }
}

const LABEL: Record<PinEvent['kind'], string> = {
  reset: 'An admin reset your PIN',
  set: 'A new PIN was chosen',
};

/**
 * Tells a member their PIN was reset or set, on the next load with a session. Batch 179.
 *
 * A reset clears the PIN and signs the member out, and for 24 hours whoever names the account
 * first at `/auth/pin/set` chooses the new one. Both steps push to the member's devices; this
 * is the second channel, for a member push could not reach — no subscription, quiet hours —
 * and the record of what happened for one it did.
 *
 * **What has been shown is remembered on this device**, not on the account. A marker on the
 * account would be cleared by whoever signs in first, and after a takeover that is the person
 * who took it; remembered here, the member's own phone still lists every reset and set from
 * the last thirty days the next time it is theirs again. Any way of closing the dialog counts
 * as having seen what it listed.
 *
 * Until the API ships, the request 404s and this renders nothing, so the web half is safe to
 * arrive first. Mounted in `Layout` beside `RenameNotice`, so only behind a session.
 */
export function PinNotice() {
  const player = useOptionalAuth()?.player ?? null;
  const timezone = player?.timezone ?? 'UTC';
  const [closedThrough, setClosedThrough] = useState(0);
  const { data } = useQuery({
    queryKey: PIN_EVENTS_KEY,
    queryFn: () => apiFetch<PinEvents>('/api/v1/me/pin-events'),
    enabled: player !== null,
    // Once per load is the point; a focus refetch would only re-ask the same thing.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  if (!player || !data) return null;
  const key = seenKey(player.id);
  const seen = Math.max(readSeen(key), closedThrough);
  const unseen = data.events.filter((event) => parseInstant(event.at).getTime() > seen);
  if (unseen.length === 0) return null;

  // The API lists newest first, so the first unseen event is the one to remember.
  const newest = unseen[0];
  const dismiss = () => {
    writeSeen(key, newest.at);
    setClosedThrough(parseInstant(newest.at).getTime());
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) dismiss();
      }}
    >
      <DialogContent className="max-w-sm" data-testid="pin-notice">
        <DialogHeader>
          <DialogTitle>Your PIN changed</DialogTitle>
          <DialogDescription>
            If any of this wasn’t you, sign out and use “Forgot PIN?” on the sign-in screen to
            ask an admin to reset it.
          </DialogDescription>
        </DialogHeader>
        <ul className="space-y-2 text-sm font-sans text-text-primary">
          {unseen.map((event) => (
            <li key={`${event.kind}-${event.at}`} className="flex flex-wrap justify-between gap-x-3">
              <span>{LABEL[event.kind]}</span>
              <time dateTime={event.at} className="text-text-muted tabular-nums">
                {formatInstant(event.at, timezone, 'EEE d MMM, HH:mm')}
              </time>
            </li>
          ))}
        </ul>
        <DialogFooter>
          <Button onClick={dismiss}>Got it</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
