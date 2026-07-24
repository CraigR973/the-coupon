import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { isTourSeen } from './IntroTour';
import { SurveyEnhancementsModal } from './SurveyEnhancementsModal';

const SEEN_KEY = 'sss_survey_enhancements_seen_v1';

function hasSeen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === 'true';
  } catch {
    return false;
  }
}

function markSeen(): void {
  try {
    localStorage.setItem(SEEN_KEY, 'true');
  } catch {
    /* ignore */
  }
}

export function SurveyEnhancementsController() {
  const { player } = useAuth();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(() => !hasSeen());
  const isSafeLandingRoute = pathname === '/';

  if (!player || !open) return null;
  if (!isTourSeen(player.id)) return null;
  if (!isSafeLandingRoute) return null;

  return (
    <SurveyEnhancementsModal
      onClose={() => {
        markSeen();
        setOpen(false);
      }}
    />
  );
}
