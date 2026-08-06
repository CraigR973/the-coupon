import { Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { installResumeRefetch } from './lib/resumeRefetch';
import { lazyRoute } from './lib/lazyRoute';
import { AuthProvider } from './contexts/AuthContext';
import { LeagueProvider } from './contexts/LeagueContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ErrorBoundary } from './components/ErrorBoundary';
import { UpdateBanner } from './components/UpdateBanner';
import { InstallPromptController } from './components/InstallPromptController';
import { NotificationsPromptController } from './components/NotificationsPromptController';
import { Skeleton } from './components/ui/skeleton';
import { LoginPage } from './pages/LoginPage';
import { JoinPage } from './pages/JoinPage';
import { DEFAULT_LEAGUE_SLUG } from './lib/api';

// Layout pulls in framer-motion via NavBar/OfflineBanner; lazy-loading it keeps
// those deps out of the unauthenticated /login chunk.
const Layout = lazyRoute(() => import('./components/Layout').then((m) => ({ default: m.Layout })));

// Lazy-loaded routes: only login + join ship eagerly so the unauth entry is fast.
const DashboardPage = lazyRoute(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })));
const CouponPickPage = lazyRoute(() => import('./pages/CouponPickPage').then((m) => ({ default: m.CouponPickPage })));
const CouponCombinedPage = lazyRoute(() =>
  import('./pages/CouponCombinedPage').then((m) => ({ default: m.CouponCombinedPage })),
);
const FootballPage = lazyRoute(() => import('./pages/FootballPage').then((m) => ({ default: m.FootballPage })));
const LeaderboardPage = lazyRoute(() => import('./pages/LeaderboardPage').then((m) => ({ default: m.LeaderboardPage })));
const PlayerProfilePage = lazyRoute(() => import('./pages/PlayerProfilePage').then((m) => ({ default: m.PlayerProfilePage })));
const OfflinePage = lazyRoute(() => import('./pages/OfflinePage').then((m) => ({ default: m.OfflinePage })));
const SettingsPage = lazyRoute(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })));
const AboutPage = lazyRoute(() => import('./pages/AboutPage').then((m) => ({ default: m.AboutPage })));

// League management
const MyLeaguesPage = lazyRoute(() => import('./pages/MyLeaguesPage').then((m) => ({ default: m.MyLeaguesPage })));
const CreateLeaguePage = lazyRoute(() => import('./pages/CreateLeaguePage').then((m) => ({ default: m.CreateLeaguePage })));
const DiscoverLeaguesPage = lazyRoute(() =>
  import('./pages/DiscoverLeaguesPage').then((m) => ({ default: m.DiscoverLeaguesPage })),
);
const JoinByCodePage = lazyRoute(() => import('./pages/JoinByCodePage').then((m) => ({ default: m.JoinByCodePage })));
const LeagueMembersPage = lazyRoute(() => import('./pages/LeagueMembersPage').then((m) => ({ default: m.LeagueMembersPage })));
const LeagueSettingsPage = lazyRoute(() =>
  import('./pages/LeagueSettingsPage').then((m) => ({ default: m.LeagueSettingsPage })),
);
const LeagueJoinRequestsPage = lazyRoute(() =>
  import('./pages/LeagueJoinRequestsPage').then((m) => ({ default: m.LeagueJoinRequestsPage })),
);
const LeagueAdminInvitesPage = lazyRoute(() =>
  import('./pages/LeagueAdminInvitesPage').then((m) => ({ default: m.LeagueAdminInvitesPage })),
);

// Auth / onboarding
const ForgotPinPage = lazyRoute(() => import('./pages/ForgotPinPage').then((m) => ({ default: m.ForgotPinPage })));
const WelcomePage = lazyRoute(() => import('./pages/WelcomePage').then((m) => ({ default: m.WelcomePage })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
});

// Widen the focus signal so refetchOnWindowFocus also fires on iOS PWA warm
// resume (pageshow/bfcache restore), not just visibilitychange. See resumeRefetch.ts.
installResumeRefetch();

