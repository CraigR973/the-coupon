-- Undo migration 032 BEFORE ACTIVATION ONLY — the lossless way back to 031.
--
-- Use it only while the two-game format has never been switched on: every table 032
-- created must still be empty and every week must be legacy. It refuses otherwise, and
-- after it refuses the only recovery is forward (migration-032-recovery.md). It keeps
-- every legacy row written since 032 landed: it drops only what 032 added — the nine
-- fence triggers, the eight guard functions, the fifteen two-game tables and the
-- gameweeks format column with its check and (id, league_id) key — then records 031.
--
-- Run it with the API and payments stopped, as one transaction, never with CASCADE:
--   psql -X -v ON_ERROR_STOP=1 -f migration-032-undo.sql "<connection>"
-- Then roll both services back to their 031 deployments (backup-restore.md).
-- Owner approval for this path: 19 Nov 2026, relayed verbatim ("yes proceed").

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
    revision text;
    tbl text;
    found bigint;
BEGIN
    SELECT string_agg(version_num, ',') INTO revision FROM public.alembic_version;
    IF revision IS DISTINCT FROM '032' THEN
        RAISE EXCEPTION 'undo-032 refused: the database is at revision %, not 032', revision;
    END IF;
    FOREACH tbl IN ARRAY ARRAY[
        'two_game_rollouts', 'two_games', 'two_game_fixtures', 'group_picks',
        'fantasy_picks', 'membership_intervals', 'weekly_fee_obligations',
        'provider_attempts', 'provider_controls', 'provider_snapshots', 'provider_work',
        'provider_refusals', 'two_game_operations', 'two_game_events', 'two_game_breaks'
    ] LOOP
        EXECUTE format('SELECT count(*) FROM public.%I', tbl) INTO found;
        IF found <> 0 THEN
            RAISE EXCEPTION 'undo-032 refused: public.% holds % row(s); recovery is forward-only',
                tbl, found;
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM public.gameweeks WHERE format <> 'legacy') THEN
        RAISE EXCEPTION 'undo-032 refused: a non-legacy week exists';
    END IF;
END $$;

DROP TRIGGER gameweeks_two_game_fence ON public.gameweeks;
DROP TRIGGER picks_two_game_fence ON public.picks;
DROP TRIGGER gameweek_fixtures_two_game_fence ON public.gameweek_fixtures;
DROP TRIGGER ledger_entries_two_game_fence ON public.ledger_entries;

DROP TABLE
    public.group_picks, public.fantasy_picks, public.weekly_fee_obligations,
    public.two_game_operations, public.two_game_events, public.two_game_fixtures,
    public.two_games, public.membership_intervals, public.two_game_rollouts,
    public.two_game_breaks, public.provider_work, public.provider_snapshots,
    public.provider_refusals, public.provider_controls, public.provider_attempts;

DROP FUNCTION
    public.two_game_guard_parent(), public.two_game_guard_legacy(),
    public.two_game_guard_child(), public.two_game_guard_fixture(),
    public.two_game_guard_fee(), public.two_game_guard_interval(),
    public.two_game_guard_ledger(), public.two_game_guard_attempt();

ALTER TABLE public.gameweeks DROP CONSTRAINT uq_gameweeks_id_league;
ALTER TABLE public.gameweeks DROP CONSTRAINT ck_gameweeks_format;
ALTER TABLE public.gameweeks DROP COLUMN format;

UPDATE public.alembic_version SET version_num = '031' WHERE version_num = '032';

COMMIT;
