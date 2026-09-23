import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  clearApiCaches,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  getStoredPlayer,
  isAccessTokenExpired,
  storeTokens,
  type StoredPlayer,
} from '../lib/tokens';
import { API_BASE, PIN_NOT_SET, refreshStoredSession } from '../lib/api';

interface AuthState {
  player: StoredPlayer | null;
  isLoading: boolean;
  sessionUnlockRequired: boolean;
  sessionUnlockError: string | null;
  /**
   * A stored session is being resumed from its refresh token (Batch 123). True only
   * between mount and that answer, and only when there was something to resume — so
   * the PIN screen is never shown to a member who was about to be let in without it.
   */
  sessionResuming: boolean;
}

interface AuthContextValue extends AuthState {
  login: (displayName: string, pin: string) => Promise<void>;
  /**
   * Create an account and land signed in, in one round trip. The API answers
   * `/register` with the same token pair as `/login`, so the two share everything
   * after the fetch — see `establishSession`.
   */
  register: (displayName: string, pin: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Update a subset of the stored player (e.g. after avatar upload). */
  updatePlayer: (patch: Partial<StoredPlayer>) => void;
  unlockStoredSession: (pin: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const INVALID_PIN = 'Invalid PIN. Try again or log out if this is not your account.';
const UNREACHABLE = 'Could not reach the server. Check your connection and try again.';

/**
 * What the unlock screen says about a refusal.
 *
 * Batch 123. Every failure used to read "Invalid PIN", including a 423 from an
 * account-wide lock somebody else is holding open and a 429 from a limit already spent
 * — so a member whose PIN is perfectly good was told to doubt it, and the obvious next
 * move is to reset a credential that works.
 *
 * Mapped from the status rather than read out of the message, so a terse `detail` from
 * the API cannot quietly replace a sentence written for a member.
 */
function unlockMessage(status: number): string {
  if (status === 423) {
    return 'Too many failed sign-in attempts on this account. It unlocks again in about fifteen minutes — your PIN has not changed.';
  }
  if (status === 429) return 'Too many attempts just now. Wait a few minutes and try again.';
  return INVALID_PIN;
}

/** Carries the status through the throw, so the catch says the same thing. */
class UnlockRefused extends Error {
  constructor(readonly status: number) {
    super(unlockMessage(status));
  }
}

function playerFromApiResponse(data: {
  player: {
    id: string;
    display_name: string;
    role: string;
    timezone: string;
    odds_format?: string;
    avatar_url?: string | null;
  };
}): StoredPlayer {
  return {
    id: data.player.id,
    displayName: data.player.display_name,
    role: data.player.role as 'player' | 'admin',
    timezone: data.player.timezone,
    oddsFormat: data.player.odds_format === 'fractional' ? 'fractional' : 'decimal',
    avatarUrl: data.player.avatar_url ?? null,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const initialPlayer = getStoredPlayer();
  const initialRequiresUnlock = !!initialPlayer && !!getRefreshToken() && isAccessTokenExpired();
  const [lockedPlayer, setLockedPlayer] = useState<StoredPlayer | null>(
    initialRequiresUnlock ? initialPlayer : null,
  );
  const [state, setState] = useState<AuthState>({
    player: initialPlayer,
    isLoading: false,
    sessionUnlockRequired: initialRequiresUnlock,
    sessionUnlockError: null,
    sessionResuming: initialRequiresUnlock,
  });

  /**
   * Batch 123. Spend the refresh token before asking for a PIN.
   *
   * An expired *access* token says only that a day has passed. The thirty-day refresh
   * token beside it is what says the session is still good, and until now nothing
   * consulted it on a cold start — the app went straight to the PIN screen. That is
   * ordinarily a nuisance and occasionally a lockout: the account lock is account-wide
   * and display names are on every leaderboard, so any member can hold a rival on that
   * screen for as long as they keep spending five attempts a quarter of an hour.
   *
   * A member with a valid refresh token has already proved who they are. They are let in
   * without touching the one path somebody else can close. If the token is dead, the PIN
   * screen is still there, and nothing about the lockout itself has been relaxed.
   */
  useEffect(() => {
    if (!initialRequiresUnlock) return;
    let cancelled = false;
    void refreshStoredSession().then((player) => {
      if (cancelled) return;
      if (!player) {
        setState((s) => ({ ...s, sessionResuming: false }));
        return;
      }
      setLockedPlayer(null);
      setState({
        player,
        isLoading: false,
        sessionUnlockRequired: false,
        sessionUnlockError: null,
        sessionResuming: false,
      });
    });
    return () => {
      cancelled = true;
    };
    // Runs once: `initialRequiresUnlock` is derived from storage at mount and is what
    // this effect exists to answer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * POST to an endpoint that answers with a token pair, then adopt that identity.
   *
   * Login and registration differ only in the URL and the fallback error text: both
   * return `TokenResponse`, and everything after it — dropping the previous member's
   * cached API responses, clearing react-query, storing the tokens — has to happen
   * identically or a new account inherits the last one's cached screens.
   */
  const establishSession = useCallback(
    async (path: string, body: Record<string, unknown>, fallbackError: string) => {
      setState((s) => ({ ...s, isLoading: true }));
      try {
        const resp = await fetch(`${API_BASE}${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          // The limiter answers with `{ error }`, not `{ detail }`, so a 429 would
          // otherwise fall through to the generic message — which reads as "your
          // details are wrong" and invites an immediate retry against a limit already
          // spent. Registration is 5/hour, tight enough for a household behind one NAT
          // to reach it honestly, so this has to say what actually happened.
          if (resp.status === 429) {
            throw new Error('Too many attempts just now. Wait a few minutes and try again.');
          }
          throw new Error(err.detail ?? fallbackError);
        }
        const data = await resp.json();
        const player = playerFromApiResponse(data);
        await clearApiCaches();
        queryClient.clear();
        storeTokens(data.access_token, data.refresh_token, player);
        setLockedPlayer(null);
        setState({
          player,
          isLoading: false,
          sessionUnlockRequired: false,
          sessionUnlockError: null,
          sessionResuming: false,
        });
      } catch (err) {
        setState((s) => ({ ...s, isLoading: false }));
        throw err;
      }
    },
    [queryClient],
  );

  const login = useCallback(
    (displayName: string, pin: string) =>
      establishSession('/api/v1/auth/login', { display_name: displayName, pin }, 'Login failed'),
    [establishSession],
  );

  const register = useCallback(
    (displayName: string, pin: string) =>
      establishSession(
        '/api/v1/auth/register',
        {
          display_name: displayName,
          pin,
          // Sent so a member's first coupon already reads in local time. The API
          // validates it and falls back to UTC, so a browser that cannot answer
          // (or answers with something unknown) still registers.
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || undefined,
        },
        'Could not create your account',
      ),
    [establishSession],
  );

  const logout = useCallback(async () => {
    const { getRefreshToken } = await import('../lib/tokens');
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).catch(() => {});
    }
    await clearTokens();
    queryClient.clear();
    setLockedPlayer(null);
    setState({
      player: null,
      isLoading: false,
      sessionUnlockRequired: false,
      sessionUnlockError: null,
      sessionResuming: false,
    });
  }, [queryClient]);

  const updatePlayer = useCallback((patch: Partial<StoredPlayer>) => {
    setState((s) => {
      if (!s.player) return s;
      const updated = { ...s.player, ...patch };
      const access = getAccessToken();
      const refresh = getRefreshToken();
      if (access && refresh) storeTokens(access, refresh, updated);
      return { ...s, player: updated };
    });
  }, []);

  const unlockStoredSession = useCallback(async (pin: string) => {
    if (!lockedPlayer) return;

    setState((s) => ({ ...s, isLoading: true, sessionUnlockError: null }));
    try {
      const resp = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: lockedPlayer.displayName, pin }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        // `PIN_NOT_SET` is a code the unlock screen routes on rather than prints: an
        // admin cleared the PIN while this session sat on the device, so there is
        // nothing to unlock and the member is sent to choose a new one.
        if (err.detail === PIN_NOT_SET) throw new Error(PIN_NOT_SET);
        throw new UnlockRefused(resp.status);
      }
      const data = await resp.json();
      const player = playerFromApiResponse(data);
      await clearApiCaches();
      queryClient.clear();
      storeTokens(data.access_token, data.refresh_token, player);
      setState({
        player,
        isLoading: false,
        sessionUnlockRequired: false,
        sessionUnlockError: null,
        sessionResuming: false,
      });
      setLockedPlayer(null);
    } catch (err) {
      setState((s) => ({
        ...s,
        isLoading: false,
        sessionUnlockRequired: true,
        sessionResuming: false,
        // Every failure used to read "Invalid PIN", including a 423 from a lock somebody
        // else is holding open and a 429 from a limit already spent. Telling a member
        // their PIN is wrong when it is not sends them to reset a credential that works.
        sessionUnlockError:
          err instanceof UnlockRefused
            ? err.message
            : err instanceof Error && err.message === PIN_NOT_SET
              ? INVALID_PIN
              : UNREACHABLE,
      }));
      throw err;
    }
  }, [lockedPlayer, queryClient]);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, updatePlayer, unlockStoredSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

/**
 * The auth context if there is one, else null — for consumers whose dependence
 * on it is cosmetic and who have a sensible answer without it.
 *
 * `useAuth` stays strict: anything that actually needs a signed-in member
 * should still fail loudly outside the provider.
 */
export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}
