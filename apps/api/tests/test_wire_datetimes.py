"""Every instant the API serialises must carry its UTC offset (Batch 43).

The defect this guards against is not visible in Python. `datetime(2026, 8, 22, 13, 30)`
is a perfectly good UTC instant here and compares correctly against every other one;
it only goes wrong on the wire, where pydantic renders it `"2026-08-22T13:30:00"` and
JavaScript's `Date` reads an offset-less date-time string as **local** time. Under BST
that is an hour early, so the pick screen's countdown expired while the API was still
accepting picks — and under GMT the same code is correct, which is what made it look
like something else for as long as it did.

`test_every_serialised_datetime_carries_an_offset` walks the app's own routes rather
than a list maintained here, so a response model written next year is covered the day
it is added.
"""

from __future__ import annotations

import types
import typing
from datetime import UTC, datetime
from typing import Annotated, get_args, get_origin, get_type_hints

from fastapi.routing import APIRoute
from pydantic import BaseModel

from src.main import app
from src.schemas import UtcDatetime, stamp_utc

# ── The alias itself ───────────────────────────────────────────────────────────


class _Instant(BaseModel):
    at: UtcDatetime
    maybe: UtcDatetime | None


def test_a_naive_value_is_serialised_as_utc() -> None:
    """The storage convention is naive UTC, so this is the case that matters."""
    payload = _Instant(at=datetime(2026, 8, 22, 13, 30), maybe=None).model_dump_json()
    assert '"at":"2026-08-22T13:30:00Z"' in payload
    assert '"maybe":null' in payload


def test_an_aware_value_is_converted_rather_than_relabelled() -> None:
    """A value already carrying an offset must move to UTC, not have UTC stamped on it."""
    london = datetime(2026, 8, 22, 14, 30, tzinfo=UTC).astimezone(
        __import__("zoneinfo").ZoneInfo("Europe/London")
    )
    assert london.hour == 15  # 14:30 UTC is 15:30 in London under BST
    payload = _Instant(at=london, maybe=london).model_dump_json()
    assert payload.count('"2026-08-22T14:30:00Z"') == 2


def test_the_python_mode_dump_stays_a_datetime() -> None:
    """Only the JSON gains the offset — internal callers still get a `datetime`."""
    dumped = _Instant(at=datetime(2026, 8, 22, 13, 30), maybe=None).model_dump()
    assert dumped["at"] == datetime(2026, 8, 22, 13, 30, tzinfo=UTC)


def test_stamp_utc_leaves_a_utc_value_alone() -> None:
    aware = datetime(2026, 8, 22, 13, 30, tzinfo=UTC)
    assert stamp_utc(aware) is aware or stamp_utc(aware) == aware


# ── The guard ──────────────────────────────────────────────────────────────────


def _unwrap(hint: object) -> list[object]:
    """Flatten a union into its members, leaving `Annotated` aliases intact."""
    if get_origin(hint) in (typing.Union, types.UnionType):
        return [arg for arg in get_args(hint) if arg is not type(None)]
    return [hint]


def _element_types(hint: object) -> list[object]:
    """Members of a `list[...]` / `dict[..., ...]`, so nesting is followed too."""
    origin = get_origin(hint)
    if origin in (list, set, tuple, frozenset):
        return list(get_args(hint))
    if origin is dict:
        return list(get_args(hint))[1:]
    return []


def _response_models() -> list[type[BaseModel]]:
    models: list[type[BaseModel]] = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.response_model is not None:
            for member in _unwrap(route.response_model):
                models.extend(
                    m
                    for m in [member, *_element_types(member)]
                    if isinstance(m, type) and issubclass(m, BaseModel)
                )
    return models


def _candidates(hint: object) -> list[object]:
    """Every type a field could serialise: union members and their element types."""
    return [c for member in _unwrap(hint) for c in [member, *_element_types(member)]]


def _reachable(roots: list[type[BaseModel]]) -> set[type[BaseModel]]:
    """`roots` plus every model they nest, however deep — the real serialised surface."""
    seen: set[type[BaseModel]] = set()
    queue = list(roots)
    while queue:
        model = queue.pop()
        if model in seen:
            continue
        seen.add(model)
        for hint in get_type_hints(model, include_extras=True).values():
            queue.extend(
                c
                for c in _candidates(hint)
                if isinstance(c, type) and issubclass(c, BaseModel) and c not in seen
            )
    return seen


def _offending_fields(model: type[BaseModel]) -> list[str]:
    """This model's own fields that serialise a datetime with no offset."""
    bad: list[str] = []
    for name, hint in get_type_hints(model, include_extras=True).items():
        for candidate in _candidates(hint):
            bare = candidate is datetime
            aliased_wrong = (
                get_origin(candidate) is Annotated
                and get_args(candidate)[0] is datetime
                and candidate != UtcDatetime
            )
            if bare or aliased_wrong:
                bad.append(f"{model.__name__}.{name}")
    return bad


def test_the_walk_finds_the_models_it_claims_to() -> None:
    """A guard that silently matched nothing would pass forever.

    ``CurrentRound`` is nested two models deep under ``/me/cross-league-summary``, so
    it also proves the closure follows nesting rather than stopping at the route.
    """
    names = {m.__name__ for m in _reachable(_response_models())}
    assert {"GameweekSlateResponse", "LeagueDetailResponse", "CurrentRound"} <= names


def test_every_serialised_datetime_carries_an_offset() -> None:
    bad: list[str] = []
    for model in _reachable(_response_models()):
        bad.extend(_offending_fields(model))
    assert not bad, (
        "these response fields serialise a datetime with no UTC offset, which "
        "JavaScript reads as local time — annotate them `UtcDatetime` "
        f"(src/schemas.py): {sorted(set(bad))}"
    )
