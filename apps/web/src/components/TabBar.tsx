import { useState, useId, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Home,
  Goal,
  Ticket,
  Trophy,
  MoreHorizontal,
  Settings as SettingsIcon,
  ShieldCheck,
  User,
  LogOut,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useLeague } from '@/contexts/LeagueContext';
import { Sheet } from '@/components/ui/sheet';
import {
  FOOTBALL_PATH,
  isCouponPath,
  isFootballPath,
  isLeagueHubPath,
  predictionsPath,
} from '@/lib/leagues';
import { cn } from '@/lib/utils';

interface TabDef {
  to: string;
  label: string;
  Icon: LucideIcon;
  /** Whether this tab owns `pathname`. */
  match: (pathname: string) => boolean;
}

/**
 * Coupon points at the bound league, because a tab has to go *somewhere* and the
 * last league viewed is the only sensible answer. Its highlighting does not: it
 * matches any league's coupon, so tapping into another league's week lights the
 * right tab from the first frame rather than after the context catches up. Leagues
 * has to exclude those paths explicitly now that the coupon lives under `/leagues/`
 * too.
 *
 * Football Stats takes no slug at all since Batch 51 — it reads the whole pool, so
 * there is no bound league for it to be pointed at.
 */
function primaryTabs(slug: string | null): ReadonlyArray<TabDef> {
  return [
    { to: '/', label: 'Home', Icon: Home, match: (p) => p === '/' },
    { to: predictionsPath(slug), label: 'Coupon', Icon: Ticket, match: isCouponPath },
    { to: FOOTBALL_PATH, label: 'Football Stats', Icon: Goal, match: isFootballPath },
    { to: '/leagues', label: 'Leagues', Icon: Trophy, match: isLeagueHubPath },
  ];
}

export function TabBar() {
  const { pathname } = useLocation();
  const { player, logout } = useAuth();
  const { activeSlug, hasLeagues } = useLeague();
  const navigate = useNavigate();
  const [moreOpen, setMoreOpen] = useState(false);
  const layoutId = useId();

  // Guarantee the More sheet closes whenever the route changes, regardless of
  // how the navigation happened (sheet button, swipe-back, deep link).
  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  // My profile is career-scoped, not bound to whichever league happens to be
  // active: a member in three leagues has three records, and silently picking one
  // of them made the other two unreachable from here. The per-league record is
  // still a tap away — from that league's leaderboard, and from this page's own
  // breakdown.
  const settings: TabDef = {
    to: '/settings',
    label: 'Settings',
    Icon: SettingsIcon,
    match: (p) => p.startsWith('/settings'),
  };
  // Site admin is in the More sheet rather than a tab of its own: it is the rarest
  // destination in the app and there are five primary slots. The gate is the profile
  // role — the same flag `/api/v1/admin` enforces — so a player never sees an entry
  // whose every screen would bounce them home.
  const adminConsole: TabDef = {
    to: '/admin/dashboard',
    label: 'Site admin',
    Icon: ShieldCheck,
    match: (p) => p.startsWith('/admin'),
  };
  const SECONDARY: ReadonlyArray<TabDef> = player
    ? [
        {
          to: '/profile',
          label: 'My profile',
          Icon: User,
          match: (p) => p.startsWith('/profile'),
        },
        ...(player.role === 'admin' ? [adminConsole] : []),
        settings,
      ]
    : [settings];

  const isMoreActive = SECONDARY.some((t) => t.match(pathname));

  // A league still loading is not yet a league to address, so the tabs fall back
  // to the slug-less paths — which redirect the moment one resolves.
  const tabs: ReadonlyArray<Omit<TabDef, 'match'> & { isCurrent: boolean }> = [
    ...primaryTabs(hasLeagues ? activeSlug : null).map((t) => ({
      ...t,
      isCurrent: t.match(pathname),
    })),
    {
      to: '#more',
      label: 'More',
      Icon: MoreHorizontal,
      isCurrent: isMoreActive,
    },
  ];

  function handleSheetNav(to: string) {
    setMoreOpen(false);
    navigate(to);
  }

  return (
    <>
      <nav
        aria-label="Primary"
        className={cn(
          'fixed bottom-0 inset-x-0 z-tabbar md:hidden',
          'bg-surface/95 backdrop-blur border-t border-border',
          'pb-safe',
        )}
      >
        <ul className="flex items-stretch justify-around h-[60px]">
          {tabs.map((tab) => {
            const { to, label, Icon, isCurrent } = tab;
            const isOverflow = to === '#more';
            const content = (
              <>
                {isCurrent && (
                  <motion.span
                    layoutId={layoutId}
                    className="absolute inset-x-3 top-0 h-0.5 bg-primary rounded-full"
                    transition={{ type: 'spring', stiffness: 360, damping: 32 }}
                  />
                )}
                <Icon
                  className={cn(
                    'h-5 w-5 transition-colors',
                    isCurrent ? 'text-primary' : 'text-text-muted',
                  )}
                  aria-hidden
                />
                <span
                  className={cn(
                    'text-[10px] font-medium tracking-tight font-sans',
                    isCurrent ? 'text-primary' : 'text-text-muted',
                  )}
                >
                  {label}
                </span>
              </>
            );
            const baseClass = cn(
              'relative flex-1 flex flex-col items-center justify-center gap-1 tap-target',
              'focus-visible:outline-none focus-visible:shadow-glow rounded-sm press-down',
            );
            return (
              <li key={label} className="contents">
                {isOverflow ? (
                  <button
                    type="button"
                    onClick={() => setMoreOpen(true)}
                    aria-haspopup="dialog"
                    aria-expanded={moreOpen}
                    className={baseClass}
                  >
                    {content}
                  </button>
                ) : (
                  <Link
                    to={to}
                    className={baseClass}
                    aria-current={isCurrent ? 'page' : undefined}
                  >
                    {content}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      </nav>

      <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} title="More">
        <div className="flex flex-col gap-1">
          {SECONDARY.map(({ to, label, Icon }) => (
            <button
              key={to}
              type="button"
              onClick={() => handleSheetNav(to)}
              className="flex items-center gap-4 px-3 py-3 rounded-md text-left text-text-primary hover:bg-surface-elevated press-down tap-target focus-visible:outline-none focus-visible:shadow-glow"
            >
              <Icon className="h-5 w-5 text-text-secondary" aria-hidden />
              <span className="font-sans text-sm">{label}</span>
            </button>
          ))}

          <div className="h-px bg-border my-3" />

          <button
            type="button"
            onClick={() => {
              setMoreOpen(false);
              void logout();
            }}
            className="flex items-center gap-4 px-3 py-3 rounded-md text-left text-error hover:bg-surface-elevated press-down tap-target focus-visible:outline-none focus-visible:shadow-glow"
          >
            <LogOut className="h-5 w-5" aria-hidden />
            <span className="font-sans text-sm">Sign out</span>
          </button>
        </div>
      </Sheet>
    </>
  );
}
