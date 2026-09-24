import { type ReactNode } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';

/**
 * Page transition wrapper.
 *
 * - PUSH/REPLACE navigations slide in from the right (forward feeling).
 * - POP (browser back) navigations slide in from the left (backward feeling).
 * - Readers who ask for reduced motion get a plain cut.
 *
 * Batch 164 replaced framer-motion here. **One behaviour changed and it is worth
 * knowing:** the old version wrapped this in `AnimatePresence mode="wait"`, so the
 * outgoing page slid away over 220ms *before* the incoming one began. CSS cannot animate
 * an element React has already unmounted, so the exit is gone and the new page enters
 * immediately. The visible difference is that a route change is now 220ms rather than
 * 440ms and has no blank moment in the middle — snappier, and closer to what a native
 * app does. Restoring the exit would mean keeping the old tree mounted, which is what
 * cost 107 KB.
 *
 * `key` is what drives it: React remounts the div on every pathname change, and a
 * freshly mounted element runs its CSS animation. Reduced motion is handled in
 * `index.css` by zeroing `--page-enter-x`, not by a hook here.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navType = useNavigationType();

  const offset = navType === 'POP' ? '-16px' : '16px';

  return (
    <div
      key={location.pathname}
      className="animate-page-enter"
      style={{ '--page-enter-x': offset } as React.CSSProperties}
    >
      {children}
    </div>
  );
}
