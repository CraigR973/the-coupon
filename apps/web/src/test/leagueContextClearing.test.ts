import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  LAST_VIEWED_LEAGUE_KEY,
  LEAGUE_SWITCH_SCROLL_KEY,
  forgetLeagueContext,
} from '@/lib/leagueRecency';
import { clearTokens, storeTokens } from '@/lib/tokens';

/**
 * Batch 143. `clearTokens()` removed the access, refresh and player keys and nothing
 * else, so `coupon_last_viewed_league` — a private league's slug **and name** —
 * survived a logout on a shared browser and pre-selected itself for whoever signed in
 * next. The names of the leagues someone belongs to are not public, and on a shared
 * device the next person is by definition not that someone.
 */

const PLAYER = { id: 'p1', displayName: 'Alice', role: 'player' as const, timezone: 'UTC' };

function seedLeagueContext() {
  localStorage.setItem(
    LAST_VIEWED_LEAGUE_KEY,
    JSON.stringify({ slug: 'the-quiet-ones', name: 'The Quiet Ones' }),
  );
  sessionStorage.setItem(LEAGUE_SWITCH_SCROLL_KEY, '240');
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal('caches', { delete: vi.fn().mockResolvedValue(true) });
});

describe('logging out', () => {
  it('leaves no league key behind', async () => {
    storeTokens('access', 'refresh', PLAYER);
    seedLeagueContext();

    await clearTokens();

    expect(localStorage.getItem(LAST_VIEWED_LEAGUE_KEY)).toBeNull();
    expect(sessionStorage.getItem(LEAGUE_SWITCH_SCROLL_KEY)).toBeNull();
  });

  it('leaves no `coupon_` key naming a league behind, whatever it is called', async () => {
    // Stricter than the two keys above, because the defect was not "we forgot this key"
    // but "clearTokens only knows about the token keys". A third one added later has to
    // fail here rather than on a shared laptop.
    storeTokens('access', 'refresh', PLAYER);
    seedLeagueContext();

    await clearTokens();

    const survivors = [
      ...Object.keys(localStorage).map((key) => `local:${key}`),
      ...Object.keys(sessionStorage).map((key) => `session:${key}`),
    ].filter((key) => /league/i.test(key));
    expect(survivors).toEqual([]);
  });

  it('still clears the tokens themselves', async () => {
    storeTokens('access', 'refresh', PLAYER);
    await clearTokens();
    expect(localStorage.getItem('coupon_access')).toBeNull();
    expect(localStorage.getItem('coupon_refresh')).toBeNull();
    expect(localStorage.getItem('coupon_player')).toBeNull();
  });

  it("keeps the preferences that are the device's, not the account's", async () => {
    // The theme belongs to whoever is holding the phone, so a logout must not reset it.
    localStorage.setItem('coupon_theme', 'light');
    storeTokens('access', 'refresh', PLAYER);

    await clearTokens();

    expect(localStorage.getItem('coupon_theme')).toBe('light');
  });
});

describe('forgetLeagueContext', () => {
  it('is safe when there is nothing stored', () => {
    expect(() => forgetLeagueContext()).not.toThrow();
  });

  it('is safe when storage itself throws', () => {
    // A private window, blocked site data, or a browser that refuses access. Logging out
    // must still log the member out.
    const thrower = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
      removeItem: () => {
        throw new Error('denied');
      },
      clear: () => undefined,
      key: () => null,
      length: 0,
    };
    vi.stubGlobal('localStorage', thrower);
    vi.stubGlobal('sessionStorage', thrower);

    expect(() => forgetLeagueContext()).not.toThrow();

    vi.unstubAllGlobals();
  });
});

describe('signing in as somebody else', () => {
  it('does not hand the previous account\'s league to the next one', async () => {
    // The shared-browser case that logging out does not cover: sign out, sign in as
    // someone else, and the switcher pre-selects a league the new member may not be in.
    const { AuthProvider } = await import('@/contexts/AuthContext');
    const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query');
    const { render, waitFor } = await import('@testing-library/react');
    const { createElement, useEffect } = await import('react');
    const { useAuth } = await import('@/contexts/AuthContext');

    seedLeagueContext();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: 'a',
          refresh_token: 'r',
          player: { id: 'p2', display_name: 'Bob', role: 'player', timezone: 'UTC' },
        }),
      }),
    );

    function SignIn() {
      const { login } = useAuth();
      useEffect(() => {
        void login('Bob', '1234');
      }, [login]);
      return null;
    }

    render(
      createElement(
        QueryClientProvider,
        { client: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
        createElement(AuthProvider, null, createElement(SignIn, null)),
      ),
    );

    await waitFor(() => expect(localStorage.getItem('coupon_player')).toContain('Bob'));
    expect(localStorage.getItem(LAST_VIEWED_LEAGUE_KEY)).toBeNull();
    expect(sessionStorage.getItem(LEAGUE_SWITCH_SCROLL_KEY)).toBeNull();
  });
});
