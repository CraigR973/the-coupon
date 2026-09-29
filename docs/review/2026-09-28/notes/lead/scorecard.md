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
| UX-12 | MED | 137 | 03 | | |
| UX-13 | MED | 138 | 03 | | |
| UX-14 | HIGH | 158 | 03 | | |
| UX-15 | MED | 167 | 03 | | |
| UX-16 | MED | 167 | 03 | | |
| UX-17 | MED | 167 | 03 | | |
| UX-18 | MED | **no batch** (session-log ~6169) | 03 | | |
| UX-19 | LOW | 168 | 03 | | |
| UX-20 | LOW | 168 | 03 | | |
| PERF-01 | MED | 144 | 04 | | |
| PERF-02 | MED | owner: one worker | 04 | | |
| PERF-03 | MED | 145 | 04 | | |
| PERF-04 | MED | 146 | 04 | | |
| PERF-05 | LOW | 146 | 04 | | |
| PERF-06 | HIGH | 159 | 04 | | |
| PERF-07 | HIGH | 159 | 04 | | |
| PERF-08 | HIGH | 160 | 04 | | |
| PERF-09 | HIGH | 161 | 04 | | |
| PERF-10 | MED | 162 | 04 | | |
| PERF-11 | MED | 163 | 04 | | |
| PERF-12 | MED | 164 | 04 | | |
| PERF-13 | MED | 165 | 04 | | |
| PERF-14 | MED | 166 (closed by re-measurement) | 04 | | |
| PERF-15 | LOW | 165 | 04 | | |
| PERF-16 | LOW | 165 | 04 | | |
| PERF-17 | LOW | 164 | 04 | | |
| OPS-11 | HIGH | 127 | 04 | | |
| OPS-12 | HIGH | 128 | 04 | | |
| OPS-13 | HIGH | 95 (built, off) | 04 | | |
| OPS-14 | MED | 129 | 04 | | |
| OPS-15 | LOW | left out of 127 | 04 | | |
| OPS-16 | INFO | 144 / 153 | 04 | | |
| OPS-17 | MED | **no batch** | 04 | | |
| OPS-18 | LOW | **no batch** | 04 | | |
| FEAT-A10 | HIGH | 134 | 05 | | |
| FEAT-A11 | MED | 148 | 05 | | |
| FEAT-A12 | LOW | carried, no batch | 05 | | |
| FEAT-B07 | MED-HIGH | 136 | 05 | | |
| FEAT-B08 | MED | 135 | 05 | | |
| FEAT-B09 | LOW | carried, no batch | 05 | | |
| DES-01 | high | 140 | 06 | | |
| DES-02 | high | 139 | 06 | | |
| DES-03 | high | 139 | 06 | | |
| DES-04 | med | 149 | 06 | | |
| DES-05 | med | 149 | 06 | | |
| DES-06 | med | 149 | 06 | | |
| DES-07 | med | 150 | 06 | | |
| DES-08 | med | 151 | 06 | | |
| DES-09 | med | 151 | 06 | | |
| PIPE-01 | HIGH | owner, by hand | 07 | not fixed | 07: settings.local.json unchanged since 30 Jul; this session was offered the Supabase write tools |
| PIPE-02 | MED | 153 | 07 | partial | 07: wording fixed; hook silent at the decision moment (PIPE-17) |
| PIPE-03 | MED | 152 | 07 | held | 07: port held → smoke fails in 1 s |
| PIPE-04 | MED | 152 | 07 | partial | 07: counts ratchet; content weakening and branch-local gate edits pass (PIPE-10) |
| PIPE-05 | MED | 152 | 07 | partial | 07: split-half refused; existing drift only reported (PIPE-14) |
| PIPE-06 | MED | 153 | 07 | partial | 07: dated, drifted again (800/550 today) |
| PIPE-07 | MED | 154 | 07 | held | 07: 38.3 KB, but 78% of the head is ticked rows (PIPE-18) |
| PIPE-08 | MED | 155 | 07 | held | 07: zero hits on main by hash |
| PIPE-09 | LOW | folded into 127 | 07 | held | 07: wrong pnpm refused |
