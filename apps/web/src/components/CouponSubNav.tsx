import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

const ITEMS: ReadonlyArray<{ to: string; label: string; exact: boolean }> = [
  { to: '/predictions', label: 'Your pick', exact: true },
  { to: '/predictions/coupon', label: 'Combined coupon', exact: false },
];

/**
 * Sub-nav across the two weekly-coupon surfaces: the player's own pick screen
 * and the leaderboard's combined accumulator.
 */
export function CouponSubNav() {
  return (
    <nav className="-mx-4 mb-5 overflow-x-auto sm:mx-0" aria-label="Coupon sections">
      <div className="flex min-w-max gap-1.5 px-4 sm:px-0">
        {ITEMS.map(({ to, label, exact }) => (
          <NavLink
            key={to}
            to={to}
            end={exact}
            className={({ isActive }) =>
              cn(
                'inline-flex items-center whitespace-nowrap rounded-full px-3.5 py-1.5 font-sans text-xs font-medium transition-colors press-down focus-visible:outline-none focus-visible:shadow-glow',
                isActive
                  ? 'border border-primary/30 bg-primary/15 text-primary'
                  : 'border border-border bg-surface text-text-secondary hover:bg-surface-elevated',
              )
            }
          >
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
