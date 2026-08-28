"""When has FotMob "bitten"? — the trigger this product had no definition for.

Batch 101, from FEAT-A07. FotMob's terms prohibit automated access. The owner took that
knowingly and it stays revisitable; what was missing was the *revisit signal*. Three
shipped features rest on it — Football Stats (Batches 46/51), the void-fixture
cross-check that removes phantom fixtures before lock (Batch 64) and live in-play scores
(Batch 72) — and TheSportsDB is named as the fallback with nothing tracking when to reach
for it. The switch should be a decision somebody makes, not something discovered on a
Saturday when the card breaks.

**What counts, and what deliberately does not.**

* **A block is immediate.** ``401``, ``403`` and ``451`` are the terms being enforced
  rather than a bad afternoon, and one is the whole signal. Waiting for a second would be
  waiting to be told twice.
* **Everything else has to be sustained.** A timeout, a ``500``, a ``429``, a connection
  reset — these are what any HTTP call to anyone does sometimes, and alerting on one
  would train the owner to ignore the alert. It takes
  :data:`CONSECUTIVE_FAILURES_BEFORE_ALERT` in a row with no success between, which a
  daily thirty-competition sweep reaches inside one run when the source is genuinely
  gone and never reaches on an ordinary hiccup.
* **A success clears the run.** The counter is consecutive, not cumulative: a source that
  fails one competition in thirty every day is not degrading, and treating it as such
  would fire eventually no matter how healthy things were.

**The cross-check is the loud one, and it is not a request-level signal at all.**
:func:`~src.services.slate_verification.verify_slate` fails *open* by design — an
unverifiable fixture is left exactly as the odds provider gave it, because deleting a
real fixture off a live card is worse than the phantom it would prevent. That is the
right behaviour and it is also silent: a slate where **nothing** could be verified looks
identical to a slate where everything was fine. It is the one FotMob dependency that
decides whether a member's pick is valid, so it reports itself separately and loudly,
however healthy the individual requests looked.

**In-process, and that is a considered choice.** A redeploy clears the counter and it
re-accumulates within one sweep, because a block answers every request and a dead source
fails every one. Batch 99 moved counters to Postgres where a reset *hands something back*
— attempts an attacker would otherwise have spent. Here a reset costs at most one sweep's
worth of delay before the same alert fires again. What is durable is the alert itself:
:data:`~src.models.notification.ActionType.football_provider_degraded` rows are the
record, and the cooldown that stops a ten-minute job pushing every ten minutes reads
them, not this.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

#: Statuses that mean "you are not welcome" rather than "try again". A single one is the
#: signal — these are the terms being applied, and they do not un-apply.
BLOCK_STATUSES = frozenset({401, 403, 451})

#: How many consecutive failures of any other kind add up to "this has bitten". A daily
#: sweep touches ~30 competitions, so a genuinely absent source clears this inside one
#: run; nothing short of five in a row without a single success does.
CONSECUTIVE_FAILURES_BEFORE_ALERT = 5


class FotMobTrouble(StrEnum):
    """What kind of trouble, because the answer changes what the owner should do."""

    #: Refused. Revisit the provider decision — this is the one FEAT-A07 anticipated.
    blocked = "blocked"
    #: Failing consistently without refusing. Could be an outage, could be a moved path.
    unreachable = "unreachable"
    #: A whole slate went unverified before lock. The pick-validity path, blind.
    blind_cross_check = "blind_cross_check"


@dataclass(frozen=True)
class FotMobAlert:
    """One thing worth telling somebody, with enough detail to act on it."""

    trouble: FotMobTrouble
    detail: str

    @property
    def loud(self) -> bool:
        """Whether this reaches an admin's phone on the short cooldown.

        A block is the decision the owner asked to be told about, and a blind cross-check
        is a card that may be carrying fixtures nobody checked. Sustained unreachability
        is a real signal but not one that needs somebody's Saturday afternoon.
        """
        return self.trouble is not FotMobTrouble.unreachable

    @property
    def title(self) -> str:
        return {
            FotMobTrouble.blocked: "Football data source refused",
            FotMobTrouble.unreachable: "Football data source failing",
            FotMobTrouble.blind_cross_check: "Fixtures went unchecked before lock",
        }[self.trouble]


class FotMobHealth:
    """Consecutive-failure state for one process, and the alert it has decided to raise.

    Not a metric — it answers exactly one question, "should somebody be told", and holds
    the answer until a caller with a database session comes to collect it.
    """

    def __init__(self) -> None:
        self._consecutive_failures = 0
        self._pending: FotMobAlert | None = None

    def reset(self) -> None:
        """Forget everything. What a restart does, and what tests need between them."""
        self._consecutive_failures = 0
        self._pending = None

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def request_succeeded(self) -> None:
        self._consecutive_failures = 0

    def request_failed(self, *, status: int | None, reason: str) -> None:
        """Record one failed call. Raises nothing — the caller is already raising."""
        if status in BLOCK_STATUSES:
            self._consecutive_failures = 0
            self._raise_alert(
                FotMobTrouble.blocked,
                f"FotMob answered {status}. {reason}",
            )
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= CONSECUTIVE_FAILURES_BEFORE_ALERT:
            self._raise_alert(
                FotMobTrouble.unreachable,
                f"{self._consecutive_failures} consecutive failures, most recently: {reason}",
            )

    def cross_check_saw_nothing(self, *, starts_on: date, fixtures: int) -> None:
        """A non-empty slate of which not one fixture could be verified.

        Called by :func:`~src.services.slate_verification.verify_slate` and nowhere else.
        Not derived from request failures on purpose: a competition FotMob simply does
        not carry answers ``200`` and returns nothing, so a slate can go entirely
        unverified without a single failed request.
        """
        self._raise_alert(
            FotMobTrouble.blind_cross_check,
            f"None of the {fixtures} fixtures on the {starts_on} card could be checked "
            "against the football data source, so the void cross-check had no opinion "
            "on any of them.",
        )

    def _raise_alert(self, trouble: FotMobTrouble, detail: str) -> None:
        """Keep the more serious of what is already pending and what has just happened.

        A collector may not arrive for ten minutes, and in that time a block should not be
        overwritten by a run of ordinary failures that followed it.
        """
        candidate = FotMobAlert(trouble=trouble, detail=detail)
        if self._pending is not None and self._pending.loud and not candidate.loud:
            return
        log.warning("fotmob trouble", trouble=str(trouble), detail=detail)
        self._pending = candidate

    def take_alert(self) -> FotMobAlert | None:
        """The pending alert, cleared. Collected once, by whoever has a session."""
        alert, self._pending = self._pending, None
        return alert


#: One per process, alongside ``football_session``'s single client. Reset by
#: ``tests/conftest.py`` between tests.
fotmob_health = FotMobHealth()
