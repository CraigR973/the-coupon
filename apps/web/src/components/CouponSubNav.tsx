import { NavLink } from 'react-router-dom';
import { predictionsPath, type PredictionsSection } from '@/lib/leagues';
import { cn } from '@/lib/utils';

const ITEMS: ReadonlyArray<{ section: PredictionsSection; label: string; exact: boolean }> = [
  { section: '', label: 'Current round', exact: true },
  { section: '/results', label: 'Season', exact: false },
];

/**
 * Sub-nav across the weekly-coupon surfaces: the round being played now, and the season
 * behind it.
 *
 * There were three until Batch 105, and the middle one was the problem. `Your pick` and
 * `Combined coupon` were two halves of one weekly job — what I took, and what everyone
 * took — so the tab strip made the member choose between two answers to the same
 * question, and each screen then repeated the other's headings, fold summaries and
 * frozen-price prose to make up for what it could not show. One `Current round` answers
 * both, and `#coupon` is where the combined half of it lives.
 *
 * `Season` was called "Results" until Batch 78 and showed none: every row of it navigates
 * to the round's coupon, because Batch 67 put the scorelines, the points and the won/lost
 * badges *there* — a settled round is read as a coupon that finished. The label was the
 * only thing claiming otherwise, so the label changed rather than the screen. The route
 * stays `/results`: members have it in their history.
 *
 * Football Stats sat here until Batch 51, on the argument that it was context for a
 * pick rather than a section of its own. That argument held only while the screen
 * was league-scoped; untied from a league it has nothing to say about *this* coupon
 * in particular, and it is a top-level tab.
 *
 * Every item stays inside `slug`: moving between them is moving within one league, never
 * between leagues. That is the switcher's job.
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
