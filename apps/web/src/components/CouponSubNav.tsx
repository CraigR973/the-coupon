import { NavLink } from 'react-router-dom';
import { predictionsPath, type PredictionsSection } from '@/lib/leagues';
import { cn } from '@/lib/utils';

const ITEMS: ReadonlyArray<{ section: PredictionsSection; label: string; exact: boolean }> = [
  { section: '', label: 'Your pick', exact: true },
  { section: '/coupon', label: 'Combined coupon', exact: false },
  { section: '/results', label: 'Results', exact: false },
  { section: '/football', label: 'Football', exact: false },
];

/**
 * Sub-nav across the weekly-coupon surfaces: the player's own pick screen, the
 * leaderboard's combined accumulator, and the tables and results behind them.
 *
 * Football sits here rather than at the top level because it is context for a
 * pick — the same league scope, reached while deciding — not a section of its own.
 *
 * Every item stays inside `slug`: moving between these four is moving within one
 * league, never between them. That is the switcher's job.
 */
export function CouponSubNav({ slug }: { slug: string }) {
  return (
    <nav className="-mx-4 mb-5 overflow-x-auto sm:mx-0" aria-label="Coupon sections">
      <div className="flex min-w-max gap-1.5 px-4 sm:px-0">
        {ITEMS.map(({ section, label, exact }) => (
          <NavLink
            key={section}
            to={predictionsPath(slug, section)}
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
