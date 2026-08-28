import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { axe } from 'jest-axe';
import axeCore from 'axe-core';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { LoginPage } from '@/pages/LoginPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { TopBar } from '@/components/TopBar';
import { SettingsPage } from '@/pages/SettingsPage';

// Disable color-contrast: jsdom cannot evaluate CSS custom properties.
// All other axe rules run at full severity.
const AXE_CONFIG = {
  rules: { 'color-contrast': { enabled: false } },
};

// ---------------------------------------------------------------------------
// Shared auth fixtures
// ---------------------------------------------------------------------------

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

function stubAuth() {
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => {
      if (k === 'coupon_player') return STORED_PLAYER;
      if (k === 'coupon_access') return FAKE_JWT;
      return null;
    },
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });
}

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

// ---------------------------------------------------------------------------
// LoginPage
// ---------------------------------------------------------------------------

vi.mock('@/hooks/usePushSubscription', () => ({
  usePushSubscription: () => ({
    permission: 'default',
    isSubscribed: false,
    isLoading: false,
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
  }),
}));

vi.mock('@/hooks/useInstallPrompt', () => ({
  useInstallPrompt: () => ({
    canInstall: false,
    isInstalled: false,
    isIosSafari: false,
    prompt: vi.fn(),
  }),
}));

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('Accessibility — LoginPage', () => {
  it('has no axe violations on initial render (text input fallback)', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve({ ok: false }));
    const { container } = render(
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <LoginPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await new Promise((r) => setTimeout(r, 50));
    const results = await axe(container, AXE_CONFIG);
    expect(results).toHaveNoViolations();
  });

  it('has no axe violations on the display-name + PIN form', async () => {
    const { container } = render(
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <LoginPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await new Promise((r) => setTimeout(r, 50));
    const results = await axe(container, AXE_CONFIG);
    expect(results).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// NavBar
// ---------------------------------------------------------------------------

describe('Accessibility — TopBar', () => {
  it('has no axe violations', async () => {
    stubAuth();
    vi.stubGlobal('fetch', () => Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }));
    const { container } = render(
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <LeagueProvider>
              <TopBar />
            </LeagueProvider>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const results = await axe(container, AXE_CONFIG);
    expect(results).toHaveNoViolations();
  });

  it('nav has an accessible label', () => {
    stubAuth();
    vi.stubGlobal('fetch', () => Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }));
    const { container } = render(
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <LeagueProvider>
              <TopBar />
            </LeagueProvider>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const nav = container.querySelector('nav');
    expect(nav?.getAttribute('aria-label')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// SettingsPage
// ---------------------------------------------------------------------------

describe('Accessibility — SettingsPage', () => {
  function renderSettings() {
    stubAuth();
    vi.stubGlobal('fetch', (url: string, opts?: RequestInit) => {
      if (url.includes('/api/v1/notifications/preferences') && (!opts?.method || opts.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              deadline_warning: true,
              predict_reminder: true,
              pick_confirmation: false,
              match_locked: true,
              result_detected: true,
              leaderboard_shift: true,
              round_complete: true,
              match_postponed: true,
              special_results: true,
              global_mute: false,
              quiet_hours_start: null,
              quiet_hours_end: null,
              leagues: [],
            }),
        });
      }
      return Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) });
    });
    Object.defineProperty(window, 'PushManager', { value: {}, writable: true, configurable: true });
    Object.defineProperty(navigator, 'serviceWorker', { value: {}, writable: true, configurable: true });
    return render(
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <SettingsPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('has no axe violations', async () => {
    const { container } = renderSettings();
    await waitFor(() => expect(container.querySelector('[role="switch"]')).toBeTruthy());
    const results = await axe(container, AXE_CONFIG);
    expect(results).toHaveNoViolations();
  });

  it('toggle switches have aria-checked and aria-label', async () => {
    const { container } = renderSettings();
    await waitFor(() => expect(container.querySelector('[role="switch"]')).toBeTruthy());
    const switches = container.querySelectorAll('[role="switch"]');
    expect(switches.length).toBeGreaterThan(0);
    switches.forEach((sw) => {
      expect(sw.getAttribute('aria-checked')).toMatch(/^(true|false)$/);
      expect(sw.getAttribute('aria-label')).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// Page-level landmark and heading rules — UX-07
// ---------------------------------------------------------------------------
//
// Of the three rules UX-07 reported, only `region` can be asserted here, and the
// other two are checked in a real browser by `e2e/prod-bundle-a11y.spec.ts`.
// That split is forced, not stylistic:
//
//   * `landmark-one-main` and `page-has-heading-one` resolve through axe's
//     visibility check, which needs layout. jsdom reports zero dimensions for
//     everything, so axe returns both as `incomplete` — "needs review" — for any
//     markup at all. Measured against this suite: no <main> and no <h1> gives the
//     same `incomplete` as a correct page and as a page with three <main>s. An
//     assertion on them here would be green whatever these pages contained.
//   * `region` does produce a real verdict under jsdom, and it is the rule that
//     covers the bulk of UX-07 — 22 of the 26 reported nodes.
//
// It also has to be `axe-core` directly rather than the `axe()` wrapper the tests
// above use. Handed anything not already inside `<body>`, jest-axe 10.0.0 falls
// back to `document.body.innerHTML = element.outerHTML` (`mount()`), which
// re-roots the context at `<body>` and replaces React's live container with a
// string clone — leaving Testing Library's auto-cleanup holding a detached node
// it cannot remove, so each case leaks its page into the next.
const PAGE_LEVEL_RULES = ['landmark-one-main', 'page-has-heading-one', 'region'];

describe.each(['light', 'dark'])(
  'Accessibility — unauthenticated pages, page-level rules (%s theme)',
  (theme) => {
    beforeEach(() => {
      // What ThemeContext.applyTheme() puts on <html>. These rules are structural
      // and never read colour, but UX-07 was reported against both themes and
      // reproducing the sweep faithfully costs one class swap.
      document.documentElement.classList.remove('light', 'dark');
      document.documentElement.classList.add(theme);
    });

    it.each([
      ['LoginPage', LoginPage],
      ['RegisterPage', RegisterPage],
    ])('%s puts all content in a landmark, under one <h1>', async (_name, Page) => {
      render(
        <QueryClientProvider client={makeQueryClient()}>
          <MemoryRouter>
            <AuthProvider>
              <Page />
            </AuthProvider>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      await waitFor(() => expect(document.querySelector('form')).toBeTruthy());

      const results = await axeCore.run(document.documentElement, {
        runOnly: { type: 'rule', values: PAGE_LEVEL_RULES },
      });
      expect(results.violations.map((v) => v.id)).toEqual([]);

      // The structural half of what the two layout-dependent rules would assert,
      // and stricter than they are: axe passes `landmark-one-main` on a page with
      // three <main>s and `page-has-heading-one` on one with three <h1>s, since
      // both ask only whether at least one exists.
      expect(document.querySelectorAll('main')).toHaveLength(1);
      expect(document.querySelectorAll('h1')).toHaveLength(1);
    });
  },
);
