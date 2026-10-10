# Forward recovery plan — migration 027 (member notification history)

Batch 194 prepares this plan before its separate `/ship-prod`. That command requires
fresh production checks and the owner's explicit shipment instruction. Production
has no backup or restore point while Batch 95 remains switched off.

## Statements and locks

Revision `027` adds three `boolean NOT NULL DEFAULT false` mute columns to
`notification_preferences`, creates an empty `member_notifications` table with
foreign keys to profiles and leagues, and creates indexes for member history and
30-day pruning. It enables and forces RLS on the new table and revokes Supabase
Data API roles. The column additions take a brief `ACCESS EXCLUSIVE` lock on
`notification_preferences`; PostgreSQL stores constant defaults in metadata,
so existing rows are not rewritten. The new table and indexes contain no rows
when created. No old column, constraint, table or index is dropped or renamed.

## Compatibility and recovery

The image serving revision `026` does not read the new table or columns, so its
application queries can run against the expanded schema. A normal Railway
rollback still **cannot start** after `027` lands: its boot-time Alembic command
does not know revision `027` and stops before the API binds. The first response
to a faulty Batch 194 deployment is therefore to correct the image and ship
forward. Keep the new table and its rows; this preserves messages already
written while the fault is repaired.

If the fault is solely in the Batch 194 application and an immediate old-image
rollback is necessary, review the live schema and migration state first. With a
fresh, explicit owner decision, the version row may be set back to `026` while
leaving the additive schema in place, then the `026` image can be redeployed.
That bookkeeping edit is **not** authorised by this note or by `/ship-prod`.
Before a later retry of `027`, account for the already-created objects; simply
running the same `upgrade()` against them would fail. Prefer a reviewed forward
repair over this route.

## Downgrade cost

`downgrade()` drops the notification table and all rows in it, then the three
mute columns. It is lossless only before the first notification or mute change.
After use it permanently erases member history, read state and category choices.
Do not run a downgrade as an automatic rollback.

The 30-day pruner deletes expired rows by `created_at`; this is an intentional
retention rule and does not make the migration downgrade safe.
