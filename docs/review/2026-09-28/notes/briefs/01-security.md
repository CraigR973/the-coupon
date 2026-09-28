# Lens 01 — Security

Output: `docs/review/2026-09-28/01-security.md`. Notes: `docs/review/2026-09-28/notes/01-security/`.
Ports: API **8110**, web **4310** (only if you need the bundle). New finding ids start at **SEC-27**.

## Your slice of the 2026-09-13 register (re-drive each against a running stack)

| id | sev then | batch | what "fixed" should look like |
| --- | --- | --- | --- |
| SEC-15 | HIGH | 122 | a league admin cannot reset a site admin's PIN, nor any league's admin's; ordinary member reset still works |
| SEC-18 | HIGH | 123 | a valid refresh token admits a member during a griefing lock (web half); per-source backoff + a lockout push (API half); brute force unchanged; correct PIN still refused during a lock |
| SEC-16 | MED | 124 | a removed member's old join code is refused; join-by-code on a `public_request` league creates a request, not a membership |
| SEC-17 | MED | 125 | a non-member site admin is refused on every **write** route into a league (pick submit at minimum — enumerate the rest); reads still allowed |
| SEC-19 | MED | 141 | CSP + frame-ancestors on production web (read-only), no CSP violations with the bundle loaded |
| SEC-20 | MED | 126 | a per-league name colliding with another member's effective name is refused; confusables/charset rules match registration |
| SEC-21 | LOW-MED | 142 (owner: hold 48.0.1) | the three advisories documented as unreachable where the pin lives, with CVE/GHSA ids |
| SEC-22 | LOW | folded into 127 per the old plan, but 127's row says OPS-15 was left out — check what actually happened | build-toolchain advisories |
| SEC-23 | LOW | 142 | `webpush()` has a timeout; odd ports refused on allowlisted hosts |
| SEC-25 | LOW | 143 | no league key survives logout / identity switch |
| SEC-26 | LOW | 143 | claiming an invite to a soft-deleted league is refused |
| SEC-01..SEC-13 | — | earlier | spot-check they still hold (the 2026-09-13 01-security.md table shows how each was checked) |

SEC-14 (registration 409 enumeration oracle) is an accepted owner decision.

## What to do

1. **Rebuild the route-by-route authorisation matrix** from the routers under
   `apps/api/src/routers/` — every route, anonymous / member / league admin /
   site admin (plus a second league's member and admin for cross-league), and
   **probe it against the running stack**, not just from the code. Mark every
   route added since `2ce6f42` (`git -C ... diff 2ce6f42 main -- apps/api/src/routers`).
   Save the matrix as a table/CSV in your notes.
2. **Cross-league IDOR**: substitute another league's round, pick, member,
   invite, join-request, audit and notification ids through this league's slug
   and through id-only routes. Note the prior near-miss: a round id from
   another league returned `200 null` rather than 404 — does it still?
3. **Re-drive SEC-15..SEC-26** as above.
4. **New surfaces since 2ce6f42** — attack each as an adversarial member:
   - account deletion and data export (Batch 136): can anyone delete or export
     someone else? Does export leak other members' data? Is the PIN re-entry
     enforced server-side? Refused while sole admin of a league someone else
     plays in? After deletion: are sessions/refresh tokens revoked, push
     subscriptions removed, the name freed and re-registrable — and can the
     re-registrant see or inherit anything of the deleted member's?
   - admin pick correction (134): site-admin only? audited? can a league admin
     or member reach it? input validation (points, odds, status)?
   - settle and rename notifications (135, 148): can a member trigger, read or
     mark someone else's notice? any IDOR on the rename-notice routes?
   - extra-week endpoints (132): authz and the new past/settled guards.
   - lockout notification and per-source backoff (123): can the push be used to
     harass (spam a member with lockout pushes)? Is the per-source key
     spoofable via `X-Forwarded-For` given `trusted_proxy_count`?
   - alarm push to site admins (129): who receives it?
   - CSP and framing headers (141), production **read-only**: record the exact
     headers; judge the policy (script-src hash, `style-src 'unsafe-inline'`,
     `connect-src` — the lead noticed production's policy also allows the
     *staging* API origin `api-production-0641`, and the HTML is served with
     `access-control-allow-origin: *` — assess whether either matters).
   - response compression (145): any BREACH-style concern on responses that mix
     a secret with attacker-reflected input? (Probably not — show why.)
5. **Live OSV query** over `apps/api/requirements.txt` (the full lock) and
   `pnpm-lock.yaml` — use `https://api.osv.dev/v1/querybatch` (public, no key).
   Record counts, every hit, reachability for each runtime one.
6. **Secrets**: tracked tree and full git history (patterns for JWT secrets,
   API keys, DSNs, VAPID private keys, Supabase service keys, R2/S3 keys given
   Batch 95's `BACKUP_*` variables). Also check Batch 155's redaction: the
   eleven non-owner member names must be absent from the working tree (they are
   still in history by owner decision — do not rewrite). Do not print any secret
   you find; record location and type only.
7. The production API's headers and `/api/v1/health` (read-only), compared with
   2026-09-13's record.

## Do not

Sign in to production, call any provider, or run anything that writes to
production. Do not read `.env*` files' values into your notes — record only
whether a key is present.
