import { NavLink, Link, useLocation } from 'react-router-dom';
import { Moon, Sun, Settings, LogOut, User } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { Brand } from '@/components/Brand';
import { Avatar } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

interface DesktopNavItem {
  to: string;
  label: string;
  matchPrefix?: string[];
  excludePrefix?: string[];
}

const DESKTOP_NAV: ReadonlyArray<DesktopNavItem> = [
  { to: '/', label: 'Home' },
  {
    to: '/predictions',
    label: 'Coupon',
    matchPrefix: ['/predictions'],
    excludePrefix: ['/predictions/football'],
  },
  {
    to: '/predictions/football',
    label: 'Football',
    matchPrefix: ['/predictions/football'],
  },
  { to: '/leagues', label: 'Leagues' },
  { to: '/settings', label: 'Settings' },
];

function desktopNavActive(pathname: string, item: DesktopNavItem): boolean {
  if (item.excludePrefix?.some((prefix) => pathname.startsWith(prefix))) return false;
  if (item.matchPrefix) return item.matchPrefix.some((prefix) => pathname.startsWith(prefix));
  if (item.to === '/') return pathname === '/';
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

export function TopBar() {
  const { player, logout } = useAuth();
  const { resolved, setMode } = useTheme();
  const { pathname } = useLocation();
  function toggleTheme() {
    setMode(resolved === 'dark' ? 'light' : 'dark');
  }

  const themeToggle = (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={resolved === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      className="tap-target inline-flex items-center justify-center rounded-md text-text-secondary hover:text-text-primary press-down focus-visible:outline-none focus-visible:shadow-glow"
    >
      {resolved === 'dark' ? (
        <Sun className="h-4 w-4" aria-hidden />
      ) : (
        <Moon className="h-4 w-4" aria-hidden />
      )}
    </button>
  );

  const avatarMenu = player ? (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`Account menu (${player.displayName})`}
        className="inline-flex items-center gap-2 press-down rounded-full focus-visible:outline-none focus-visible:shadow-glow"
      >
        <span className="hidden sm:inline text-sm text-text-secondary font-sans">
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
        'bg-surface/90 backdrop-blur-md border-b border-border',
        'pt-[calc(env(safe-area-inset-top,0px)+1rem)] md:pt-safe',
      )}
    >
      <div className="max-w-6xl mx-auto px-4 h-16 md:h-14 flex items-center gap-4">
        {/* ── Mobile layout (< md): toggle | centred brand | avatar ── */}
        <div className="relative flex md:hidden items-center w-full justify-between">
          {themeToggle}
          <NavLink
            to="/"
            aria-label="Home"
            className="press-down absolute inset-y-0 left-1/2 -translate-x-1/2 flex items-center"
          >
            <Brand variant="compact" size={46} />
          </NavLink>
          {avatarMenu}
        </div>

        {/* ── Desktop layout (md+): brand | nav | toggle + badge + avatar ── */}
        <NavLink to="/" aria-label="Home" className="press-down hidden md:block shrink-0">
          <Brand variant="compact" size={46} />
        </NavLink>

        <nav aria-label="Main navigation" className="hidden md:flex items-center gap-1 flex-1">
          {DESKTOP_NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              aria-current={desktopNavActive(pathname, item) ? 'page' : undefined}
              className={cn(
                'px-3 py-1.5 rounded-sm text-sm font-medium font-sans tracking-tight transition-colors press-down',
                'focus-visible:outline-none focus-visible:shadow-glow',
                desktopNavActive(pathname, item)
                  ? 'bg-primary/15 text-primary'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-elevated',
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-3">
          {themeToggle}
          {avatarMenu}
        </div>
      </div>
    </header>
  );
}
