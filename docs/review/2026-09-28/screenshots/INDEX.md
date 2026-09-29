# Screenshot index — 2026-09-28 review

Each pass appends its own rows.

| file | pass | state shown | how it was driven |
| --- | --- | --- | --- |
| home--last-result-void--1280--light.png | 02 correctness | Alice's home: L1 "Last result · Gameweek 1 … 4-fold · 54.91" for a round with two void legs (CORR-21) | web_check.mjs, prod bundle on 4320 vs API 8120, scratch data after lifecycle.py |
| results--void-leg-price--1280--light.png | 02 correctness | L1 Results list: Gameweek 1 at 54.91, void legs multiplied (CORR-21) | same run |
| coupon--settled-void-legs--1280--light.png | 02 correctness | The same round's settled coupon: 7.44, "2 legs voided — not in the combined price", header "4 of 3" after a leave and an erasure (CORR-21, CORR-26) | same run, reached by tapping the Results row |
