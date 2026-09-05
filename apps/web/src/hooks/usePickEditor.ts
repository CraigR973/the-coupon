import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ApiError, NetworkError, apiFetch } from '../lib/api';
import { useOddsFormat } from './useOddsFormat';
import { formatOdds, selectionKey } from '../lib/coupon';
import type {
  PickMarket,
  PickOutcome,
  PickResponse,
  SubmitPickBody,
  SubmitPickResponse,
} from '../lib/types';

// Query keys the pick screen + combined view read; a successful grab invalidates
// all three so the slate re-fetches taken-flags, the coupon rebuilds, and "my
// pick" updates. Exported so the pages register under the same keys.
//
// The gameweek is part of the key because Batch 12 made both reads browsable back
// through the season — without it, viewing a past week would poison the cache
// entry the current week reads from. `undefined` is the "latest" entry.
export const gameweekKey = (slug: string, gameweekId?: string) =>
  ['gameweek', slug, gameweekId] as const;
export const couponKey = (slug: string, gameweekId?: string) =>
  ['coupon', slug, gameweekId] as const;
export const gameweekListKey = (slug: string) => ['gameweeks', slug] as const;
export const myPickKey = (slug: string, gameweekId: string | undefined) =>
  ['my-pick', slug, gameweekId] as const;

/**
 * How long a submission may go unanswered before we stop waiting on it.
 *
 * Longer than the service worker's three-second read timeout, and deliberately so: a
 * read that gives up early costs a spinner, while a write that gives up early throws
 * away an answer that was about to arrive and leaves the member in the one state this
 * hook works hardest to avoid — not knowing whether their claim landed. Twelve seconds
 * covers a slow mobile round trip through the odds provider (the submit path prices the
 * fixture upstream before it commits) without leaving anyone staring at a spinner
 * through the last minute before lock.
 */
export const PICK_SUBMIT_TIMEOUT_MS = 12_000;

/**
 * The refusal a submission gets when the price moved between the card and the tap.
 *
 * Sent as `PRICE_MOVED:<current price>`, which is the only detail in the API that carries
 * a value rather than only a code — see `pickErrorMessage`.
 */
export const PRICE_MOVED = 'PRICE_MOVED';

/** Turn the backend `detail` code into a player-facing message. */
export function pickErrorMessage(detail: string): string {
  switch (detail) {
    case 'SELECTION_TAKEN':
      return 'Someone in your league just grabbed that selection — pick another.';
    case 'FIXTURE_TAKEN':
      return 'Someone in your league already has that game — pick another match.';
    case 'PICKS_LOCKED':
      return 'Picks are locked for this week.';
    case 'PICKS_NOT_OPEN':
      return 'Picks haven’t opened for this round yet — check back closer to kick-off.';
    case 'SELECTION_NOT_AVAILABLE':
      return 'That selection isn’t being priced right now — try another.';
    // Browsing the card falls back to the last known prices; freezing one onto a pick
    // does not, because the price is what a winner is scored on (Batch 48).
    case 'ODDS_UNAVAILABLE':
      return 'Prices are unavailable right now, so your pick wasn’t saved — try again shortly.';
    // Batch 89's shared per-league budget. The league, not this member, is what ran out —
    // the copy has to say so, or a member who has picked once today reads it as an
    // accusation and stops trying.
    case 'PICKS_BUSY':
      return 'Too many picks are being made in your league right now — your pick wasn’t saved. Try again in a few minutes.';
    default:
      // Batch 114. `PRICE_MOVED:<price>` — the code alone is not an answer, because what
      // the member has to decide is whether to take the *new* number, and they cannot
      // decide that without seeing it. The price rides in the detail because `ApiError`
      // keeps only a string one.
      if (detail.startsWith(`${PRICE_MOVED}:`)) {
        const moved = detail.slice(PRICE_MOVED.length + 1);
        return `That price moved before your pick landed — it’s now ${moved}. Tap again to take it.`;
      }
      return detail || 'Could not save your pick — try again.';
  }
}

/**
 * The two states a submission can be left in when the network, rather than the server,
 * is what answered.
 *
 * `queued` — it never left the device, so the server cannot possibly hold it and sending
 * it again is free of consequence. Flushed automatically on reconnect.
 *
 * `unconfirmed` — it left and nothing came back, so the server may or may not have
 * applied it. **Never re-sent automatically.** Reconnecting reads the round's pick back
 * and turns the unknown into a fact; only the member re-sends.
 */
