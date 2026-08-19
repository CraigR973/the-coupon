import { useLayoutEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useLeague } from '@/contexts/LeagueContext';
import { leagueSwitchPath } from '@/lib/leagues';
import { cn } from '@/lib/utils';

interface Props {
  currentSlug: string;
  className?: string;
}

const LEAGUE_SWITCH_SCROLL_KEY = 'coupon_league_switch_scroll';

function getSavedScrollOffset(): number {
  if (typeof window === 'undefined') return 0;

  const raw = window.sessionStorage.getItem(LEAGUE_SWITCH_SCROLL_KEY);
  const parsed = raw ? Number(raw) : 0;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function saveScrollOffset(offset: number): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.setItem(LEAGUE_SWITCH_SCROLL_KEY, String(Math.max(0, offset)));
}

/**
 * The league switcher. Purely presentational: every entry is a link to that
 * league's own address, and binding the context is the destination's job
 * (`useRouteLeague`) rather than this strip's — a nav component that quietly
 * rewrote which league the app was on was a side effect waiting to be forgotten.
 *
 * Where an entry points is `leagueSwitchPath`'s decision, taken from the current
 * pathname: a switch keeps the reader on the surface they are already on. Deriving
 * it here rather than at the five call sites means a league-scoped surface added
 * later is switchable without touching this file.
 */
export function LeagueSwitchStrip({ currentSlug, className }: Props) {
  const { leagues } = useLeague();
  const { pathname } = useLocation();
  const navRef = useRef<HTMLElement | null>(null);

  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    nav.scrollLeft = getSavedScrollOffset();
  }, [currentSlug, leagues.length]);

  if (leagues.length < 2) return null;

  const persistScrollPosition = () => {
    if (!navRef.current) return;
    saveScrollOffset(navRef.current.scrollLeft);
  };

  return (
    <section
      className={cn(
        'space-y-3 rounded-2xl border border-border/80 bg-surface-elevated/70 px-3 py-3 shadow-sm',
        'sm:px-4',
        className,
      )}
      data-testid="league-switch-strip"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-text-primary">
          Your leagues
        </p>
        {/* Surface-neutral on purpose: the strip sits on the coupon, the results and
            the football tables as well as the standings, and since Batch 34 a tap
            keeps the reader on whichever of those they are reading. */}
        <span className="rounded-full border border-border/80 bg-surface px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.18em] text-text-muted">
          Tap to switch
        </span>
      </div>
      <nav
        ref={navRef}
        className="-mx-1 overflow-x-auto scroll-smooth"
        aria-label="Switch league"
        data-testid="league-switch-scroll"
        onScroll={persistScrollPosition}
      >
        <div className="flex min-w-max gap-2 px-1">
          {leagues.map((league) => {
            const isCurrent = league.slug === currentSlug;
            return isCurrent ? (
              <span
                key={league.slug}
                aria-current="page"
                className={cn(
                  'inline-flex max-w-[13rem] items-center rounded-full border px-3.5 py-1.5 text-xs font-medium font-sans whitespace-nowrap shadow-sm',
                  'border-primary/40 bg-primary/15 text-primary',
                )}
                title={league.name}
              >
                <span className="truncate">{league.name}</span>
              </span>
            ) : (
              <Link
                key={league.slug}
                to={leagueSwitchPath(league.slug, pathname)}
                onClick={persistScrollPosition}
                className={cn(
                  'inline-flex max-w-[13rem] items-center rounded-full border px-3.5 py-1.5 text-xs font-medium font-sans whitespace-nowrap transition-colors press-down shadow-sm',
                  'border-border bg-surface text-text-secondary hover:border-primary/40 hover:text-text-primary hover:bg-surface-elevated',
                  'focus-visible:outline-none focus-visible:shadow-glow',
                )}
                title={`Open ${league.name}`}
              >
                <span className="truncate">{league.name}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </section>
  );
}
