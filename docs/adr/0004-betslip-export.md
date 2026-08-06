# ADR 0004 — Betslip export: do not build it

Status: **accepted, 2026-08-06 — the decision is not to build this.** Scoped as
Batch 17, which was a timeboxed spike required to end in an ADR rather than a
feature. It ships no code.

## Context

The ask is to push a completed coupon to a bookmaker account, Bet365 first, so a
member can take the leaderboard's combined accumulator to a real book in one
action instead of typing eleven legs in by hand. The batch row predicted the
likely finding: no betslip API, and a shareable betslip link for the books that
support one.

The first half of that prediction is right. The second half is not — the
shareable link exists, but it carries **one** selection, and a coupon is never
one selection. That is the finding, and it is what closes the batch.

## What we hold, and what we deliberately threw away

The obstacle is not effort. It is that this application holds no identifier any
bookmaker would recognise, and that was a decision, not an oversight.

A pick is identified by `(fixture, market, outcome)` — the same triple as the
uniqueness rule the leaderboard already enforces. `services/odds_provider.py`
states the reason in its own docstring: no provider identifier needs to survive
into settlement. Revision `005` acted on it and dropped the Betfair market and
selection ids `picks` used to carry. That is what let the Exchange be swapped
for odds-api.io in Batch 7 without touching the schema, and it is the single
most valuable property of the odds port.

What survives is one field: `fixtures.provider_event_id`, which is odds-api.io's
numeric event id. It is odds-api.io's namespace. Bet365 has never seen it.
`models/match.py` already records the same problem in the other direction —
"providers' event ids share no namespace" — which is why Batch 16 needed
`team_aliases` at all.

So a betslip export cannot start from what is stored. It has to start from the
odds provider, live, at export time.

## What the books actually offer

Four mechanisms were checked. None of them is the one this batch wanted.

**1. Bet365 publishes no betslip API.** Confirmed as expected. Everything
returned by searching for one is a third party: BetsAPI and similar odds
scrapers, or unofficial "place bet" services that drive a logged-in session on
the customer's behalf. Those are out of the question — they need the member's
Bet365 credentials, and handing an unofficial service a bookmaker login to place
real money bets is not something this product will ever do.

**2. Bet Share is real, and points the wrong way.** Bet365 ships a genuine
share feature: a customer sends a link, the recipient opens it, and the
selections load into their own Bet365 app for them to stake themselves. It is
exactly the ergonomics this batch wanted. It is also generated **by a logged-in
Bet365 customer, from their own betslip** — there is no way for an outside
system to mint one. The direction is inbound: a member could share a bet *to*
the group, but The Coupon cannot push a coupon *out*.

Worth noting for a later batch: inbound is a real, if small, product idea, and
it needs nothing from Bet365 but a text field.

**3. Affiliate "add to betslip" links are single-selection.** Several UK books
offer these to affiliates, Bet365 among them, described by practitioners as
painful to implement. The mechanism is the bookmaker's own event id plus its own
market id in a URL — identifiers we do not have and cannot derive. Getting them
means a Bet365 Partners account, which is a commercial affiliate relationship,
not a feature. In every account of how these work, one link carries one
selection.

**4. Our own provider already ships links — and they do not solve it.**
This was the one genuine surprise, and it is worth recording precisely because
it looks like the answer and is not.

odds-api.io advertises "direct bet links — deep links directly to bookmaker bet
slips", and its OpenAPI schema bears it out. `/odds` and `/odds/multi` responses
carry:

- `urls`, an event-level map of bookmaker name to URL, with `Bet365` a
  documented key; and
- `homeLink` / `drawLink` / `awayLink` on each entry under
  `bookmakers[].odds[]`.

Both are already arriving in payloads this application fetches today, and both
are being discarded. `OAEventOdds` does not declare `urls`, so pydantic drops
it; `OAMarket.odds` is `list[dict[str, Any]]` and `_selections_for` reads only
the `home` / `draw` / `away` / `yes` / `no` keys, so the `*Link` values sit
unread in dicts we already have. **Surfacing a link would cost zero extra
requests, zero new providers, and nothing against the 100/hour budget.** Cost is
not what stops this.

