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

/**
 * An answer from the API that was not a success — the request reached the server and
 * came back refused.
 *
 * `message` is still the `detail` string, so every caller that reads `err.message`
 * predates this class and keeps working. What it adds is `status`, which is the only
 * thing that separates "the server refused you" from "we never heard back" — and on the
 * pick path those two are different enough that Batch 90 exists to tell them apart.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/**
 * The request did not produce an answer at all — offline, DNS, a dropped connection, or
 * a timeout we imposed ourselves.
 *
 * `mayHaveLanded` is the field that matters and the reason this class exists. A write
 * that never left the device can be retried freely; a write that left and went unanswered
 * **cannot**, because the server may have applied it. On the pick path a blind retry of
 * the second kind can overwrite a claim the member has since changed their mind about, so
 * this flag is what lets `usePickEditor` queue one and merely *check* the other.
 *
 * It is set from what we can actually know: a `fetch` we refused to start because the
 * browser reported itself offline definitely never landed. Anything else — including a
 * connection that dropped a millisecond later — might have.
 */
export class NetworkError extends Error {
  readonly mayHaveLanded: boolean;

  constructor(message: string, mayHaveLanded: boolean, options?: { cause?: unknown }) {
    super(message, options);
    this.name = 'NetworkError';
    this.mayHaveLanded = mayHaveLanded;
  }
}

/** Extra, non-`RequestInit` options `apiFetch` understands. */
export interface ApiFetchOptions extends RequestInit {
  /**
   * Abort the request after this many milliseconds and raise a `NetworkError` whose
   * `mayHaveLanded` is `true`.
   *
   * Opt-in, and deliberately not a default: a read that hangs is a spinner, while a
   * *write* that hangs leaves the member staring at a claim they cannot tell the state
   * of. Only the pick submission sets it today.
   */
  timeoutMs?: number;
}

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
  options: ApiFetchOptions = {},
): Promise<T> {
  await ensureFreshToken();

  const accessToken = getAccessToken();
  const { timeoutMs, ...init } = options;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

  const resp = await sendRequest(`${API_BASE}${path}`, { ...init, headers }, timeoutMs);

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
      const retry = await fetch(`${API_BASE}${path}`, { ...init, headers });
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
    const fallback = `API error ${resp.status}`;
    let detail: string | undefined;
    try {
      const body = await resp.json();
      detail = typeof body?.detail === 'string' ? body.detail : undefined;
    } catch {
      detail = undefined;
    }
    throw new ApiError(resp.status, detail ?? fallback);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

/**
 * One `fetch`, with the two failure modes separated before they reach a caller.
 *
 * The browser gives every transport failure the same shape — a `TypeError` — whether the
 * request never left or left and went unanswered, and that distinction is exactly what a
 * write has to have. Two things narrow it: refusing to start while `navigator.onLine` is
 * false (which means it definitely did not land), and imposing our own deadline (which
 * means it did leave, so it might have).
 *
 * `navigator.onLine` is only ever trusted in the *negative*. `true` means "there is a
 * network interface", not "the server is reachable" — a captive portal or a pub's dead
 * wifi reports online — so it is used to prove a request never left and never to promise
 * one will arrive.
 */
async function sendRequest(
  url: string,
  init: RequestInit,
  timeoutMs?: number,
): Promise<Response> {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    throw new NetworkError('You are offline', false);
  }

  if (timeoutMs === undefined) {
    try {
      return await fetch(url, init);
    } catch (cause) {
      throw new NetworkError('The network request failed', true, { cause });
    }
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (cause) {
    throw new NetworkError('The network request failed', true, { cause });
  } finally {
    clearTimeout(timer);
  }
}
