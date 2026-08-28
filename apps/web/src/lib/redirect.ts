/**
 * Where a signed-out member should land after signing in or registering.
 *
 * `?next=` is attacker-suppliable — both `/login` and `/register` are public, and a
 * crafted link's visible host is the real app, which is what makes it worth phishing
 * with. The guard this replaces tested `startsWith('/') && !startsWith('//')`, which
 * stops the protocol-relative `//evil.com` but not the backslash form `/\evil.com`:
 * that starts with a single `/`, so it passed, and browsers resolve `\` as `/` inside
 * a special scheme (WHATWG URL, "special authority slashes state"), landing the member
 * on `https://evil.com/`. That is GHSA-wrjc-x8rr-h8h6, and react-router has no fix on
 * the 6.x line — only 7.18.0+, a major migration out of proportion to this gap.
 *
 * So the check does not try to enumerate the hostile forms. It hands the string to the
 * same URL parser the browser will use and keeps the result only if it stayed on this
 * origin — which is decided by the parser rather than by a pattern this file has to
 * predict. What is returned is the *parsed* path rather than the caller's string, so
 * whatever react-router later does with it cannot diverge from what was validated.
 */
export function resolveNextDestination(search: string, origin: string): string {
  const requested = new URLSearchParams(search).get('next');

  // A bare `evil.com` resolves to the same-origin path `/evil.com` and would pass the
  // origin check below, so the leading slash is still required: every `?next=` this app
  // issues is an absolute path (`/join/:token`), and nothing should arrive relative.
  if (!requested || !requested.startsWith('/')) return '/';

  let resolved: URL;
  try {
    resolved = new URL(requested, origin);
  } catch {
    return '/';
  }

  if (resolved.origin !== origin) return '/';
  return `${resolved.pathname}${resolved.search}${resolved.hash}`;
}
