import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  isAccessTokenExpiringSoon,
  storeTokens,
  getStoredPlayer,
} from './tokens';

if (import.meta.env.PROD && !import.meta.env.VITE_API_URL) {
  throw new Error('VITE_API_URL is required in production builds');
}
export const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/**
 * The slug the browser e2e seed and the first production seed use.
 *
 * Only a last-resort default now — for a `:slug` route param that is somehow
 * absent, and for `activeSlug` before the member's leagues have loaded. Batch 8
 * took it out of the pages and Batch 30 put the league in the URL, so nothing
 * reads it as "the league" any more.
 */
export const DEFAULT_LEAGUE_SLUG = 'the-coupon';

/**
 * The `detail` a login (or a session unlock) carries when the account has no credential
 * to check — an admin cleared it and the member has not chosen a new one yet (Batch 66).
 *
 * A code rather than a sentence because two screens route on it: `/login` and the stored
 * session's PIN gate both send the member to `/set-pin` instead of telling them their
 * PIN is wrong, which would send them round the forgot-PIN loop that got them here.
 */
export const PIN_NOT_SET = 'PIN_NOT_SET';

let refreshPromise: Promise<void> | null = null;

async function silentRefresh(): Promise<void> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    await clearTokens();
    throw new Error('No refresh token');
  }
  const resp = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!resp.ok) {
    clearTokens();
    throw new Error('Refresh failed');
  }
  const data = await resp.json();
  const player = getStoredPlayer()!;
  storeTokens(data.access_token, data.refresh_token, player);
}

async function ensureFreshToken(): Promise<void> {
  if (!isAccessTokenExpiringSoon()) return;
  if (!refreshPromise) {
    refreshPromise = silentRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  await refreshPromise;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  await ensureFreshToken();

  const accessToken = getAccessToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });

  // 401 only, deliberately — do not add 403 here (Batch 61).
  //
  // The API moved to fastapi 0.141, where `HTTPBearer` answers a *missing* credential
  // with 401 instead of the 403 that fastapi 0.111 sent. That is the correct code:
  // RFC 7235 reserves 403 for a caller who is authenticated and still forbidden. So
  // this branch now also catches the anonymous case, which previously fell through to
  // the generic error below — a silent refresh followed by `/login` is a better answer
  // for a member whose access token has gone missing than an error toast.
  //
  // Widening this to `|| resp.status === 403` would be a regression, not a belt-and-
  // braces: a genuine 403 is a signed-in member hitting something they may not have,
  // and refreshing then redirecting would sign them out for asking.
  //
  // The redirect is safe because every bearer-protected call sits under
  // `<ProtectedRoute />`; the six public routes reach no such endpoint. And nothing
  // needed to change for the deploy gap — Vercel ships this app on merge while the API
  // waits for `/ship-prod`, so for a while the old 403 arrives and takes exactly the
  // path it takes today.
  if (resp.status === 401) {
    // Access token was rejected — attempt one refresh then retry
    try {
      await silentRefresh();
      const retryToken = getAccessToken();
      if (retryToken) headers['Authorization'] = `Bearer ${retryToken}`;
      const retry = await fetch(`${API_BASE}${path}`, { ...options, headers });
      if (!retry.ok) throw new Error(`${retry.status}`);
      return retry.json() as Promise<T>;
    } catch {
      await clearTokens();
      window.location.href = '/login';
      throw new Error('Session expired');
    }
  }

  if (!resp.ok) {
    // Try to surface the FastAPI `detail` field for a more useful error message.
    try {
      const body = await resp.json();
      const detail = typeof body?.detail === 'string' ? body.detail : undefined;
      throw new Error(detail ?? `API error ${resp.status}`);
    } catch (e) {
      if (e instanceof Error && e.message !== `API error ${resp.status}`) throw e;
      throw new Error(`API error ${resp.status}`);
    }
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}
