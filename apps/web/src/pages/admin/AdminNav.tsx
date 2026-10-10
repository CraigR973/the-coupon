import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

/**
 * The site-admin console's own sub-nav.
 *
 * Dashboard first because it is the one an admin opens on a Saturday morning; Players
 * second because the PIN-reset push lands there directly and that is the arrival with a
 * member waiting on the other end. Calendar owns the one deployment-wide season
 * (Batch 113); Results and Sync are the operational half (Batch 69).
 */
const TABS = [
  { to: '/admin/dashboard', label: 'Dashboard' },
  { to: '/admin/calendar', label: 'Calendar' },
  { to: '/admin/players', label: 'Players' },
  { to: '/admin/results', label: 'Results' },
  { to: '/admin/sync', label: 'Sync' },
  { to: '/admin/invites', label: 'Invites' },
  { to: '/admin/leagues', label: 'All leagues' },
] as const;

export function AdminNav() {
  return (
    <nav aria-label="Site admin" className="mb-5 flex w-full min-w-0 flex-nowrap gap-1 overflow-x-auto overscroll-x-contain py-1.5">
      {TABS.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn(
              'shrink-0 rounded-md px-3 py-2 font-sans text-sm whitespace-nowrap press-down tap-target',
              'focus-visible:outline-hidden focus-visible:shadow-glow',
              isActive
                ? 'bg-surface-elevated text-text-primary font-semibold'
                : 'text-text-secondary hover:text-text-primary',
            )
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
