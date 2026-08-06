"""Name reconciliation between the two providers' team spellings.

``fixtures.home`` / ``away`` are free text from odds-api.io; ``teams.name`` is free text
from the football-data source. Nothing joins them. "Airdrieonians FC" and "Airdrieonians"
are the same club, and so are "Nott'm Forest" and "Nottingham Forest", but a string
comparison says otherwise — and matching a provider's own vocabulary by exact string has
already caused three defects in this project (Betfair's certlogin field names, its
sponsored English competition names, and a division allow-list that starved the slate).

So the layer is three stages, cheapest first, each one narrower than a bare fuzzy match:

1. **Alias lookup.** Every spelling ever resolved is stored in ``team_aliases``, keyed by
   ``(competition_id, normalised)``. This is a primary-key hit and covers everything after
   the first sighting.
2. **Normalised equality.** Case, accents, punctuation, club designators ("FC", "AFC")
   and a small set of British abbreviations are folded away, so most first sightings match
   outright.
3. **Similarity, scoped to the competition and only when it is decisive.** The candidate
   pool is one division — around two dozen clubs — and a match must clear a threshold
   *and* beat the runner-up by a margin. Two clubs that look equally like the input are
   left unresolved rather than resolved arbitrarily: no form line is much better than the
   wrong club's form line.

Every resolution is written back as an alias, so the layer gets cheaper and more accurate
as it runs, and every link it has made is one visible, correctable row.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from difflib import SequenceMatcher

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.team import Team, TeamAlias

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Tokens that say "this is a football club" rather than *which* football club. Dropped so
# "Airdrieonians FC" and "Airdrieonians" normalise alike.
#
# Deliberately short. "Town", "City", "United", "Rovers" and "Athletic" are *not* here:
# they are what tells Boston United from Boston Town, and dropping them would merge clubs
# that genuinely share a place name — the failure this layer exists to avoid.
_CLUB_WORDS: frozenset[str] = frozenset(
    {"fc", "afc", "cfc", "rfc", "sfc", "fk", "sk", "cf", "sc", "ac", "football", "club"}
)

# Abbreviations British sources use, expanded to the long form both providers agree on.
# One token may expand to several. Everything here was chosen because the two spellings
# appear in real UK listings, not to make fuzzy matching easier — an expansion that is
# wrong merges two clubs permanently, so the bar is "unambiguous across the four home
# nations", and anything short of that is left to an alias row instead.
_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "utd": ("united",),
    "nottm": ("nottingham",),
    "sheff": ("sheffield",),
    "wed": ("wednesday",),
    "wolves": ("wolverhampton", "wanderers"),
    "spurs": ("tottenham", "hotspur"),
    "qpr": ("queens", "park", "rangers"),
    "hearts": ("heart", "of", "midlothian"),
    "hibs": ("hibernian",),
    "st": ("saint",),
    "sainttrinity": ("saint", "trinity"),
    "athl": ("athletic",),
    "acad": ("academy",),
    "res": ("reserves",),
}

#: A similarity below this is never a match, however far ahead of the runner-up it is.
MATCH_THRESHOLD = 0.86
#: …and it must also beat the runner-up by this much, or the input is ambiguous.
MATCH_MARGIN = 0.05
#: What one name's words being a strict subset of the other's is worth — "Inverness
#: Caledonian" against "Inverness Caledonian Thistle". Deliberately below 1.0, so an
#: exact match always outranks a subset of itself: with both "Rangers" and "Queens Park
#: Rangers" in a division, "Rangers" must resolve to the club actually called that.
SUBSET_SCORE = 0.95

# Apostrophes and full stops are *intra-word* punctuation in club names, so they are
# deleted rather than turned into a space: "Nott'm" has to stay one token for the
# abbreviation to expand, and "F.C." has to fold to "fc" rather than "f c".
_INTRA_WORD = re.compile(r"[.'’ʼ]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise_name(name: str) -> str:
    """Fold a club name to the form aliases and comparisons are keyed on.

    Accents are stripped, ``&`` becomes ``and``, punctuation and case go, British
    abbreviations expand, and club designators are dropped. ``"Nott'm Forest FC"`` and
    ``"Nottingham Forest"`` both become ``"nottingham forest"``.

    A name made entirely of club designators keeps them — dropping every token would
    normalise it to the empty string, which would then match every other such name.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    tidied = _INTRA_WORD.sub("", stripped.casefold().replace("&", " and "))
    folded = _NON_ALNUM.sub(" ", tidied)

    expanded: list[str] = []
    for token in folded.split():
        expanded.extend(_EXPANSIONS.get(token, (token,)))
    kept = [token for token in expanded if token not in _CLUB_WORDS]
    return " ".join(kept or expanded)


