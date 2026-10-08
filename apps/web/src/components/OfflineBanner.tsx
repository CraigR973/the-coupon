import { WifiOff } from 'lucide-react';
import { useOnlineStatus } from '@/hooks/useOnlineStatus';

export function OfflineBanner() {
  const isOnline = useOnlineStatus();

  if (isOnline) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="offline-banner"
      className="sticky top-[calc(53px+var(--safe-top))] z-banner flex min-h-9 items-center justify-center gap-2 border-b border-warning/30 px-4 py-2 text-center font-sans text-sm text-text-primary sm:top-[calc(57px+var(--safe-top))]"
      style={{ background: 'color-mix(in srgb, var(--warning) 12%, var(--bg))' }}
    >
      <WifiOff className="h-4 w-4 shrink-0 text-warning" aria-hidden />
      You're offline — some content may be outdated
    </div>
  );
}
