# ADR 0006 — Store avatars in a public Supabase bucket under an unguessable key

Status: **accepted, 2026-08-20.** Scoped as Batch 44, which enabled the profile
pictures Batch 42 modelled and deliberately left switched off.

## Context

Batch 42 shipped the whole shape of avatars — the column, the port, three
endpoints, the upload control — with exactly one implementation of
`AvatarStorage`, and it refuses. It recorded three things that had to be true
before a real backend could be wired: bytes must be re-encoded rather than
passed through, the bucket's access rules must be written explicitly, and
removal must exist on both sides. The third shipped with Batch 42. This ADR
records the second; the first is a code decision, not an architectural one, and
lives in `apps/api/src/services/avatar_storage.py`.

`docs/LAUNCH_PLAN.md` carries a standing scope decision — "Use Supabase as
managed PostgreSQL only" — taken when the inherited avatar upload UI was removed
because nothing implemented it. Batch 44 revisits that narrowly: Storage, in one
bucket, for one feature. Nothing else moves to Supabase, and the Data API stays
denied.

## Decision

**A single public-read bucket, with the object key carrying a random token.**

The key is `{player_id}/{22 random url-safe characters}.webp`. Reading needs no
credential; *finding* the URL needs the URL. Player ids appear on every league
page, so a key derived from the player id alone would make every member's
picture enumerable by anyone who can see a leaderboard — the random half is what
stops that.

Replacing a picture writes a new random key and deletes the objects that were
there before, so a URL that leaked stops resolving as soon as the member changes
their picture. That is also why the objects can be served
`Cache-Control: immutable` for a year: a new picture is a new URL, so nothing
ever needs invalidating.

## Alternatives

**A private bucket with signed URLs** was the other candidate, and it is the
stronger posture: nothing is readable without a link this API minted. It was
rejected on cost, not on principle. `profiles.avatar_url` would stop being a URL
and become a stored path, and every surface that shows a member — `/auth/me`,
the league members list, the pick roster, the combined coupon — would have to
mint a signed URL per picture on every read, which is a Supabase round trip per
member per page against a product whose whole read path is otherwise one
database query. The expiry would also have to be chosen and then handled on the
client when it lapsed mid-session.

**Storing the image in Postgres** as a `bytea` column keeps the single-store
posture and needs no new surface at all. Rejected: the API would then serve
every avatar byte through its own process, on a Railway replica sized for JSON,
and Supabase's own guidance is against blobs in the database.

**A third-party image CDN** was not considered seriously — it is another vendor,
another key, and another privacy boundary for a fifteen-player private game.

## Consequences

- A member's picture is world-readable to anyone holding its URL. This is
  recorded here rather than implied: it is the price of the column staying a
  plain URL, and the owner accepted it on 2026-08-20.
- The bucket is provisioned by hand from `docs/runbooks/avatar-storage.md`, not
  by a migration. Buckets and their policies live in Supabase's `storage`
  schema, which does not exist in the throwaway `pgserver` instance CI and the
  local gate run against, so a migration touching it would fail every run.
- The service-role key bypasses RLS by design. It is held only by the API, never
  reaches a browser, travels as a header rather than a query parameter (the
  shape that leaked the odds key in Batch 36), and is registered in
  `settings.secret_values()` so the log renderer redacts it.
- `AVATAR_STORAGE` defaults to `none`. A deployment that has not provisioned a
  bucket behaves exactly as it did before this batch, and `GET /api/v1/config`
  tells the web app to keep the upload control unmounted.
