import {addressedGamesDestination,isAddressedGamePath} from '../lib/leagues';
import { useGameNavigation } from '../hooks/useGameIntents';
import { gamesTabDestination, leagueForGames } from '../lib/gameSwitch';
import { NavLink, Link, useLocation } from 'react-router-dom';
import { Settings, LogOut, User } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useLeague } from '@/contexts/LeagueContext';
import { Brand } from '@/components/Brand';
import { NotificationBell } from '@/components/NotificationBell';
import { Avatar } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
  FOOTBALL_PATH,
  isCouponPath,
  isFootballPath,
  isLeagueHubPath,
  predictionsPath,
} from '@/lib/leagues';
import { cn } from '@/lib/utils';

interface DesktopNavItem {
  to: string;
  label: string;
  /**
   * What the link reads below `md`. The full label stays its accessible name, so the
   * visible word is still part of what a screen reader or voice control hears.
   */
  shortLabel?: string;
  /** Shown from `md` up only; the account menu carries the same destination. */
  wideOnly?: boolean;
  /** Whether this entry owns `pathname`. */
  match: (pathname: string) => boolean;
}

/** The desktop mirror of `TabBar`'s primary tabs — same targets, same rules. */
function desktopNav(slug: string | null, gamesPath?: string): ReadonlyArray<DesktopNavItem> {
  return [
    { to: '/', label: 'Home', match: (p) => p === '/' },
    { to: gamesPath??predictionsPath(slug), label: gamesPath?'Games':'Coupon', match: p=>isCouponPath(p)||isAddressedGamePath(p) },
    { to: FOOTBALL_PATH, label: 'Football Stats', shortLabel: 'Football', match: isFootballPath },
    { to: '/leagues', label: 'Leagues', match: isLeagueHubPath },
    {
      to: '/settings',
      label: 'Settings',
      wideOnly: true,
      match: (p) => p === '/settings' || p.startsWith('/settings/'),
    },
  ];
}

export function TopBar() {
  const { player, logout } = useAuth();
  const { activeSlug, hasLeagues } = useLeague();
  const {pathname}=useLocation();
  // Batch 232: the Games tab opens the game that needs the member first, not the archive.
  const addressedArchive=addressedGamesDestination(pathname);
  const gameLeague=leagueForGames(useGameNavigation(),addressedArchive,activeSlug);
  const gamesPath=gameLeague?gamesTabDestination(gameLeague):addressedArchive;
  const navItems = desktopNav(hasLeagues ? activeSlug : null,gamesPath);

  const avatarMenu = player ? (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`Account menu (${player.displayName})`}
        className="inline-flex items-center gap-2 press-down rounded-full focus-visible:outline-hidden focus-visible:shadow-glow"
      >
        <span className="hidden lg:inline text-sm text-text-secondary font-sans">
          {player.displayName}
        </span>
        <Avatar name={player.displayName} size="sm" src={player.avatarUrl} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          {/* Career-scoped, matching TabBar's entry — the same label must not
              mean two different pages depending on which bar you reach it from. */}
          <Link to="/profile">
            <User className="h-4 w-4" aria-hidden />
            My profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/settings">
            <Settings className="h-4 w-4" aria-hidden />
            Settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void logout()}>
          <LogOut className="h-4 w-4" aria-hidden />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  ) : null;

  return (
    <header
      className={cn(
        'sticky top-0 z-header',
        'bg-surface border-b border-border',
        'pt-safe',
      )}
    >
      <div className="max-w-7xl mx-auto px-4 h-[52px] sm:h-14 flex items-center gap-4">
        {/* ── Mobile layout (< sm): brand | bell + avatar ──
            Batch 242: the bell lived inside Home's hero and nowhere else, and the
            light/dark switch took the left slot on every screen. The bell now sits by the
            avatar on every signed-in screen; the theme choice is in Settings → Appearance. */}
        <div className="relative flex sm:hidden items-center w-full justify-end">
          <NavLink
            to="/"
            aria-label="Home"
            className="press-down absolute inset-y-0 left-0 flex items-center"
          >
            <Brand variant="compact" size={46} />
          </NavLink>
          <div className="flex items-center gap-2">
            {player && <NotificationBell />}
            {avatarMenu}
          </div>
        </div>

        {/* ── Desktop layout (sm+): brand | nav | bell + avatar ── */}
        <NavLink to="/" aria-label="Home" className="press-down hidden sm:block shrink-0">
          <Brand variant="compact" size={46} />
        </NavLink>

        {/* Batch 170. A 1280 display at 200% zoom is 640 CSS px, the bottom of this
            layout, where the five links overflowed the bar and pushed the account menu off
            screen. Below `md` the bar sheds what has another way in: Settings (also in the
            account menu) and "Stats". The name beside the avatar waits for `lg`, because
            names run to 32 characters. Links never wrap, so the bar stays one 56px row. */}
        <nav aria-label="Main navigation" className="hidden sm:flex items-center gap-1 flex-1">
          {navItems.map((item) => (
            <Link
              key={item.label}
              to={item.to}
              aria-current={item.match(pathname) ? 'page' : undefined}
              aria-label={item.shortLabel ? item.label : undefined}
              className={cn(
                'whitespace-nowrap px-3 py-1.5 rounded-sm text-sm font-medium font-sans tracking-tight transition-colors press-down',
                'focus-visible:outline-hidden focus-visible:shadow-glow',
                item.wideOnly && 'hidden md:block',
                item.match(pathname)
                  ? 'bg-primary/[0.08] dark:bg-primary/15 text-text-primary'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-elevated',
              )}
            >
              {item.shortLabel ? (
                <>
                  <span className="md:hidden">{item.shortLabel}</span>
                  <span className="hidden md:inline">{item.label}</span>
                </>
              ) : (
                item.label
              )}
            </Link>
          ))}
        </nav>

        <div className="hidden sm:flex items-center gap-3">
          {player && <NotificationBell />}
          {avatarMenu}
        </div>
      </div>
    </header>
  );
}