Three things stop it:

- **There is no `yesLink` or `noLink`.** The schema documents link fields for
  the three Match Odds sides and nothing else. `BOTH_TEAMS_TO_SCORE` is half
  the markets this game offers and it has no outcome link at all.
- **The one un-elided example is an event page, not a betslip.** Every `urls`
  sample in the vendor's documentation is truncated
  (`"Bet365": "https://www.bet365.com/..."`); the only complete URL published
  anywhere in their docs is a WebSocket example pointing at
  `.../sports/football/match/63017989` — a match page. "Deep link to a betslip"
  is marketing copy that the schema does not substantiate.
- **It is one link per outcome regardless.** Which is the wall.

## The wall: the acca and the ability to mint it never coincide

State this precisely, because the obvious follow-up — "can't we just generate an
add-to-betslip link that copies the whole coupon across?" — deserves an exact
answer rather than a slogan.

Two capabilities are needed: a link that carries **all** the legs, and the
ability for **us** to create it. Bet365 has both. They never come together.

- **Bet Share carries the whole acca.** It is genuinely the feature this batch
  wanted, multiples included. It is minted from inside an authenticated Bet365
  session — the help text is "once you have placed your bet, select Share", and
  the alternative route is the customer's own My Bets or betslip. It starts from
  a bet that a Bet365 customer already holds. We are not that customer, we have
  no session, and there is no unauthenticated entry point.
- **The affiliate add-to-betslip link is one we could create**, with a Bet365
  Partners account — and it carries exactly one selection, keyed on Bet365's own
  event and market ids.

So the answer is no. Nothing we can generate carries more than one leg, and the
one thing that carries eleven can only be created by the person we would be
trying to send it to. Beyond Bet Share, no source — vendor documentation,
affiliate practitioners, or a competing odds API's own deep-link release notes —
describes a URL that loads multiple selections into a betslip together.

**Reverse-engineering the Bet Share encoding is not the way round it.** The
format is undocumented and proprietary; Bet365's terms prohibit automated
analysis or capture of site information; they throttle and change aggressively
to defeat it, and they pursue it. Building the product's headline feature on a
scheme that is both against the counterparty's terms and free to change without
notice trades a permanent obligation for a temporary trick.

A coupon is a `leg_count`-fold accumulator with one leg per member, drawn from
different fixtures in different competitions. Ten members is ten links, ten
pages, and ten manual additions, after which the member still has to switch the
betslip to a multiple themselves. That is worse than reading the ten legs off
the screen we already render, and it is the entire justification for the batch
evaporating.

## The second wall: the odds would be wrong

Independent of the plumbing, and fatal on its own.

`picks.odds_at_pick` is frozen when the pick is submitted, and
`combined_odds` is the product of those frozen prices. That is the game's
scoring rule and it is correct for the game. It also means the headline number
on the coupon screen is a historical price, sometimes days old, that no
bookmaker is still offering.

An exported acca would price at Bet365's live number and disagree with the
figure the member is looking at when they tap the button. Members would read the
gap as a bug in the app, every week, and they would not be wrong to — the two
numbers genuinely mean different things. Explaining that in a tooltip is not a
fix; it is an admission that the export shows something other than the coupon.

## Decision

**Do not build betslip export.** Do not take a Bet365 Partners account for it,
do not surface `urls` or `*Link`, and do not put an outbound bet link on the
coupon screen. The combined acca stays what `services/coupon.py` already calls
it: something "to reference on a real book".

## The contract bullet

The product contract's last line is "the product is for points and fun and never
places a wager."

An export would not literally place a wager — the member stakes it themselves at
the book. Reading the bullet that narrowly is a mistake. The bullet is not a
statement about which function call the code makes; it is what makes this a game
between friends rather than a betting product with a leaderboard attached. A
one-tap route from the group's coupon to a real stake is the thing the bullet
exists to exclude, whoever presses the final button.

That reading is the deciding argument. Even if a book shipped a perfect
eleven-leg accumulator link tomorrow, the answer here would be the same.

## Compliance is the cost nobody costed

Recorded because it would have surfaced late and expensively.

