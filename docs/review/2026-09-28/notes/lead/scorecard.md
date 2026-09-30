# Prior-register scorecard — the lead's working copy

Every id in the 2026-09-13 register, the lens that re-drives it, and the verdict
once the lens reports (held / regressed / partial / not fixed / accepted). The
README's scorecard is built from this table.

| id | 2026-09-13 sev | batch / disposition | lens | verdict | evidence |
| --- | --- | --- | --- | --- | --- |
| SEC-15 | HIGH | 122 | 01 | partial | 01: admin guard holds; demote-then-reset bypass (SEC-27); ordinary members still takeable, reach other leagues (SEC-32) |
| SEC-16 | MED | 124 | 01 | held | 01: removed member's old code 404 after rotation; public_request by code → pending |
| SEC-17 | MED | 125 | 01 | held | 01: non-member site admin pick 403; league-admin writes keep bypass by design |
| SEC-18 | HIGH | 123 | 01 | partial | 01: web half holds in code; per-source backoff charged after the lock (SEC-28) |
| SEC-19 | MED | 141 | 01 | held | 01: prod CSP + XFO DENY; 0 CSP violations on 11 routes |
| SEC-20 | MED | 126 | 01 | partial | 01: override may copy a non-member's global name (SEC-29) |
| SEC-21 | LOW-MED | 142 (hold 48.0.1, document) | 01 | held | 01: live OSV = exactly 3 advisories, documented beside pin |
| SEC-22 | LOW | folded into 127 (OPS-15 left out) | 01 | not fixed | 01: dropped between plan and 127; now 32 advisories (SEC-30) |
| SEC-23 | LOW | 142 | 01 | held | 01: odd ports 422; webpush timeout 5 s |
| SEC-24 | — | withdrawn | — | withdrawn | 2026-09-13 reconciliation |
| SEC-25 | LOW | 143 | 01 | held | 01: Chromium logout → no league key |
| SEC-26 | LOW | 143 | 01 | held | 01: invite to deleted league → 404 |
| CORR-08 | HIGH | 120 | 02 | held | 02: 4×12 concurrent, one 201, eleven 409 with CORS, 0 500s |
| CORR-09 | HIGH | 121 | 02 | held | 02: stray without pick retired; with pick refused at settle (residual CORR-20) |
| CORR-10 | MED | 131 | 02 | held | 02: void-only win rate null; 1 won + 1 void = 100% |
| CORR-11 | MED | 132 | 02 | held | 02: past 422, settled week 409 |
| CORR-12 | MED | 132 | 02 | held | 02: anchor independent of discovery order |
| CORR-13 | MED | 121 | 02 | not fixed | 02: stray and Friday round both labelled '1' |
| CORR-14 | MED | 130 | 02 | partial | 02: leave path fixed; self-deletion path not (CORR-19) |
| CORR-15 | MED | 133 | 02 | partial | 02: budget mechanism works but prices raw pool 36 vs 23 walked (CORR-24) |
| CORR-16 | LOW | accepted, no action | 02 | accepted | 02: still true, still harmless |
| CORR-17 | LOW | 147 | 02 | held | 02: real trigger across both 2026/27 changes, every round reminded once |
| CORR-18 | LOW | 157 | 02 | held | 02: fields gone from API and web |
| void legs | decision | 156 | 02 | partial | 02: coupon right; Results list and home still multiply voids (CORR-21) |
| UX-12 | MED | 137 | 03 | held | 03: 0 landmark/heading violations in 16 runs |
| UX-13 | MED | 138 | 03 | held | 03: 5.08 / 5.60:1 rendered |
| UX-14 | HIGH | 158 | 03 | partial | 03: ring 4.72 / 7.62:1 at 599 of 630 stops; hidden behind tab bar/header (UX-28), not drawn on two controls (UX-29) |
| UX-15 | MED | 167 | 03 | partial | 03: pick labels fixed; other text clips at 320/390 (UX-32) |
| UX-16 | MED | 167 | 03 | held | 03: More sheet returns focus; five other dialogs do not (UX-30) |
| UX-17 | MED | 167 | 03 | held | 03: failures in role=alert, successes in role=status |
| UX-18 | MED | **no batch** (session-log ~6169) | 03 | not fixed | 03: never batched; lost leg 2.39-3.24:1; same defect on profile (UX-21) |
| UX-19 | LOW | 168 | 03 | held | 03: both links 24 px |
| UX-20 | LOW | 168 | 03 | partial | 03: desktop header kept at 200%, but overflows 79 px and hides the account menu (UX-27) |
| PERF-01 | MED | 144 | 04 | held | 04: 15 → 13 statements, projection |
| PERF-02 | MED | owner: one worker | 04 | unchanged (decision) | 04: one worker, scheduler in-process |
| PERF-03 | MED | 145 | 04 | held (local) | 04: 299 KB → 15 KB gzip locally; not checkable read-only in prod |
| PERF-04 | MED | 146 | 04 | held | 04: EXPLAIN at stress uses the new indexes |
| PERF-05 | LOW | 146 | 04 | held | 04: 5+5 pool — but see PERF-20 |
| PERF-06 | HIGH | 159 | 04 | held | 04: refresh walks 23 per window, not 41 |
| PERF-07 | HIGH | 159 | 04 | held | 04: three windows 72/hour, 337/day; cliff moved to four |
| PERF-08 | HIGH | 160 | 04 | held | 04: counter = counting fake in every simulated hour |
| PERF-09 | HIGH | 161 | 04 | held | 04: installation bucket caps at 50/hour (see PERF-23) |
| PERF-10 | MED | 162 | 04 | held | 04: submit answers before fan-out — but see PERF-20 |
| PERF-11 | MED | 163 | 04 | held | 04: SW filters role-gated chunks; 70 entries |
| PERF-12 | MED | 164 | 04 | held | 04: no framer-motion in any chunk; 697 KiB / 238 KiB gzip |
| PERF-13 | MED | 165 | 04 | held | 04: countdown no longer re-renders the screen |
| PERF-14 | MED | 166 (closed by re-measurement) | 04 | held | 04: Lighthouse standings 98, TBT 166 ms (was 77 / 915) |
| PERF-15 | LOW | 165 | 04 | held | 04: both contexts memoised |
| PERF-16 | LOW | 165 | 04 | partial | 04: standings key fixed; 42 inline keys remain |
| PERF-17 | LOW | 164 | 04 | not fixed | 04: /login still loads 3 fonts, 48.8 KiB |
| OPS-11 | HIGH | 127 | 04 | held | 04: Node 24 in CI, gate, .nvmrc, engines |
| OPS-12 | HIGH | 128 | 04 | held | 04: recovery assertion rehearsed locally |
| OPS-13 | HIGH | 95 (built, off) | 04 | not fixed | 04 + 05: built, switched off; no backup for 56 days |
| OPS-14 | MED | 129 | 04 | held | 04: one push then silence; healthy sends none |
| OPS-15 | LOW | left out of 127 | 04 | not fixed | 04: Vite 5→8, ESLint 8→10, Tailwind 3→4, Vitest 2→5 |
| OPS-16 | INFO | 144 / 153 | 04 | held | 04 (with PERF-01); docstring defers to measured count |
| OPS-17 | MED | **no batch** | 04 | not fixed | 04: all 13 jobs misfire_grace_time=1; a job due during a busy loop was dropped |
| OPS-18 | LOW | **no batch** | 04 | not fixed | 04: jobs still share the top of the hour |
| FEAT-A10 | HIGH | 134 | 05 | partial | 05: API holds; unusable from the app and per-pick only (FEAT-A13) |
| FEAT-A11 | MED | 148 | 05 | held | 05: in-app notice shown once, seen recorded, not repeated |
| FEAT-A12 | LOW | carried, no batch | 05 | not fixed | 05: sharper — with sign-ups closed nobody new can get in by any path |
| FEAT-B07 | MED-HIGH | 136 | 05 | held | 05 + 01 + 02: export and deletion through Settings in Chromium; history sums |
| FEAT-B08 | MED | 135 | 05 | held | 05 + 02: both settle paths send once; muted league silent (gap CORR-23) |
| FEAT-B09 | LOW | carried, no batch | 05 | not fixed | 05: /results ignores season across a boundary |
| DES-01 | high | 140 | 06 | partial | 06: two columns at 1280, but the round's left column is empty and home still stretched |
| DES-02 | high | 139 | 06 | partial | 06: first group opens, first price at y=1134 on a 783 screen (DES-13) |
| DES-03 | high | 139 | 06 | partial | 06: right variant and action per refusal; illegible in dark mode (DES-10) |
| DES-04 | med | 149 | 06 | held | 06: toasts 15 px above the tab bar, also with a real 34 px inset |
| DES-05 | med | 149 | 06 | partial | 06: round still shifts on load (CLS 0.247) |
| DES-06 | med | 149 | 06 | partial | 06 + 03: six screens still show errors as empty (UX-25) |
| DES-07 | med | 150 | 06 | held | 06: first-run home reaches the fold with a primary action |
| DES-08 | med | 151 | 06 | partial | 06: home figure white, profiles green; home labels clipped |
| DES-09 | med | 151 | 06 | held | 06: no text under 12 px on core screens (was 84 nodes ≤11 px) |
| PIPE-01 | HIGH | owner, by hand | 07 | not fixed | 07: settings.local.json unchanged since 30 Jul; this session was offered the Supabase write tools |
| PIPE-02 | MED | 153 | 07 | partial | 07: wording fixed; hook silent at the decision moment (PIPE-17) |
| PIPE-03 | MED | 152 | 07 | held | 07: port held → smoke fails in 1 s |
| PIPE-04 | MED | 152 | 07 | partial | 07: counts ratchet; content weakening and branch-local gate edits pass (PIPE-10) |
| PIPE-05 | MED | 152 | 07 | partial | 07: split-half refused; existing drift only reported (PIPE-14) |
| PIPE-06 | MED | 153 | 07 | partial | 07: dated, drifted again (800/550 today) |
| PIPE-07 | MED | 154 | 07 | held | 07: 38.3 KB, but 78% of the head is ticked rows (PIPE-18) |
| PIPE-08 | MED | 155 | 07 | held | 07: zero hits on main by hash |
| PIPE-09 | LOW | folded into 127 | 07 | held | 07: wrong pnpm refused |

