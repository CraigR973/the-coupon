# Backfill note — deployment season calendar

Batch 113 makes the public Gameweek label deployment-wide while preserving
`gameweeks.number` as each league's internal, never-reused ordinal. The run is:

```bash
python -m src.backfill_season_calendar --dry-run
```

The first command is read-only. It derives each season's week-1 anchor from the earliest
stored round, prints every visible move as `league · date: was Gameweek N -> now Gameweek
M`, and reports how many labels stay unchanged. It includes rounds with picks and settled
history: those moves are permitted, but they are never silent.

For the 2026/27 production data described in the batch, the anchor is Saturday 8 August
2026. 2-1 Hibs remains 1–5. McCann's Defenders' two stored rounds move to the corresponding
deployment weeks, including 5 September moving from Gameweek 3 to Gameweek 5.

Applying is a separate owner action and is deliberately not part of this batch's ship:

```bash
python -m src.backfill_season_calendar --apply
```

`--apply` stores one `season_calendars` row per represented season. It does not update
`gameweeks.number`, picks, outcomes, points, or standings. Run `--dry-run` again afterwards;
because the stored anchor is now the source of the public labels, it must report no moves.

Do not edit the inferred anchor between the dry run and apply. Once any round in the
season has settled, the admin API refuses an anchor move. Production application and its
independent read-back should be appended to this note when the owner authorises the run.
