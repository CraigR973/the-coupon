# Runbook — provisioning avatar storage

Profile pictures are built and tested but **off in every environment** until the
steps below are run there. Until then `POST /api/v1/auth/me/avatar` answers 503,
`GET /api/v1/config` reports `avatar_uploads: false`, and the web app leaves its
upload control unmounted. Nothing here is reversible-by-accident: the feature
returns to that state the moment `AVATAR_STORAGE` goes back to `none`.

Read ADR 0006 first — it records *why* the bucket is public-read with an
unguessable key, and what was rejected.

These steps are the owner's: they need the Supabase dashboard and they seal a
secret. This is not a migration, and deliberately so — buckets live in
Supabase's `storage` schema, which does not exist in the throwaway `pgserver`
instance CI runs against, so a migration touching it would fail every run.

## 1. Create the bucket

Supabase dashboard → **Storage** → **New bucket**:

| Field                  | Value                      |
| ---------------------- | -------------------------- |
| Name                   | `avatars`                  |
| Public bucket          | **on**                     |
| Restrict file size     | `2 MB`                     |
| Allowed MIME types     | `image/webp`               |

The size and MIME restrictions are belt and braces — the API caps the body as it
arrives and only ever writes a WebP it encoded itself — but they mean a leaked
service key cannot turn the bucket into general-purpose file hosting.

## 2. Write the policies explicitly

Run this in the SQL editor. It is idempotent; re-running it is safe.

```sql
-- Anyone may read an object, because the bucket is public and the key is the
-- secret (ADR 0006). Nobody may write with an anon or authenticated token:
-- every write goes through the API with the service-role key, which bypasses
-- RLS and is therefore not covered by these policies.
drop policy if exists "avatars are readable" on storage.objects;
create policy "avatars are readable"
  on storage.objects for select
  using (bucket_id = 'avatars');

-- No insert/update/delete policy exists on purpose. Without one, RLS denies
-- those verbs to every role that is subject to it.
```

Confirm the negative half rather than assuming it:

```sql
select polname, polcmd
from pg_policy
where polrelid = 'storage.objects'::regclass;
```

Expect exactly one `avatars` row, with `polcmd = 'r'` (SELECT). If an
`INSERT`/`UPDATE`/`DELETE` policy naming `avatars` appears, remove it — a
browser holding an `authenticated` token would otherwise be able to write into
the bucket directly, bypassing every check in `upload_avatar`.

## 3. Seal the configuration

On Railway, for the target environment:

```bash
railway variables --set AVATAR_STORAGE=supabase --set SUPABASE_URL=https://<ref>.supabase.co --set SUPABASE_SERVICE_KEY=<service-role key>
```

- `SUPABASE_URL` is the project REST base, no trailing slash and no `/storage`.
- `SUPABASE_SERVICE_KEY` is the **service role** key, not the anon key. It
  bypasses RLS, which is why step 2 exists at all.
- `AVATAR_BUCKET` defaults to `avatars`; set it only if step 1 used another name.

Setting a variable triggers a Railway redeploy. Record it in
`docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md` as the new rollback baseline — a
config-only redeploy is still the deployment a rollback would land on.

## 4. Verify

```bash
curl -s -H "Authorization: Bearer <access token>" https://<api-host>/api/v1/config
```

Expect `{"avatar_uploads":true}`. Then, as a real member: Settings now shows a
**Profile picture** card. Upload one and check three things.

1. The returned `avatar_url` contains a random segment, not just the player id.
2. Fetching that URL anonymously returns the image with
   `content-type: image/webp` — whatever format was uploaded.
3. Uploading a second picture makes the first URL 404.

If uploads answer 502, the bucket exists but refused the write — check the size
and MIME restrictions from step 1 against `image/webp`. If they answer 503 after
step 3, `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` is empty; the API falls back to
the refusing backend rather than 500ing, and logs
`AVATAR_STORAGE=supabase but SUPABASE_URL/SUPABASE_SERVICE_KEY is unset`.

## Turning it back off

```bash
railway variables --set AVATAR_STORAGE=none
```

Uploads answer 503 again and the card disappears from Settings. Pictures already
stored stay in the bucket and stay readable — the column still holds their URLs.
To take them down as well, clear the column and empty the bucket:

```sql
update profiles set avatar_url = null where avatar_url is not null;
```

```sql
delete from storage.objects where bucket_id = 'avatars';
```