function RouteFallback() {
  return (
    <div className="space-y-4" aria-label="Loading page">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-[320px] w-full" />
    </div>
  );
}

/**
 * Wraps protected routes with LeagueProvider.
 * Must be inside BrowserRouter (for useNavigate) and QueryClientProvider (for useQuery).
 */
function LeagueAwareLayout() {
  return (
    <LeagueProvider>
      <Outlet />
    </LeagueProvider>
  );
}

/**
 * Redirects /leagues/:slug/members and siblings to the new /admin/* sub-paths.
 * Reads :slug from URL params so the slug is preserved exactly.
 */
function LeagueAdminRedirect({ suffix }: { suffix: string }) {
  const { slug = DEFAULT_LEAGUE_SLUG } = useParams<{ slug: string }>();
  return <Navigate to={`/leagues/${slug}/admin/${suffix}`} replace />;
}

/**
 * The league landing page is the leaderboard itself — entering a league drops
 * you straight onto the full standings.
 */
function LeagueHomeRedirect() {
  const { slug = DEFAULT_LEAGUE_SLUG } = useParams<{ slug: string }>();
  return <Navigate to={`/leagues/${slug}/leaderboard`} replace />;
}

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <UpdateBanner />
            <InstallPromptController />
            <NotificationsPromptController />
            <Toaster position="bottom-right" richColors closeButton />
            <ErrorBoundary>
              <Suspense fallback={<RouteFallback />}>
                <Routes>
                  {/* Public routes (no auth, no league context) */}
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/forgot-pin" element={<ForgotPinPage />} />
                  <Route path="/join/:token" element={<JoinPage />} />
                  <Route path="/welcome" element={<WelcomePage />} />

                  {/* Protected: authenticated + LeagueProvider */}
                  <Route element={<ProtectedRoute />}>
                    <Route element={<LeagueAwareLayout />}>
                      {/* Standard app shell with TopBar + TabBar */}
                      <Route element={<Layout />}>
                        <Route path="/" element={<DashboardPage />} />
                        <Route path="/predictions" element={<CouponPickPage />} />
                        <Route path="/predictions/coupon" element={<CouponCombinedPage />} />
                        <Route path="/predictions/football" element={<FootballPage />} />
                        <Route path="/settings" element={<SettingsPage />} />
                        <Route path="/about" element={<AboutPage />} />
                        <Route path="/offline" element={<OfflinePage />} />

                        {/* Old top-level routes → redirect to the Leagues hub */}
                        <Route path="/leaderboard" element={<Navigate to="/leagues" replace />} />

                        {/* League management — public (all members) */}
                        <Route path="/leagues" element={<MyLeaguesPage />} />
                        <Route path="/leagues/new" element={<CreateLeaguePage />} />
                        <Route path="/leagues/discover" element={<DiscoverLeaguesPage />} />
                        <Route path="/leagues/join" element={<JoinByCodePage />} />
                        <Route path="/leagues/:slug" element={<LeagueHomeRedirect />} />

                        {/* Per-league standings */}
                        <Route path="/leagues/:slug/leaderboard" element={<LeaderboardPage />} />
                        <Route path="/leagues/:slug/players/:playerId" element={<PlayerProfilePage />} />

                        {/* Old per-league member/settings paths → redirect to /admin/* sub-paths */}
                        <Route path="/leagues/:slug/members" element={<LeagueAdminRedirect suffix="members" />} />
                        <Route path="/leagues/:slug/settings" element={<LeagueAdminRedirect suffix="settings" />} />
                        <Route path="/leagues/:slug/requests" element={<LeagueAdminRedirect suffix="requests" />} />

                        {/* Per-league admin */}
                        <Route path="/leagues/:slug/admin/members" element={<LeagueMembersPage />} />
                        <Route path="/leagues/:slug/admin/settings" element={<LeagueSettingsPage />} />
                        <Route path="/leagues/:slug/admin/requests" element={<LeagueJoinRequestsPage />} />
                        <Route path="/leagues/:slug/admin/invites" element={<LeagueAdminInvitesPage />} />
                      </Route>
                    </Route>
                  </Route>

                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
