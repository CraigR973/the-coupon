import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { ApiError, apiFetch } from '@/lib/api';
import { keys } from '@/lib/queryKeys';
import { formatInstant } from '@/lib/time';
import { useOptionalAuth } from '@/contexts/AuthContext';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';

interface InboxItem {
  id: string;
  kind: string;
  title: string;
  body: string;
  url: string;
  created_at: string;
  read_at: string | null;
}

interface Inbox {
  items: InboxItem[];
  unread_count: number;
}

/** Home's durable copy of league notifications, including members without push. */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const readAttempt = useRef<string | null>(null);
  const player = useOptionalAuth()?.player;
  const queryClient = useQueryClient();
  const { data, error, isLoading, refetch } = useQuery<Inbox>({
    queryKey: keys.notifications(),
    queryFn: () => apiFetch<Inbox>('/api/v1/notifications/inbox'),
    retry: false,
    refetchInterval: 60_000,
  });
  const { mutate: markRead } = useMutation({
    mutationFn: () => apiFetch('/api/v1/notifications/inbox/read', { method: 'POST' }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.notifications() }),
  });

  const unread = data?.unread_count ?? 0;
  const readAttemptKey = unread > 0 ? `${unread}:${data?.items.find((item) => !item.read_at)?.id ?? ''}` : null;
  useEffect(() => {
    if (!open || !readAttemptKey || readAttempt.current === readAttemptKey) return;
    readAttempt.current = readAttemptKey;
    markRead();
  }, [open, readAttemptKey, markRead]);

  // The web ships before the migration and API route. Keep the old home intact.
  if (error instanceof ApiError && error.status === 404) return null;

  const timezone = player?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? 'UTC';

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) readAttempt.current = null;
      }}
    >
      <DialogTrigger asChild>
        <button
          type="button"
          className="relative inline-flex h-11 w-11 items-center justify-center rounded-full border border-border bg-surface-elevated text-text-primary shadow-sm hover:bg-surface focus-visible:outline-none focus-visible:shadow-glow"
          aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
          data-testid="notification-bell"
        >
          <Bell className="h-5 w-5" aria-hidden />
          {unread > 0 && (
            <span className="absolute -right-1 -top-1 flex min-h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 font-sans text-caption font-bold text-primary-foreground">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] max-w-md overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Notifications</DialogTitle>
          <DialogDescription className="sr-only">
            League updates saved for the past 30 days. Opening this list marks them read.
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <p className="font-sans text-sm text-text-muted">Loading league updates…</p>
        ) : error ? (
          <div className="space-y-2">
            <p className="font-sans text-sm text-text-secondary">League updates could not load.</p>
            <button
              type="button"
              onClick={() => void refetch()}
              className="font-sans text-sm text-primary underline focus-visible:outline-none focus-visible:shadow-glow"
            >
              Try again
            </button>
          </div>
        ) : data?.items?.length ? (
          <ul className="divide-y divide-border" aria-label="League notifications">
            {data.items.map((item) => (
              <li key={item.id}>
                <Link
                  to={item.url}
                  onClick={() => setOpen(false)}
                  className="block rounded-md px-2 py-3 hover:bg-surface-elevated focus-visible:outline-none focus-visible:shadow-glow"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-sans text-sm font-semibold text-text-primary">{item.title}</span>
                    {!item.read_at && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}
                  </div>
                  <p className="mt-1 font-sans text-sm text-text-secondary">{item.body}</p>
                  <time className="mt-1 block font-mono text-xs text-text-muted" dateTime={item.created_at}>
                    {formatInstant(item.created_at, timezone, 'd MMM, HH:mm') ?? item.created_at}
                  </time>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="font-sans text-sm text-text-secondary">
            Your league updates will appear here for 30 days, even without push notifications.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
