# Screenshot index — 2026-09-28 review

Each pass appends its own rows.

| file | pass | state shown | how it was driven |
| --- | --- | --- | --- |
| home--last-result-void-unstyled--1280--light.png | 02 correctness | **Unstyled** (built by the lead's first `web.sh`, which ran Vite outside `apps/web`, so Tailwind emitted a 9 KB stylesheet; text content is valid evidence, the layout is not). Alice's home: L1 "Last result · Gameweek 1 … 4-fold · 54.91" for a round with two void legs (CORR-21) | web_check.mjs, prod bundle on 4320 vs API 8120, scratch data after lifecycle.py |
| results--void-leg-price-unstyled--1280--light.png | 02 correctness | **Unstyled**, as above. L1 Results list: Gameweek 1 at 54.91, void legs multiplied (CORR-21) | same run |
| coupon--settled-void-legs-unstyled--1280--light.png | 02 correctness | **Unstyled**, as above. The same round's settled coupon: 7.44, "2 legs voided — not in the combined price", header "4 of 3" after a leave and an erasure (CORR-21, CORR-26) | same run, reached by tapping the Results row |
| settings--your-data-unstyled--1280--light.png | 05 features | Settings scrolled to "Your data" (Bob): Download my data + Delete my account (FEAT-B07). **Unstyled** — the stylesheet did not apply under the route-fulfilment harness; functional evidence only, not for the design corpus | notes/05-features/browser.mjs PHASES=bob, prod bundle fulfilled on the API origin 8150 |
| settings--delete-confirm-unstyled--1280--light.png | 05 features | Delete confirm panel with PIN entered, not submitted (Bob). Unstyled, as above | same, PHASES=bob |
| login--after-account-deleted-unstyled--1280--light.png | 05 features | /login after Carol deleted her own account through Settings; toast "Your account has been deleted." bottom right. Unstyled, as above | browser.mjs PHASES=b07 |
| home--rename-notice-unstyled--1280--light.png | 05 features | In-app rename notice dialog for an untold renamed profile id (FEAT-A11). Unstyled, as above | browser.mjs PHASES=a11 |
| register--signups-closed-before-submit-unstyled--1280--light.png | 05 features | /register with PUBLIC_SIGNUP_ENABLED=false: the full form, no notice (FEAT-A12). Unstyled, as above | browser.mjs PHASES=a12, stack env PUBLIC_SIGNUP_ENABLED=false |
| register--signups-closed-after-submit-unstyled--1280--light.png | 05 features | The same form after filling name + PIN twice: only now "Sign-ups are closed right now. Ask a league admin for an invite." Unstyled, as above | same |
