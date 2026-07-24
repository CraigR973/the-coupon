import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { KnockoutAnnouncementModal } from './KnockoutAnnouncementModal';

const SEEN_KEY = 'sss_knockout_announcement_seen_v1';

function storageKey(playerId?: string): string {
  return playerId ? `${SEEN_KEY}_${playerId}` : SEEN_KEY;
}

function hasSeen(playerId?: string): boolean {
  try {
    return localStorage.getItem(storageKey(playerId)) === 'true';
  } catch {
    return false;
  }
}

function markSeen(playerId?: string): void {
  try {
    localStorage.setItem(storageKey(playerId), 'true');
  } catch {
    /* ignore */
  }
}

export function KnockoutAnnouncementController() {
  const { player } = useAuth();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(() => !hasSeen(player?.id));
  const isSafeLandingRoute = pathname === '/';

  if (!player || !open) return null;
  if (!isSafeLandingRoute) return null;

  return (
    <KnockoutAnnouncementModal
      onClose={() => {
        markSeen(player.id);
        setOpen(false);
      }}
    />
  );
}