An outbound bet link makes The Coupon gambling advertising. Marketing affiliates
are not themselves licensable in Great Britain, but the operator is held
accountable for affiliate conduct under the LCCP, ASA rulings land on the
operator, and the affiliate carries the compliance obligations in practice. That
brings age-gating, 18+ presentation, responsible-gambling messaging, and content
rules about appeal to under-18s.

The application has **none** of it. Authentication is a display name and a
four-digit PIN; there is no date of birth, no age check, and no
responsible-gambling copy anywhere in `apps/web/src` or `apps/api/src`. A
private game for friends does not need any of that. A surface that routes people
to a bookmaker does. Adding the button is a day; becoming a compliant gambling
affiliate is not, and it is not what the owner asked for.

## What survives

One thing, and it needs no bookmaker at all: **share the coupon as text.** Legs,
selections, prices, combined odds — the same content
`CombinedAccaView.tsx` already renders, formatted for WhatsApp. It works at
every book because it favours none, it adds no gambling-marketing surface, and
it takes the member from "screenshot the screen" to "paste it". If the real
demand behind this batch was the group chat rather than the betslip, that is the
feature, and it is small.

Deliberately not built here — this batch's output is a decision, and adding a
share button to it would smuggle a feature past a spike. It is a candidate row
for a later batch if the owner wants it.

## What was not verified, and what would settle it

The timebox went on the codebase read and the four mechanisms above. Two claims
rest on vendor documentation rather than a live response:

- that `urls` and `homeLink` / `drawLink` / `awayLink` are actually **populated**
  for Bet365 on UK football, rather than merely present in the schema; and
- where those URLs land.

`api.odds-api.io` is reachable from this machine — the note that it was blocked
here no longer holds, verified 2026-08-06 — but no API key is available locally
(`.env.example` carries a placeholder), so the request could not be made. One
authenticated `GET /odds?eventId=<any UK fixture>&bookmakers=Bet365` by the
owner would settle both, and the payload is already fetched in normal operation,
so it costs one request against the daily 500.

It would not change this ADR. Both walls above hold whatever those fields
contain: there is still no `yesLink`, still no way to compose eleven legs into
one link, still a frozen price that disagrees with the book's, and still the
contract bullet.

## Consequences

- Batch 17 closes with a document and no code. The verification gate was run to
  confirm the tree is unchanged and green, not to cover new behaviour.
- The combined coupon stays a scoreboard. `CombinedAccaView.tsx` and
  `GET /leagues/{slug}/coupon` are unchanged and need no export-shaped fields.
- `urls` and the `*Link` keys keep arriving and keep being ignored. That is now
  a recorded decision rather than an oversight, so a future reader who finds
  them in a payload does not re-open this.
- No Bet365 Partners account, and no affiliate relationship. The product takes
  no revenue from anyone's betting.
- The provider-neutral pick identity — no bookmaker ids in the database — is
  reaffirmed. Betslip export was the one plausible reason to reintroduce them,
  and it is rejected.
- Inbound Bet Share (a member pasting a link into the group) and a plain-text
  coupon share are the two ideas worth carrying forward. Neither needs a
  bookmaker integration.

## Sources

- bet365 Bet Share: <https://help.bet365.com/s/en-us/sports/bet-share> (403 to
  automated fetch from here; behaviour taken from
  <https://www.olbg.com/news/bookmaker-betting-news-now-share-your-bets-directly-bet365>)
- Affiliate add-to-betslip practice:
  <https://www.gpwa.org/forum/bookmakers-offering-add-betslip-affiliate-link-236761.html>
- Bet365 terms on automated access and analysis of site information:
  <https://help.bet365.es/s/en-es/terms-and-conditions>
- odds-api.io schema and docs: <https://docs.odds-api.io/api-reference/openapi.json>,
  <https://docs.odds-api.io/llms-full.txt>
- A competing provider's deep-link feature, for comparison:
  <https://the-odds-api.com/releases/deep-links.html>
- GB affiliate obligations: <https://iclg.com/practice-areas/gambling-laws-and-regulations/united-kingdom/>,
  <https://track360.io/blog/ukgc-lccp-affiliate-compliance-checklist-2026>
