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
import {
  CombinedCouponRedirect,
  PredictionsRedirect,
} from './components/PredictionsRedirect';
import { COUPON_SECTION_HASH } from './lib/leagues';
import { RouteFallback } from './components/RouteFallback';
import { UpdateBanner } from './components/UpdateBanner';
import { InstallPromptController } from './components/InstallPromptController';
import { NotificationsPromptController } from './components/NotificationsPromptController';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { JoinPage } from './pages/JoinPage';
import { DEFAULT_LEAGUE_SLUG } from './lib/api';

// Layout pulls in framer-motion via NavBar/OfflineBanner; lazy-loading it keeps
// those deps out of the unauthenticated /login chunk.
const Layout = lazyRoute(() => import('./components/Layout').then((m) => ({ default: m.Layout })));

// Lazy-loaded routes: only login, register and join ship eagerly so the unauth entry
// is fast. Register is in that set because it is now half of what a shared link leads to.
const DashboardPage = lazyRoute(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })));
const CurrentRoundPage = lazyRoute(() => import('./pages/CurrentRoundPage').then((m) => ({ default: m.CurrentRoundPage })));
const FootballPage = lazyRoute(() => import('./pages/FootballPage').then((m) => ({ default: m.FootballPage })));
const ResultsPage = lazyRoute(() => import('./pages/ResultsPage').then((m) => ({ default: m.ResultsPage })));
const LeaderboardPage = lazyRoute(() => import('./pages/LeaderboardPage').then((m) => ({ default: m.LeaderboardPage })));
const PlayerProfilePage = lazyRoute(() => import('./pages/PlayerProfilePage').then((m) => ({ default: m.PlayerProfilePage })));
const CareerProfilePage = lazyRoute(() => import('./pages/CareerProfilePage').then((m) => ({ default: m.CareerProfilePage })));
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
const LeagueAuditLogPage = lazyRoute(() =>
  import('./pages/LeagueAuditLogPage').then((m) => ({ default: m.LeagueAuditLogPage })),
);

// Auth / onboarding
const ForgotPinPage = lazyRoute(() => import('./pages/ForgotPinPage').then((m) => ({ default: m.ForgotPinPage })));
const SetPinPage = lazyRoute(() => import('./pages/SetPinPage').then((m) => ({ default: m.SetPinPage })));
const WelcomePage = lazyRoute(() => import('./pages/WelcomePage').then((m) => ({ default: m.WelcomePage })));

// Site admin (Batch 66). Lazy like everything else, and behind `requireAdmin` — a
// member who is not a site admin never loads a byte of it.
const AdminPlayersPage = lazyRoute(() =>
  import('./pages/admin/PlayersPage').then((m) => ({ default: m.PlayersPage })),
);
const AdminInvitesPage = lazyRoute(() =>
  import('./pages/admin/InvitesPage').then((m) => ({ default: m.InvitesPage })),
);
const AdminAllLeaguesPage = lazyRoute(() =>
  import('./pages/admin/AllLeaguesPage').then((m) => ({ default: m.AllLeaguesPage })),
);
const AdminDashboardPage = lazyRoute(() =>
  import('./pages/admin/DashboardPage').then((m) => ({ default: m.AdminDashboardPage })),
);
const AdminSyncPage = lazyRoute(() =>
  import('./pages/admin/SyncPage').then((m) => ({ default: m.SyncPage })),
);
const AdminResultsPage = lazyRoute(() =>
  import('./pages/admin/ResultsPage').then((m) => ({ default: m.AdminResultsPage })),
);

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
                  <Route path="/register" element={<RegisterPage />} />
                  <Route path="/forgot-pin" element={<ForgotPinPage />} />
                  {/* The far end of an admin PIN reset. Public, because the member has
                      no credential to authenticate with — that is the whole state. */}
                  <Route path="/set-pin" element={<SetPinPage />} />
                  <Route path="/join/:token" element={<JoinPage />} />
                  <Route path="/welcome" element={<WelcomePage />} />

                  {/* Protected: authenticated + LeagueProvider */}
                  <Route element={<ProtectedRoute />}>
                    <Route element={<LeagueAwareLayout />}>
                      {/* Standard app shell with TopBar + TabBar */}
                      <Route element={<Layout />}>
                        <Route path="/" element={<DashboardPage />} />

                        {/* The weekly coupon, addressed at a league so a week can be
                            linked, shared and reopened at the league it came from. */}
                        <Route path="/leagues/:slug/predictions" element={<CurrentRoundPage />} />
                        {/* The combined coupon is a section of the round now (Batch 105),
                            so its old address redirects into it rather than answering. */}
                        <Route
                          path="/leagues/:slug/predictions/coupon"
                          element={<CombinedCouponRedirect />}
                        />
                        <Route path="/leagues/:slug/predictions/results" element={<ResultsPage />} />

                        {/* Football Stats reads the whole fixture pool, so it names no
                            league — Batch 51 took it off the coupon's sub-nav and out
                            of `/leagues/`. */}
                        <Route path="/football" element={<FootballPage />} />

                        {/* The slug-less paths they replaced — every link, bookmark and
                            reminder minted before this batch still lands correctly. */}
                        <Route
                          path="/predictions"
                          element={
                            <PredictionsRedirect section="">
                              <CurrentRoundPage />
                            </PredictionsRedirect>
                          }
                        />
                        <Route
                          path="/predictions/coupon"
                          element={
                            <PredictionsRedirect section="" hash={COUPON_SECTION_HASH}>
                              <CurrentRoundPage />
                            </PredictionsRedirect>
                          }
                        />
                        <Route
                          path="/predictions/results"
                          element={
                            <PredictionsRedirect section="/results">
                              <ResultsPage />
                            </PredictionsRedirect>
                          }
                        />

                        {/* The two addresses Football Stats used to answer at. Kept as
                            redirects for the same reason as the block above — a member
                            who bookmarked the tables should still land on them. */}
                        <Route
                          path="/leagues/:slug/predictions/football"
                          element={<Navigate to="/football" replace />}
                        />
                        <Route
                          path="/predictions/football"
                          element={<Navigate to="/football" replace />}
                        />

                        {/* The member's own record across every league. Per-league
                            records keep their own route under /leagues/:slug. */}
                        <Route path="/profile" element={<CareerProfilePage />} />
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
                        <Route
                          path="/leagues/:slug/admin/audit-log"
                          element={<LeagueAuditLogPage />}
                        />

                        {/* Site admin — people and access (Batch 66). A second gate
                            inside the authenticated one: `requireAdmin` bounces a
                            player home rather than rendering a screen whose every
                            request would 403. */}
                        <Route element={<ProtectedRoute requireAdmin />}>
                          <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
                          <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
                          <Route path="/admin/players" element={<AdminPlayersPage />} />
                          <Route path="/admin/results" element={<AdminResultsPage />} />
                          <Route path="/admin/sync" element={<AdminSyncPage />} />
                          <Route path="/admin/invites" element={<AdminInvitesPage />} />
                          <Route path="/admin/leagues" element={<AdminAllLeaguesPage />} />
                        </Route>
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
