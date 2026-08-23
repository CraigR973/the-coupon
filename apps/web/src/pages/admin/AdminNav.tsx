import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

/**
 * The site-admin console's own sub-nav.
 *
 * Three screens rather than one, because they answer three different questions and the
 * one an admin arrives with is usually "where is this person" — the PIN-reset push lands
 * on Players directly. Operational admin (dashboard, sync, results) is Batch 69 and will
 * add to this row rather than replace it.
 */
const TABS = [
  { to: '/admin/players', label: 'Players' },
  { to: '/admin/invites', label: 'Invites' },
  { to: '/admin/leagues', label: 'All leagues' },
] as const;

export function AdminNav() {
  return (
    <nav aria-label="Site admin" className="mb-5 flex gap-1 overflow-x-auto">
      {TABS.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn(
              'rounded-md px-3 py-2 font-sans text-sm whitespace-nowrap press-down tap-target',
              'focus-visible:outline-none focus-visible:shadow-glow',
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