export type OutstandingState = 'queued' | 'unconfirmed';

export interface OutstandingPick {
  /** `${fixtureId}:${market}:${outcome}` — the same key the buttons are addressed by. */
  key: string;
  state: OutstandingState;
  /** What the member was trying to claim, for the copy. */
  body: SubmitPickBody;
}

export interface PickEditor {
  /**
   * Grab (or re-pick to) a selection. One pick per member per gameweek.
   *
   * `odds` is the price the button was showing when it was tapped, carried through so the
   * API can refuse a price that has moved rather than freeze one the member never saw
   * (Batch 114).
   */
  submit: (
    fixtureId: string,
    market: PickMarket,
    outcome: PickOutcome,
    odds?: number,
  ) => void;
  /** `selectionKey` currently being submitted, for a per-button spinner. */
  pendingKey: string | null;
  isSubmitting: boolean;
  /**
   * The one intent this device is holding that the server has not confirmed, if any.
   * `null` whenever the screen and the server agree.
   */
  outstanding: OutstandingPick | null;
  /** Send a `queued` intent, or check an `unconfirmed` one. Safe to call at any time. */
  resolveOutstanding: () => void;
  /** Drop the held intent without sending it — the member decided against it. */
  discardOutstanding: () => void;
  /**
   * Set when the submission just made was the one that filled the coupon. Batch 108.
   *
   * `null` at every other moment, including on a round that was already complete when
   * this member picked into it — see `RoundCompletion`.
   */
  completion: RoundCompletion | null;
  /** Clear the completion hand-off once the member has taken it, or dismissed it. */
  dismissCompletion: () => void;
}

/**
 * The moment this member filled their league's coupon, held long enough to offer them
 * something to do about it.
 *
 * **Why the client decides this rather than the API saying so.** `all_picked` is true for
 * *anyone* who submits into a full coupon, including somebody changing their pick
 * afterwards — the API distinguishes the real transition internally (Batch 107's insert
 * against `uq_gameweek_completions_gameweek` arbitrates it) but does not return that
 * distinction. It does not need to: **a change of pick cannot fill a coupon**, because it
 * moves no count. So "this submission completed the round" is exactly `all_picked` on a
 * submission by a member who did not already hold a pick, and that is a fact the screen
 * already has.
 *
 * Held in memory only, like the outstanding-intent queue above and for the same reason:
 * it is a thing that just happened to this person on this device, not a fact about the
 * round, and a reload finding the coupon already complete should show them the coupon
 * rather than re-congratulate them.
 */
export interface RoundCompletion {
  /** The round they completed — the hand-off must open *that* one, not the current one. */
  gameweekId: string;
  /** Members in the league, both halves of the `12/12` the league's push quotes. */
  memberCount: number;
}

/**
 * The weekly land-grab. Owns the pick mutation (POST .../picks): optimistic
 * per-button pending state, cache invalidation of the slate / coupon / my-pick,
 * and mapping the backend's 409/422 detail codes to friendly toasts.
 *
 * The odds are snapshotted server-side, so the client sends only the selection
 * identity `{ fixture_id, market, outcome }`.
 *
 * ## Why this hook is more than a `useMutation` (Batch 90)
 *
 * This is the one write the product is built around, and it is used hardest in the worst
 * conditions the app ever sees — a pub, on a phone, in the hour before Saturday lock. It
 * used to be a bare mutation whose every failure became the same sentence, so "the wifi
 * dropped" and "someone beat you to Arsenal" were indistinguishable, and a member could
 * not tell whether the claim they had just made was theirs.
 *
 * Three things follow from the domain and they drive the whole design:
 *
 * 1. **A pick is a claim in a first-come race.** Silence is the worst answer, because the
 *    member's next move (pick something else, or stop worrying) depends entirely on which
 *    way it went.
 * 2. **A retry can do real harm.** The server updates a member's pick *in place*, so
 *    re-sending an unanswered submission is safe for that submission — but if the member
 *    has since chosen something else, a late retry of the older intent silently takes
 *    their claim backwards. That is worse than the failure it was trying to fix, so the
 *    unknown case is never retried on its own.
 * 3. **Only the newest intent can be right.** One pick per member per round means the
 *    queue is a single slot, not a log: a newer selection supersedes an older unsent one
 *    rather than queueing behind it. This is the property that makes reconnecting safe.
 *
 * ## Why the queue is in memory and not on disk
 *
 * Deliberately not persisted — no IndexedDB, no Background Sync, nothing that outlives
 * the tab. Batch 87 (SEC-13) had just finished stopping this app from keeping API
 * responses on the device, and while a queued pick is a different kind of thing (the
 * member's own unsent intent, containing nobody else's league data) the argument for
 * persisting it does not survive the obvious question: when does it get cleared? An
 * intent that outlives a sign-out fires under whoever holds the phone next, which is a
 * worse failure than the one it prevents. The case it would cover — the member closes
 * the tab while offline and comes back later — is one where re-picking is what they would
 * expect anyway.
 */