## Carried owner actions (not register items in 2026-09-13, tracked since 2026-08-26)

| id | state 29 Sep | evidence |
| --- | --- | --- |
| FEAT-A01 launch gate L5 | not done | `LAUNCH_PLAN.md:30` unticked; `launch-log.md` L0-L4 only |
| FEAT-A02 / OPS-13 backups | built (95), switched off | no backup since launch 4 Aug — 56 days on 29 Sep |
| FEAT-A09 egress consumer | not done | STATUS; runbook step 5 |
| PIPE-01 local agent config | not done | settings.local.json mtime 30 Jul |

## Totals (30 Sep)

81 items (SEC-24 withdrawn in 2026-09-13): **47 held · 21 partial · 11 not fixed · 0 regressed**,
2 unchanged by decision or accepted (PERF-02, CORR-16).
Of the 11 not fixed, 2 were ticked by the batch that claimed them (CORR-13 by 121, PERF-17 by
164); 5 never had a batch (UX-18, OPS-17, OPS-18 omitted; SEC-22 and OPS-15 dropped between the
plan and Batch 127); 2 were held back deliberately (FEAT-A12, FEAT-B09); 2 are owner actions
(OPS-13, PIPE-01). New defects introduced by these batches: DES-10 (149), UX-26 (164), UX-27
(168), PERF-20 (162 with 146).