def similarity(left: str, right: str) -> float:
    """How alike two already-normalised names are, in ``0.0`` to ``1.0``.

    Three views, best-of, because each catches a difference the others score badly:

    * character similarity, for spelling drift ("Airdrieonians" / "Airdrieonian");
    * shared-token proportion, for a differing word ("Bangor City" / "Bangor Town");
    * a flat :data:`SUBSET_SCORE` when one name's words are *all* in the other's
      ("Inverness Caledonian" / "Inverness Caledonian Thistle"), which the first two both
      score below the threshold on a three-word name.

    The subset score is a strong claim, not a certain one, so it stays below an exact
    match and leans on :func:`best_match`'s ambiguity guard: when a division holds both
    "Boston United" and "Boston Town", a bare "Boston" is a subset of each, they tie, and
    nothing is resolved.
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    left_tokens, right_tokens = set(left.split()), set(right.split())
    shared = left_tokens & right_tokens
    if not shared:
        return ratio
    score = max(ratio, len(shared) / max(len(left_tokens), len(right_tokens)))
    if shared in (left_tokens, right_tokens):
        score = max(score, SUBSET_SCORE)
    return score


def best_match(name: str, candidates: Sequence[Team]) -> tuple[Team | None, float]:
    """The candidate a normalised name most likely means, and its score.

    Returns ``(None, score)`` when nothing clears :data:`MATCH_THRESHOLD`, or when the
    top two candidates are within :data:`MATCH_MARGIN` of each other. An ambiguous name
    is left unresolved on purpose: the screens degrade to showing no form, which is a
    great deal better than confidently showing another club's.
    """
    scored = sorted(
        ((similarity(name, team.normalised_name), team) for team in candidates),
        key=lambda pair: (pair[0], pair[1].normalised_name),
        reverse=True,
    )
    if not scored:
        return None, 0.0
    top_score, top_team = scored[0]
    if top_score < MATCH_THRESHOLD:
        return None, top_score
    if len(scored) > 1 and top_score - scored[1][0] < MATCH_MARGIN:
        log.info(
            "team name ambiguous",
            name=name,
            first=top_team.normalised_name,
            second=scored[1][1].normalised_name,
            score=round(top_score, 3),
        )
        return None, top_score
    return top_team, top_score


async def record_alias(
    db: AsyncSession, competition_id: str, name: str, team: Team, *, source: str = "provider"
) -> None:
    """Remember that ``name`` means ``team`` in this competition.

    Idempotent, and does not re-point an existing alias: the first resolution wins, so a
    later fuzzy match cannot silently overwrite a link made from the provider's own name
    or corrected by hand. Flushes but does not commit.
    """
    normalised = normalise_name(name)
    if not normalised:
        return
    existing = await db.get(TeamAlias, (competition_id, normalised))
    if existing is not None:
        return
    db.add(
        TeamAlias(
            competition_id=competition_id,
            normalised=normalised,
            team_id=team.id,
            alias=name[:120],
            source=source,
        )
    )
    await db.flush()


async def competition_teams(db: AsyncSession, competition_id: str) -> list[Team]:
    """Every club recorded in one competition — the candidate pool for a fuzzy match."""
    result = await db.execute(select(Team).where(Team.competition_id == competition_id))
    return list(result.scalars().all())


async def resolve_names(
    db: AsyncSession, competition_id: str, names: Iterable[str], *, source: str = "odds"
) -> dict[str, Team]:
    """Resolve free-text club names within one competition, learning what it resolves.

    Batched on purpose: a slate asks about every club on the card at once, so the alias
    table is read in one query and the candidate pool loaded at most once, rather than
    per name. Names that do not resolve are simply absent from the result — callers show
    nothing for them.

    Flushes any learned aliases but does not commit; the caller owns the transaction.
    """
    wanted = {name: normalise_name(name) for name in names if name and name.strip()}
    if not wanted:
        return {}

    alias_rows = await db.execute(
        select(TeamAlias.normalised, Team)
        .join(Team, Team.id == TeamAlias.team_id)
        .where(
            TeamAlias.competition_id == competition_id,
            TeamAlias.normalised.in_(set(wanted.values())),
        )
    )
    by_normalised: dict[str, Team] = {row[0]: row[1] for row in alias_rows.all()}

    resolved: dict[str, Team] = {}
    unresolved: dict[str, str] = {}
    for name, normalised in wanted.items():
        team = by_normalised.get(normalised)
        if team is not None:
            resolved[name] = team
        else:
            unresolved[name] = normalised
    if not unresolved:
        return resolved

    candidates = await competition_teams(db, competition_id)
    for name, normalised in unresolved.items():
        team, score = best_match(normalised, candidates)
        if team is None:
            log.info(
                "team name unresolved",
                competition_id=competition_id,
                name=name,
                best_score=round(score, 3),
                candidates=len(candidates),
            )
            continue
        resolved[name] = team
        await record_alias(db, competition_id, name, team, source=source)
    return resolved