export function usePickEditor(
  slug: string,
  gameweekId: string | undefined,
  { holdsPick = false }: { holdsPick?: boolean } = {},
): PickEditor {
  const queryClient = useQueryClient();
  const oddsFormat = useOddsFormat();
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [outstanding, setOutstanding] = useState<OutstandingPick | null>(null);
  const [completion, setCompletion] = useState<RoundCompletion | null>(null);

  // Whether this member already held a pick, captured at the instant `submit` is called
  // rather than read in `onSuccess`. By then the invalidation this hook fires may have
  // refetched the slate, and the answer would be the post-submission one — which is
  // always "yes", and would turn the completion hand-off off permanently.
  const holdsPickRef = useRef(holdsPick);
  holdsPickRef.current = holdsPick;
  const heldAtSubmitRef = useRef(false);

  // The reconnect handler reads this, and it is registered once — a state value captured
  // in that closure would be whatever it was when the listener was attached.
  const outstandingRef = useRef<OutstandingPick | null>(null);
  const hold = useCallback((next: OutstandingPick | null) => {
    outstandingRef.current = next;
    setOutstanding(next);
  }, []);

  const invalidate = useCallback(() => {
    // Prefix-matched, so every gameweek's entry for this league is refreshed —
    // a grab changes the season list's pick counts as well as this week's slate.
    void queryClient.invalidateQueries({ queryKey: ['gameweek', slug] });
    void queryClient.invalidateQueries({ queryKey: ['coupon', slug] });
    void queryClient.invalidateQueries({ queryKey: gameweekListKey(slug) });
    void queryClient.invalidateQueries({ queryKey: myPickKey(slug, gameweekId) });
  }, [queryClient, slug, gameweekId]);

  /**
   * Read the round's pick back and settle what an unanswered submission actually did.
   *
   * This is the whole answer to "unknown": the server already holds the truth, and one
   * cheap `GET` converts a state the member cannot act on into one they can. It is a read,
   * so running it is never the thing that changes anything.
   *
   * A pick that came back matching the intent *did* land — say so, because the member has
   * spent the last few seconds believing they had lost the race. Anything else means the
   * claim is not theirs, and the intent drops back to `queued`: the server demonstrably
   * does not hold it, so sending it again can no longer overwrite anything.
   */
  const reconcile = useCallback(
    async (body: SubmitPickBody) => {
      if (gameweekId === undefined) return;
      let held: PickResponse | null;
      try {
        held = await apiFetch<PickResponse | null>(
          `/api/v1/leagues/${slug}/gameweeks/${gameweekId}/pick`,
        );
      } catch {
        // Still unreachable. The intent stays `unconfirmed` and the next reconnect tries
        // again — reporting a guess here would be the failure this batch exists to end.
        return;
      }

      const current = outstandingRef.current;
      // The member moved on while the check was in flight; that newer intent is the only
      // one that can be right, so this answer is about a claim nobody is waiting on.
      if (current === null || current.key !== keyFor(body)) return;

      if (held !== null && matches(held, body)) {
        hold(null);
        invalidate();
        toast.success(`Your pick did land — ${held.runner_name} is yours.`);
        return;
      }

      hold({ key: current.key, state: 'queued', body });
      invalidate();
      toast.error('Your pick didn’t land — it’s ready to send again.');
    },
    [slug, gameweekId, hold, invalidate],
  );
  const reconcileRef = useRef(reconcile);
  reconcileRef.current = reconcile;

  const mutation = useMutation({
    mutationFn: (body: SubmitPickBody) =>
      apiFetch<SubmitPickResponse>(`/api/v1/leagues/${slug}/picks`, {
        method: 'POST',
        body: JSON.stringify(body),
        timeoutMs: PICK_SUBMIT_TIMEOUT_MS,
      }),
    onSuccess: (pick) => {
      hold(null);
      invalidate();

      // The completion **replaces** the grab toast rather than stacking on top of it,
      // which is the same rule Batch 107 gave the push: one event reached the member, not
      // two, and of the pair this is the one that says something they could not otherwise
      // know. The price is still in the copy, so nothing is lost by dropping the other.
      if (pick.all_picked && !heldAtSubmitRef.current) {
        setCompletion({ gameweekId: pick.gameweek_id, memberCount: pick.member_count });
        return;
      }
      toast.success(`Grabbed ${pick.runner_name} @ ${formatOdds(pick.odds, oddsFormat)}`);
    },
    onError: (err, body) => {
      // A refusal is an *answer*: the server saw the claim and said no. The member's
      // pick did not land and they know exactly why, so nothing is held.
      if (err instanceof ApiError) {
        hold(null);
        toast.error(pickErrorMessage(err.message));
        return;
      }
      if (err instanceof NetworkError && !err.mayHaveLanded) {
        hold({ key: keyFor(body), state: 'queued', body });
        toast.error('You’re offline — we’ll send this pick the moment you’re back.');
        return;
      }
      // Everything else is the unknown case, including a plain `Error` from somewhere
      // that has not been given a type: assume it may have landed. Guessing the safe way
      // costs a check; guessing the other way costs a member their claim.
      hold({ key: keyFor(body), state: 'unconfirmed', body });
      toast.error('We didn’t hear back — your pick may not have been saved. Checking…');
      void reconcile(body);
    },
    onSettled: () => setPendingKey(null),
  });

  // Held in a ref so the reconnect listener and `onError` can both reach the current
  // one; `mutate` itself is stable across renders but the surrounding closures are not.
  const mutateRef = useRef(mutation.mutate);
  mutateRef.current = mutation.mutate;


  const send = useCallback((body: SubmitPickBody) => {
    heldAtSubmitRef.current = holdsPickRef.current;
    setPendingKey(keyFor(body));
    mutateRef.current(body);
  }, []);

  const submit = useCallback(
    (fixtureId: string, market: PickMarket, outcome: PickOutcome, odds?: number) => {
      const body: SubmitPickBody = { fixture_id: fixtureId, market, outcome, odds };
      // Drop whatever was held before this one goes out. One pick per member per round
      // means the newest intent is the only one that can be correct, so an older unsent
      // intent must not survive to fire later and take the member's claim backwards —
      // and an older *unconfirmed* one must not either, because reconciling it after
      // this lands would report on a claim nobody is waiting for. Whether this attempt
      // ends up held, and in which state, is `onError`'s answer.
      hold(null);
      send(body);
    },
    [hold, send],
  );

  const resolveOutstanding = useCallback(() => {
    const current = outstandingRef.current;
    if (current === null) return;
    if (current.state === 'queued') {
      send(current.body);
      return;
    }
    void reconcileRef.current(current.body);
  }, [send]);

  const discardOutstanding = useCallback(() => hold(null), [hold]);

  const dismissCompletion = useCallback(() => setCompletion(null), []);

  // Reconnecting is the moment both held states can be settled, and each gets the
  // treatment its certainty earns: a queued intent is sent, an unconfirmed one is only
  // read back. Nothing here can re-send a claim whose fate is unknown.
  useEffect(() => {
    const onReconnect = () => {
      const current = outstandingRef.current;
      if (current === null) return;
      if (current.state === 'queued') send(current.body);
      else void reconcileRef.current(current.body);
    };
    window.addEventListener('online', onReconnect);
    return () => window.removeEventListener('online', onReconnect);
  }, [send]);

  return {
    submit,
    pendingKey,
    isSubmitting: mutation.isPending,
    outstanding,
    resolveOutstanding,
    discardOutstanding,
    completion,
    dismissCompletion,
  };
}

function keyFor(body: SubmitPickBody): string {
  return `${body.fixture_id}:${selectionKey(body.market, body.outcome)}`;
}

function matches(pick: PickResponse, body: SubmitPickBody): boolean {
  return (
    pick.fixture_id === body.fixture_id &&
    pick.market === body.market &&
    pick.outcome === body.outcome
  );
}
