import { keys } from '@/lib/queryKeys';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import type { RenameNoticeState } from '@/lib/types';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const RENAME_NOTICE_KEY = keys.me.renameNotice();

/**
 * Tells a renamed member their sign-in name changed, when push could not. Batch 148.
 *
 * Batch 74 renamed three members, and Batch 93 told them by web push — the only channel it
 * had. One of them has no push subscription, so every boot tried again and nothing ever
 * arrived. This is the second channel: the app, on the next load with a session.
 *
 * **Any way of closing it counts as seeing it**, and seeing it is what tells the API to
 * stop — the "Got it" button, the corner cross, Escape and a tap outside all post the same
 * acknowledgement, which writes the marker the push path writes. The dialog closes at once
 * rather than waiting on that call. If the call fails, the marker stays unwritten and the
 * next load shows the notice again, which is the rule push follows too: nothing is marked
 * as told until something actually reached them.
 *
 * **Everyone else pays one cheap request per app load.** The API answers from the member's
 * id alone for anyone outside the three, without a query of its own. Until the API ships,
 * that request 404s and this renders nothing, so the web half is safe to arrive first.
 *
 * The copy comes from the API, so both channels say exactly the same thing. Mounted in
 * `Layout`, which renders only once `ProtectedRoute` has let a signed-in member through,
 * never under the PIN gate.
 */
export function RenameNotice() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: RENAME_NOTICE_KEY,
    queryFn: () => apiFetch<RenameNoticeState>('/api/v1/me/rename-notice'),
    // Once per load is the whole point; a focus refetch would only re-ask the same thing.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  const notice = data?.notice ?? null;
  if (!notice) return null;

  const dismiss = () => {
    queryClient.setQueryData<RenameNoticeState>(RENAME_NOTICE_KEY, { notice: null });
    void apiFetch<void>('/api/v1/me/rename-notice/seen', { method: 'POST' }).catch(() => {
      // Unwritten marker: the next load asks again. See the comment above.
    });
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) dismiss();
      }}
    >
      <DialogContent className="max-w-sm" data-testid="rename-notice">
        <DialogHeader>
          <DialogTitle>{notice.title}</DialogTitle>
          <DialogDescription>{notice.body}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={dismiss}>Got it</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
