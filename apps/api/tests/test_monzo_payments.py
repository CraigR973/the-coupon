"""Batch 208 — payments through the league's Monzo link reach the ledger (ADR 0009).

The payments service reads the owner's Monzo account and writes the league's link payments
to the ledger. Every Monzo response here is synthetic, shaped like ADR 0009's evidence: an
app payer with a stable ``user_…`` id, a card payer with a fresh ``anonuser_…`` id every
time, both through one ``unipaylink_…`` link. Nothing calls Monzo. The row's cases:

* the link filter;
* both payer kinds;
* deduplication across events;
* an unsigned webhook body never trusted without a re-read;
* refresh with rotation;
* a Monzo outage leaving manual entry working.

Plus what the owner's decisions of 2026-10-16 add: only payments made after the connection
count, nothing is read until a league has a link id, and the service registers its own
webhook. The service commits through its own sessions, so every row is removed again by
the ``world`` fixture, including the one connection row.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.auth import create_access_token, hash_pin
from src.main import app as api_app
from src.models.league import League, LeaguePrivacy
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind, PayerMapping
from src.models.monzo_connection import MonzoConnection, MonzoLinkStatus, MonzoPot
from src.models.notification import ActionType, AuditLog
from src.models.profile import Profile, UserRole
from src.payments_service import __main__ as payments_main
from src.payments_service import app as payments_app
from src.payments_service.__main__ import configure_payments_logging
from src.payments_service.crypto import TokenCipher, TokenCipherUnavailable, TokenUnreadable
from src.payments_service.ingest import (
    account_holders,
    link_payment,
    pot_ref_fields,
    pot_top_up,
    transaction_shape,
)
from src.payments_service.monzo import ALLOWED_CALLS, MonzoCallRefused, MonzoClient, MonzoRefused
from src.payments_service.reader import (
    ConnectOutcome,
    PaymentsReader,
    ReadOutcome,
)
from src.payments_service.settings import (
    PRODUCTION_ORIGIN,
    MonzoSettings,
    monzo_settings,
    monzo_settings_problems,
)

_API = Path(__file__).resolve().parents[1]
_ROOT = _API.parents[1]

PIN = "1234"
FEE = 100
NOW = datetime(2026, 10, 16, 12, 0)
PATH_SECRET = "path-Secret_marker" + "A" * 25 + "="
CLIENT_SECRET = "client-secret-marker"
OWNER = "user_00009Owner"


def _rfc3339(moment: datetime) -> str:
    return moment.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _settings() -> MonzoSettings:
    return MonzoSettings(
        client_id="oauth2client_00009Test",
        client_secret=CLIENT_SECRET,
        encryption_key=Fernet.generate_key().decode(),
        webhook_path_secret=PATH_SECRET,
    )


def _link() -> str:
    return f"unipaylink_{uuid.uuid4().hex}"


def app_payment(
    tx_id: str,
    link: str,
    *,
    user: str = "user_00009Jamie",
    name: str = "Jamie Smith",
    amount: int = FEE,
    created: datetime = NOW + timedelta(minutes=1),
) -> dict[str, Any]:
    """Paid in the Monzo app: a stable user id, the link in the metadata."""
    return {
        "id": tx_id,
        "created": _rfc3339(created),
        "amount": amount,
        "currency": "GBP",
        "description": "DESCRIPTION-MARKER",
        "scheme": "p2p_payment",
        "notes": "",
        "metadata": {"p2p_initiator": "collection-pot", "universal_payment_link_id": link},
        "counterparty": {"user_id": user, "name": name},
    }


def card_payment(
    tx_id: str,
    link: str,
    *,
    name: str = "J. Smith",
    amount: int = FEE,
    created: datetime = NOW + timedelta(minutes=1),
) -> dict[str, Any]:
    """Paid by card through the link page: a fresh anonymous id every time."""
    return {
        "id": tx_id,
        "created": _rfc3339(created),
        "amount": amount,
        "currency": "GBP",
        "description": "DESCRIPTION-MARKER",
        "scheme": "topup",
        "notes": "MESSAGE-MARKER",
        "metadata": {"link_type": "collection_pot", "universal_payment_link_id": link},
        "counterparty": {"user_id": f"anonuser_{uuid.uuid4().hex[:12]}", "name": name},
    }


# ── A synthetic Monzo ──────────────────────────────────────────────────────────


class FakeMonzo:
    """Monzo's documented surface, in memory. Records every call it is asked to answer."""

    def __init__(self) -> None:
        self.accounts: list[dict[str, Any]] = [
            {"id": "acc_00009Main", "closed": False},
            {"id": "acc_00009Closed", "closed": True},
        ]
        self.transactions: dict[str, list[dict[str, Any]]] = {"acc_00009Main": []}
        self.webhooks: list[dict[str, str]] = []
        self.calls: list[tuple[str, str]] = []
        self.user_id = OWNER
        self.approved = False
        self.down = False
        self.refuse_refresh = False
        self.live_access: set[str] = set()
        self.live_refresh: set[str] = set()
        self.refreshed_with: list[str] = []
        #: Every ``since`` a transactions read asked for, in order (Batch 214).
        self.since_asked: list[str] = []
        self._issued = 0

    def add(self, transaction: dict[str, Any], account: str = "acc_00009Main") -> None:
        self.transactions.setdefault(account, []).append(transaction)

    def find(self, tx_id: str) -> dict[str, Any] | None:
        for listed in self.transactions.values():
            for transaction in listed:
                if transaction["id"] == tx_id:
                    return transaction
        return None

    def _grant(self) -> httpx.Response:
        self._issued += 1
        access, refresh = f"access-{self._issued}", f"refresh-{self._issued}"
        self.live_access.add(access)
        self.live_refresh.add(refresh)
        return httpx.Response(
            200,
            json={
                "access_token": access,
                "refresh_token": refresh,
                "expires_in": 30 * 3600,
                "user_id": self.user_id,
                "token_type": "Bearer",
                "client_id": "oauth2client_00009Test",
            },
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        if self.down:
            return httpx.Response(503)
        if path == "/oauth2/token":
            form = parse_qs(request.content.decode())
            grant = form.get("grant_type", [""])[0]
            if grant == "authorization_code" and form.get("code") == ["good-code"]:
                return self._grant()
            if grant == "refresh_token":
                token = form.get("refresh_token", [""])[0]
                self.refreshed_with.append(token)
                if self.refuse_refresh or token not in self.live_refresh:
                    return httpx.Response(400, json={"code": "bad_request.invalid_grant"})
                self.live_refresh.discard(token)  # rotation: the old one is spent
                return self._grant()
            return httpx.Response(400, json={"code": "bad_request"})

        bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if bearer not in self.live_access:
            return httpx.Response(401)
        if not self.approved:
            return httpx.Response(403, json={"code": "forbidden.insufficient_permissions"})
        query = parse_qs(urlsplit(str(request.url)).query)
        if path == "/accounts":
            return httpx.Response(200, json={"accounts": self.accounts})
        if path == "/transactions":
            listed = self.transactions.get(query["account_id"][0], [])
            since = query["since"][0]
            self.since_asked.append(since)
            if since.startswith("tx_"):
                ids = [transaction["id"] for transaction in listed]
                page = listed[ids.index(since) + 1 :]
            else:
                page = [t for t in listed if t["created"] >= since]
            return httpx.Response(200, json={"transactions": page[: int(query["limit"][0])]})
        if path.startswith("/transactions/"):
            found = self.find(path.removeprefix("/transactions/"))
            if found is None:
                return httpx.Response(404)
            return httpx.Response(200, json={"transaction": found})
        if path == "/webhooks" and request.method == "GET":
            account = query["account_id"][0]
            return httpx.Response(
                200, json={"webhooks": [h for h in self.webhooks if h["account_id"] == account]}
            )
        if path == "/webhooks" and request.method == "POST":
            form = parse_qs(request.content.decode())
            hook = {"id": "webhook_x", "account_id": form["account_id"][0], "url": form["url"][0]}
            self.webhooks.append(hook)
            return httpx.Response(200, json={"webhook": hook})
        return httpx.Response(404)


class Clock:
    def __init__(self) -> None:
        self.at = NOW

    def __call__(self) -> datetime:
        return self.at


# ── Committed worlds, cleaned up afterwards ────────────────────────────────────


@dataclass
class World:
    sessions: async_sessionmaker[AsyncSession]
    leagues: list[uuid.UUID] = field(default_factory=list)
    profiles: list[uuid.UUID] = field(default_factory=list)


@pytest_asyncio.fixture
async def world(db_engine: AsyncEngine) -> AsyncIterator[World]:
    created = World(async_sessionmaker(bind=db_engine, expire_on_commit=False))
    try:
        yield created
    finally:
        async with created.sessions() as db:
            await db.execute(delete(MonzoConnection))
            if created.leagues:
                await db.execute(
                    delete(LedgerEntry).where(LedgerEntry.league_id.in_(created.leagues))
                )
                await db.execute(
                    delete(PayerMapping).where(PayerMapping.league_id.in_(created.leagues))
                )
                await db.execute(delete(MonzoPot).where(MonzoPot.league_id.in_(created.leagues)))
                await db.execute(
                    delete(LeagueMembership).where(LeagueMembership.league_id.in_(created.leagues))
                )
                await db.execute(delete(AuditLog).where(AuditLog.target_id.in_(created.leagues)))
                await db.execute(delete(League).where(League.id.in_(created.leagues)))
            if created.profiles:
                await db.execute(delete(Profile).where(Profile.id.in_(created.profiles)))
            await db.commit()


@dataclass
class Setup:
    world: World
    fake: FakeMonzo
    clock: Clock
    reader: PaymentsReader
    league: League
    members: list[Profile]
    admin: Profile


async def _profile(world: World, name: str, role: UserRole = UserRole.player) -> Profile:
    async with world.sessions() as db:
        profile = Profile(
            display_name=f"{name}-{uuid.uuid4().hex[:8]}", pin_hash=hash_pin(PIN), role=role
        )
        db.add(profile)
        await db.commit()
    world.profiles.append(profile.id)
    return profile


async def _league(world: World, members: list[Profile], link: str | None) -> League:
    tag = uuid.uuid4().hex[:8]
    async with world.sessions() as db:
        league = League(
            slug=f"monzo-{tag}",
            name=f"Monzo {tag}",
            created_by=members[0].id,
            privacy=LeaguePrivacy.private,
            entry_fee_pence=FEE,
            payment_link_url="https://pay.example/weekly-coupon",
            monzo_link_id=link,
        )
        db.add(league)
        await db.flush()
        for index, member in enumerate(members):
            db.add(
                LeagueMembership(
                    league_id=league.id,
                    player_id=member.id,
                    role=LeagueMemberRole.admin if index == 0 else LeagueMemberRole.player,
                )
            )
        await db.commit()
    world.leagues.append(league.id)
    return league


@pytest_asyncio.fixture
async def setup(world: World) -> Setup:
    fake, clock = FakeMonzo(), Clock()
    reader = PaymentsReader(
        _settings(), world.sessions, MonzoClient(httpx.MockTransport(fake)), now=clock
    )
    members = [await _profile(world, "runner"), await _profile(world, "jamie")]
    admin = await _profile(world, "site-admin", UserRole.admin)
    league = await _league(world, members, _link())
    return Setup(world, fake, clock, reader, league, members, admin)


async def _connect(s: Setup, *, approve: bool = True) -> None:
    """The owner's connect: browser, then (optionally) the Monzo app, then one catch-up."""
    state = parse_qs(urlsplit(await s.reader.start_connect()).query)["state"][0]
    assert await s.reader.finish_connect("good-code", state) == ConnectOutcome.awaiting_approval
    s.fake.approved = approve
    await s.reader.catch_up()


async def _entries(s: Setup) -> list[LedgerEntry]:
    async with s.world.sessions() as db:
        return list(
            (
                await db.scalars(
                    select(LedgerEntry)
                    .where(LedgerEntry.league_id == s.league.id)
                    .order_by(LedgerEntry.occurred_at)
                )
            ).all()
        )


async def _connection(s: Setup) -> MonzoConnection:
    async with s.world.sessions() as db:
        connection = (await db.execute(select(MonzoConnection))).scalar_one()
        return connection


async def _map(s: Setup, member: Profile, **key: str) -> None:
    async with s.world.sessions() as db:
        db.add(PayerMapping(league_id=s.league.id, player_id=member.id, **key))
        await db.commit()


@pytest.fixture
def live_loggers() -> Iterator[None]:
    """Switch back on the loggers an in-process migration switched off, then restore them.

    ``migrations/env.py`` calls ``fileConfig``, which disables every logger that already
    exists; ``test_migration_012`` and ``test_migration_014`` run it in-process and sort
    before this module. Without this, a log assertion here could pass on an empty log.
    """
    names = ("payments", "payments.app", "payments.reader", "uvicorn.access")
    loggers = [logging.getLogger(name) for name in names]
    before = [logger.disabled for logger in loggers]
    for logger in loggers:
        logger.disabled = False
    try:
        yield
    finally:
        for logger, was_disabled in zip(loggers, before, strict=True):
            logger.disabled = was_disabled


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


# ── Reading a transaction (no database) ────────────────────────────────────────


def test_an_app_payment_through_a_link_is_read_with_its_stable_payer_id() -> None:
    link = _link()
    payment = link_payment(app_payment("tx_00009A", link))
    assert payment is not None
    assert (payment.transaction_id, payment.link_id, payment.amount_pence) == (
        "tx_00009A",
        link,
        FEE,
    )
    assert (payment.payer_user_id, payment.payer_name) == ("user_00009Jamie", "Jamie Smith")
    assert payment.occurred_at == NOW + timedelta(minutes=1)


def test_a_card_payment_keeps_the_name_and_drops_the_anonymous_id() -> None:
    payment = link_payment(card_payment("tx_00009B", _link(), name="  J. Smith "))
    assert payment is not None
    assert (payment.payer_user_id, payment.payer_name) == (None, "J. Smith")


def test_the_link_id_is_found_on_the_transaction_itself_too() -> None:
    link = _link()
    transaction = app_payment("tx_00009C", link)
    del transaction["metadata"]["universal_payment_link_id"]
    transaction["universal_payment_link_id"] = link
    payment = link_payment(transaction)
    assert payment is not None and payment.link_id == link


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"decline_reason": "INSUFFICIENT_FUNDS"}, "declined"),
        ({"amount": -100}, "money out"),
        ({"amount": 0}, "nothing moved"),
        ({"currency": "EUR"}, "not sterling"),
        ({"metadata": {"p2p_initiator": "collection-pot"}}, "no payment link"),
        ({"metadata": {"universal_payment_link_id": "pot_123"}}, "not a link id"),
        ({"id": "not-a-transaction"}, "not a transaction id"),
        ({"created": "2026-10-16T12:01:00"}, "no time zone"),
        ({"created": None}, "no time"),
    ],
)
def test_anything_but_money_in_through_a_link_is_not_a_payment(
    change: dict[str, Any], why: str
) -> None:
    transaction = {**app_payment("tx_00009D", _link()), **change}
    assert link_payment(transaction) is None, why


# ── What the service may call ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", "/pots/pot_1/deposit"),
        ("PUT", "/pots/pot_1/withdraw"),
        ("POST", "/feed"),
        ("PATCH", "/transactions/tx_1"),
        ("PUT", "/transaction-receipts"),
        ("POST", "/attachment/register"),
        ("DELETE", "/webhooks/webhook_1"),
        ("GET", "/pots"),
    ],
)
async def test_a_call_outside_the_allow_list_is_refused_before_it_is_sent(
    method: str, path: str
) -> None:
    sent: list[httpx.Request] = []
    client = MonzoClient(
        httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(200))
    )
    with pytest.raises(MonzoCallRefused):
        await client._call(method, path, access_token="access-1")
    assert sent == []


def test_the_allow_list_reaches_no_money_feed_or_annotation_endpoint() -> None:
    reachable = {(method, pattern.pattern) for method, pattern in ALLOWED_CALLS}
    assert reachable == {
        ("POST", "/oauth2/token"),
        ("GET", "/accounts"),
        ("GET", "/transactions"),
        ("GET", "/transactions/tx_[A-Za-z0-9]+"),
        ("GET", "/webhooks"),
        ("POST", "/webhooks"),
    }


# ── Settings and the key ──────────────────────────────────────────────────────


def test_tokens_are_sealed_under_the_key_and_open_under_no_other() -> None:
    cipher = TokenCipher(Fernet.generate_key().decode())
    sealed = cipher.seal("access-token-marker")
    assert "access-token-marker" not in sealed
    assert cipher.open(sealed) == "access-token-marker"
    with pytest.raises(TokenUnreadable):
        TokenCipher(Fernet.generate_key().decode()).open(sealed)


def test_a_malformed_key_is_refused_without_repeating_it() -> None:
    with pytest.raises(TokenCipherUnavailable) as refused:
        TokenCipher("not-a-key-marker")
    assert "not-a-key-marker" not in str(refused.value)


def test_the_settings_need_all_four_secrets_and_a_long_url_safe_path_secret() -> None:
    environ = {
        "MONZO_CLIENT_ID": "oauth2client_1",
        "MONZO_CLIENT_SECRET": "s",
        "MONZO_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "MONZO_WEBHOOK_PATH_SECRET": PATH_SECRET,
    }
    settings = monzo_settings(environ)
    assert settings is not None and settings.webhook_url.endswith(f"/monzo/webhook/{PATH_SECRET}")
    for name in environ:
        assert monzo_settings({**environ, name: " "}) is None, name
    assert monzo_settings({**environ, "MONZO_WEBHOOK_PATH_SECRET": "short"}) is None
    assert monzo_settings({**environ, "MONZO_WEBHOOK_PATH_SECRET": "a/b" * 20}) is None


def _good_environ() -> dict[str, str]:
    return {
        "MONZO_CLIENT_ID": "oauth2client_1",
        "MONZO_CLIENT_SECRET": "s",
        "MONZO_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "MONZO_WEBHOOK_PATH_SECRET": PATH_SECRET,
    }


@pytest.mark.parametrize(
    ("name", "value", "problem"),
    [
        ("MONZO_CLIENT_ID", None, "MONZO_CLIENT_ID is not set"),
        ("MONZO_CLIENT_SECRET", "   ", "MONZO_CLIENT_SECRET is empty"),
        (
            "MONZO_TOKEN_ENCRYPTION_KEY",
            '"quoted-key-marker"',
            "MONZO_TOKEN_ENCRYPTION_KEY is wrapped in quotes",
        ),
        (
            "MONZO_WEBHOOK_PATH_SECRET",
            "plus+slash/marker-" * 3,
            "MONZO_WEBHOOK_PATH_SECRET has characters other than letters, digits, "
            "'-', '_' and '='",
        ),
        (
            "MONZO_WEBHOOK_PATH_SECRET",
            "short-marker",
            "MONZO_WEBHOOK_PATH_SECRET is shorter than 32 characters",
        ),
    ],
)
def test_a_refused_setting_is_named_and_its_value_never_repeated(
    name: str, value: str | None, problem: str
) -> None:
    environ = _good_environ()
    assert monzo_settings_problems(environ) == []
    if value is None:
        del environ[name]
    else:
        environ[name] = value
    problems = monzo_settings_problems(environ)
    assert problems == [problem]
    assert monzo_settings(environ) is None
    if value is not None and value.strip():
        assert value.strip() not in " ".join(problems)


def test_the_boot_log_names_the_refused_settings_and_no_value(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, live_loggers: None
) -> None:
    for name in _good_environ():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MONZO_CLIENT_ID", "oauth2client_marker")
    monkeypatch.setenv("MONZO_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("MONZO_WEBHOOK_PATH_SECRET", "short-marker")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused")
    payments_app._configured_reader.cache_clear()
    try:
        with caplog.at_level(logging.ERROR, logger="payments.app"):
            assert payments_app._configured_reader() is None
    finally:
        payments_app._configured_reader.cache_clear()
    logged = caplog.text
    assert "MONZO_CLIENT_SECRET is not set" in logged
    assert "MONZO_WEBHOOK_PATH_SECRET is shorter than 32 characters" in logged
    assert "short-marker" not in logged
    assert "oauth2client_marker" not in logged


def test_the_redirect_address_is_the_registered_one_on_the_recorded_origin() -> None:
    """The fixed contract, and the origin ``.railway/railway.ts`` records for production."""
    assert _settings().redirect_uri == (
        "https://payments-production-0aa1.up.railway.app/monzo/oauth/callback"
    )
    source = (_ROOT / ".railway" / "railway.ts").read_text()
    start = source.index("export const PAYMENTS_ORIGINS = ") + len(
        "export const PAYMENTS_ORIGINS = "
    )
    origins = json.loads(source[start : source.index(" as const;", start)])
    assert origins["the-coupon-production"] == PRODUCTION_ORIGIN


def test_log_lines_never_carry_a_monzo_secret(
    capsys: pytest.CaptureFixture[str], live_loggers: None
) -> None:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    key = Fernet.generate_key().decode()
    try:
        configure_payments_logging(
            {
                "MONZO_CLIENT_ID": "oauth2client_1",
                "MONZO_CLIENT_SECRET": CLIENT_SECRET,
                "MONZO_TOKEN_ENCRYPTION_KEY": key,
                "MONZO_WEBHOOK_PATH_SECRET": PATH_SECRET,
                "LOG_LEVEL": "INFO",
            }
        )
        logging.getLogger("uvicorn.access").info(f'"POST /monzo/webhook/{PATH_SECRET}" 200')
        logging.getLogger("payments").info(f"client {CLIENT_SECRET} key {key}")
    finally:
        root.handlers, root.level = saved_handlers, saved_level
    printed = capsys.readouterr().out
    assert "/monzo/webhook/<redacted>" in printed
    assert "client <redacted> key <redacted>" in printed
    for secret in (PATH_SECRET, CLIENT_SECRET, key):
        assert secret not in printed


def test_the_service_writes_no_access_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monzo's callback carries a one-time code in its query string; no line may print it."""
    started: dict[str, Any] = {}

    async def agreed() -> str:
        return "029"

    monkeypatch.setattr(payments_main, "verify", agreed)
    monkeypatch.setattr(payments_main, "configure_payments_logging", lambda: None)
    monkeypatch.setattr(
        payments_main.uvicorn, "run", lambda *_args, **kwargs: started.update(kwargs)
    )
    assert payments_main.main() == 0
    assert started["access_log"] is False
    assert started["log_config"] is None


def test_the_payments_service_never_loads_the_api_settings_even_indirectly() -> None:
    probe = (
        "import sys, src.payments_service.app, src.payments_service.__main__;"
        "print(sorted(m for m in ('src.config', 'src.database', 'src.main') if m in sys.modules))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=_API,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"


# ── Connecting ────────────────────────────────────────────────────────────────


async def test_a_connect_sends_the_registered_redirect_and_waits_for_the_app(
    setup: Setup,
) -> None:
    target = urlsplit(await setup.reader.start_connect())
    query = parse_qs(target.query)
    assert f"{target.scheme}://{target.netloc}{target.path}" == "https://auth.monzo.com/"
    assert query["client_id"] == ["oauth2client_00009Test"]
    assert query["redirect_uri"] == [
        "https://payments-production-0aa1.up.railway.app/monzo/oauth/callback"
    ]
    assert query["response_type"] == ["code"]
    state = query["state"][0]

    assert await setup.reader.finish_connect("good-code", state) == (
        ConnectOutcome.awaiting_approval
    )
    connection = await _connection(setup)
    assert connection.status == MonzoLinkStatus.awaiting_approval
    assert connection.monzo_user_id == OWNER
    assert connection.counting_since == NOW
    # Not approved in the app yet: Monzo withholds account data, and that is not an error.
    assert (await setup.reader.catch_up()).outcome == ReadOutcome.awaiting_approval
    assert (await _connection(setup)).last_error is None

    setup.fake.approved = True
    assert (await setup.reader.catch_up()).outcome == ReadOutcome.read
    connection = await _connection(setup)
    assert connection.status == MonzoLinkStatus.connected
    # Its own webhook, on every open account, registered once.
    assert setup.fake.webhooks == [
        {
            "id": "webhook_x",
            "account_id": "acc_00009Main",
            "url": f"{PRODUCTION_ORIGIN}/monzo/webhook/{PATH_SECRET}",
        }
    ]
    await setup.reader.catch_up()
    assert ("POST", "/webhooks") in setup.fake.calls
    assert setup.fake.calls.count(("POST", "/webhooks")) == 1


async def test_tokens_are_stored_encrypted(setup: Setup) -> None:
    await _connect(setup)
    connection = await _connection(setup)
    assert connection.access_token_encrypted and connection.refresh_token_encrypted
    assert "access-1" not in connection.access_token_encrypted
    assert "refresh-1" not in connection.refresh_token_encrypted
    cipher = TokenCipher(setup.reader.settings.encryption_key)
    assert cipher.open(connection.access_token_encrypted) == "access-1"
    assert cipher.open(connection.refresh_token_encrypted) == "refresh-1"


async def test_a_used_expired_or_unknown_state_is_refused(setup: Setup) -> None:
    assert await setup.reader.finish_connect("good-code", "never-issued") == (
        ConnectOutcome.bad_state
    )
    state = parse_qs(urlsplit(await setup.reader.start_connect()).query)["state"][0]
    assert await setup.reader.finish_connect("good-code", state) == (
        ConnectOutcome.awaiting_approval
    )
    assert await setup.reader.finish_connect("good-code", state) == ConnectOutcome.bad_state

    late = parse_qs(urlsplit(await setup.reader.start_connect()).query)["state"][0]
    setup.clock.at = NOW + timedelta(minutes=11)
    assert await setup.reader.finish_connect("good-code", late) == ConnectOutcome.bad_state
    assert ("POST", "/oauth2/token") in setup.fake.calls
    assert setup.fake.calls.count(("POST", "/oauth2/token")) == 1


async def test_another_monzo_account_cannot_replace_the_owners(setup: Setup) -> None:
    await _connect(setup)
    setup.fake.user_id = "user_00009Stranger"
    state = parse_qs(urlsplit(await setup.reader.start_connect()).query)["state"][0]
    assert await setup.reader.finish_connect("good-code", state) == ConnectOutcome.other_user
    connection = await _connection(setup)
    assert (connection.monzo_user_id, connection.status) == (OWNER, MonzoLinkStatus.connected)
    cipher = TokenCipher(setup.reader.settings.encryption_key)
    assert connection.access_token_encrypted is not None
    assert cipher.open(connection.access_token_encrypted) == "access-1"


async def test_the_connect_pages_echo_nothing_from_the_request(setup: Setup) -> None:
    payments_app.app.dependency_overrides[payments_app.get_reader] = lambda: setup.reader
    try:
        async with AsyncClient(
            transport=ASGITransport(app=payments_app.app), base_url="http://test"
        ) as client:
            start = await client.get("/monzo/oauth/start")
            assert start.status_code == 302
            assert start.headers["location"].startswith("https://auth.monzo.com/?")
            refused = await client.get(
                "/monzo/oauth/callback", params={"code": "<b>x</b>", "state": "<script>"}
            )
            assert refused.status_code == 400
            assert "<script>" not in refused.text and "<b>x</b>" not in refused.text
            state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
            done = await client.get(
                "/monzo/oauth/callback", params={"code": "good-code", "state": state}
            )
            assert done.status_code == 200
            assert "approve in the Monzo app" in done.text
            assert done.headers["cache-control"] == "no-store"
    finally:
        payments_app.app.dependency_overrides.pop(payments_app.get_reader, None)


async def test_without_its_settings_the_service_says_so_and_reads_nothing() -> None:
    payments_app.app.dependency_overrides[payments_app.get_reader] = lambda: None
    try:
        async with AsyncClient(
            transport=ASGITransport(app=payments_app.app), base_url="http://test"
        ) as client:
            assert (await client.get("/monzo/oauth/start")).status_code == 503
            webhook = await client.post(f"/monzo/webhook/{PATH_SECRET}", json={})
            assert webhook.status_code == 404
            assert (await client.get("/health")).status_code == 200
    finally:
        payments_app.app.dependency_overrides.pop(payments_app.get_reader, None)


# ── Reading: the link filter and both payer kinds ─────────────────────────────


async def test_only_payments_through_the_leagues_own_link_count(setup: Setup) -> None:
    await _connect(setup)
    link = setup.league.monzo_link_id
    assert link is not None
    setup.fake.add(app_payment("tx_00009Ours", link))
    setup.fake.add(app_payment("tx_00009Other", _link()))
    setup.fake.add({**app_payment("tx_00009Dinner", link), "metadata": {}})
    setup.fake.add(app_payment("tx_00009Closed", link), account="acc_00009Closed")
    setup.clock.at = NOW + timedelta(minutes=5)

    await setup.reader.catch_up()
    assert [entry.monzo_transaction_id for entry in await _entries(setup)] == ["tx_00009Ours"]


async def test_an_app_payer_is_matched_by_their_monzo_user_id(setup: Setup) -> None:
    await _connect(setup)
    jamie = setup.members[1]
    await _map(setup, jamie, monzo_user_id="user_00009Jamie")
    assert setup.league.monzo_link_id is not None
    setup.fake.add(app_payment("tx_00009App", setup.league.monzo_link_id, name="Someone Else"))
    setup.clock.at = NOW + timedelta(minutes=5)

    await setup.reader.catch_up()
    (entry,) = await _entries(setup)
    assert (entry.kind, entry.player_id, entry.amount_pence) == (
        LedgerKind.payment,
        jamie.id,
        FEE,
    )
    assert entry.payer_monzo_user_id == "user_00009Jamie"
    assert entry.occurred_at == NOW + timedelta(minutes=1)
    assert entry.created_by is None


async def test_a_card_payer_is_matched_by_their_normalised_name(setup: Setup) -> None:
    await _connect(setup)
    jamie = setup.members[1]
    await _map(setup, jamie, normalised_name="j smith")
    assert setup.league.monzo_link_id is not None
    setup.fake.add(card_payment("tx_00009Card1", setup.league.monzo_link_id, name="J. SMITH"))
    setup.fake.add(card_payment("tx_00009Card2", setup.league.monzo_link_id, name="j smith"))
    setup.clock.at = NOW + timedelta(minutes=5)

    await setup.reader.catch_up()
    entries = await _entries(setup)
    assert [(entry.player_id, entry.payer_monzo_user_id) for entry in entries] == [
        (jamie.id, None),
        (jamie.id, None),
    ]


async def test_an_unknown_payer_is_queued_for_the_organiser(setup: Setup) -> None:
    await _connect(setup)
    link = setup.league.monzo_link_id
    assert link is not None
    setup.fake.add(app_payment("tx_00009NewApp", link, user="user_00009New", name="New Person"))
    setup.fake.add(card_payment("tx_00009NewCard", link, name="Card Person"))
    setup.clock.at = NOW + timedelta(minutes=5)

    await setup.reader.catch_up()
    queued = {
        entry.monzo_transaction_id: (entry.player_id, entry.payer_monzo_user_id, entry.payer_name)
        for entry in await _entries(setup)
    }
    assert queued == {
        "tx_00009NewApp": (None, "user_00009New", "New Person"),
        "tx_00009NewCard": (None, None, "Card Person"),
    }

    # The organiser's queue on the API is where they surface.
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as api:
        overview = await api.get(
            f"/api/v1/leagues/{setup.league.slug}/payments", headers=_auth(setup.admin)
        )
    assert overview.status_code == 200, overview.text
    assert {row["payer_name"] for row in overview.json()["queued_payments"]} == {
        "New Person",
        "Card Person",
    }


async def test_a_mapped_payer_who_never_joined_this_league_is_queued(setup: Setup) -> None:
    await _connect(setup)
    outsider = await _profile(setup.world, "outsider")
    await _map(setup, outsider, monzo_user_id="user_00009Outsider")
    assert setup.league.monzo_link_id is not None
    setup.fake.add(
        app_payment("tx_00009Out", setup.league.monzo_link_id, user="user_00009Outsider")
    )
    setup.clock.at = NOW + timedelta(minutes=5)

    await setup.reader.catch_up()
    (entry,) = await _entries(setup)
    assert entry.player_id is None


async def test_payments_made_before_the_connection_are_left_to_opening_balances(
    setup: Setup,
) -> None:
    assert setup.league.monzo_link_id is not None
    setup.fake.add(
        app_payment(
            "tx_00009Before", setup.league.monzo_link_id, created=NOW - timedelta(minutes=1)
        )
    )
    await _connect(setup)
    setup.fake.add(app_payment("tx_00009After", setup.league.monzo_link_id))
    setup.clock.at = NOW + timedelta(minutes=5)
    # Even when Monzo returns it (a webhook names it), the earlier one is not counted.
    await setup.reader.nudge("tx_00009Before")
    await setup.reader.catch_up()
    assert [entry.monzo_transaction_id for entry in await _entries(setup)] == ["tx_00009After"]


async def test_nothing_is_read_until_a_league_has_a_link_id_and_then_the_gap_is(
    setup: Setup,
) -> None:
    link = setup.league.monzo_link_id
    assert link is not None
    async with setup.world.sessions() as db:
        league = await db.get(League, setup.league.id)
        assert league is not None
        league.monzo_link_id = None
        await db.commit()
    await _connect(setup)
    setup.fake.add(app_payment("tx_00009Gap", link))
    setup.clock.at = NOW + timedelta(minutes=5)
    await setup.reader.catch_up()
    assert ("GET", "/transactions") not in setup.fake.calls
    assert await _entries(setup) == []

    async with setup.world.sessions() as db:
        league = await db.get(League, setup.league.id)
        assert league is not None
        league.monzo_link_id = link
        await db.commit()
    setup.clock.at = NOW + timedelta(minutes=10)
    await setup.reader.catch_up()
    assert [entry.monzo_transaction_id for entry in await _entries(setup)] == ["tx_00009Gap"]


# ── Deduplication and the webhook ─────────────────────────────────────────────


async def _webhook(setup: Setup, body: Any, secret: str = PATH_SECRET) -> httpx.Response:
    payments_app.app.dependency_overrides[payments_app.get_reader] = lambda: setup.reader
    try:
        async with AsyncClient(
            transport=ASGITransport(app=payments_app.app), base_url="http://test"
        ) as client:
            return await client.post(f"/monzo/webhook/{secret}", json=body)
    finally:
        payments_app.app.dependency_overrides.pop(payments_app.get_reader, None)


async def test_created_updated_and_catch_up_write_one_entry(setup: Setup) -> None:
    await _connect(setup)
    assert setup.league.monzo_link_id is not None
    transaction = app_payment("tx_00009Once", setup.league.monzo_link_id)
    setup.fake.add(transaction)
    for event in ("transaction.created", "transaction.updated", "transaction.updated"):
        answered = await _webhook(setup, {"type": event, "data": transaction})
        assert answered.status_code == 200
    setup.clock.at = NOW + timedelta(minutes=5)
    await setup.reader.catch_up()
    setup.clock.at = NOW + timedelta(minutes=10)
    await setup.reader.catch_up()

    (entry,) = await _entries(setup)
    assert entry.monzo_transaction_id == "tx_00009Once"


async def test_the_webhook_body_is_never_believed_only_re_read(setup: Setup) -> None:
    await _connect(setup)
    link = setup.league.monzo_link_id
    assert link is not None
    setup.fake.add(app_payment("tx_00009Real", link, amount=FEE))
    forged = app_payment("tx_00009Real", link, amount=99_999, user="user_00009Forger")
    assert (
        await _webhook(setup, {"type": "transaction.created", "data": forged})
    ).status_code == 200
    (entry,) = await _entries(setup)
    assert (entry.amount_pence, entry.payer_monzo_user_id) == (FEE, "user_00009Jamie")

    # A body describing a link payment Monzo does not have writes nothing.
    invented = app_payment("tx_00009Invented", link)
    assert (
        await _webhook(setup, {"type": "transaction.created", "data": invented})
    ).status_code == 200
    # And one Monzo says is not a link payment at all writes nothing either.
    setup.fake.add({**app_payment("tx_00009NotLink", link), "metadata": {}})
    claims = app_payment("tx_00009NotLink", link)
    assert (
        await _webhook(setup, {"type": "transaction.created", "data": claims})
    ).status_code == 200
    assert [e.monzo_transaction_id for e in await _entries(setup)] == ["tx_00009Real"]
    assert ("GET", "/transactions/tx_00009Invented") in setup.fake.calls


async def test_a_wrong_webhook_secret_is_not_found_and_reads_nothing(setup: Setup) -> None:
    await _connect(setup)
    assert setup.league.monzo_link_id is not None
    setup.fake.add(app_payment("tx_00009Secret", setup.league.monzo_link_id))
    calls_before = len(setup.fake.calls)
    body = {"type": "transaction.created", "data": {"id": "tx_00009Secret"}}
    for secret in ("wrong" + PATH_SECRET[5:], PATH_SECRET[:-1]):
        assert (await _webhook(setup, body, secret)).status_code == 404
    # Malformed or foreign events are answered, and ignored.
    for ignored in ({"type": "account.updated", "data": {"id": "tx_00009Secret"}}, ["x"], {}):
        assert (await _webhook(setup, ignored)).status_code == 200
    assert len(setup.fake.calls) == calls_before
    assert await _entries(setup) == []


# ── The token: refresh with rotation ──────────────────────────────────────────


async def test_an_expiring_token_is_refreshed_and_the_refresh_token_rotated(
    setup: Setup,
) -> None:
    await _connect(setup)
    cipher = TokenCipher(setup.reader.settings.encryption_key)

    setup.clock.at = NOW + timedelta(hours=29, minutes=55)  # inside the ten-minute margin
    assert (await setup.reader.catch_up()).outcome == ReadOutcome.read
    connection = await _connection(setup)
    assert connection.refresh_token_encrypted and connection.access_token_encrypted
    assert cipher.open(connection.refresh_token_encrypted) == "refresh-2"
    assert cipher.open(connection.access_token_encrypted) == "access-2"
    assert connection.access_expires_at == setup.clock.at + timedelta(hours=30)

    # The next refresh spends the new refresh token; the old one is never used again.
    setup.clock.at = NOW + timedelta(hours=59, minutes=55)
    assert (await setup.reader.catch_up()).outcome == ReadOutcome.read
    assert setup.fake.refreshed_with == ["refresh-1", "refresh-2"]
    assert "refresh-1" not in setup.fake.live_refresh


async def test_a_refused_refresh_asks_for_a_reconnect_and_stops_reading(setup: Setup) -> None:
    await _connect(setup)
    setup.fake.refuse_refresh = True
    setup.clock.at = NOW + timedelta(hours=30)
    assert (await setup.reader.catch_up()).outcome == ReadOutcome.failed
    connection = await _connection(setup)
    assert connection.status == MonzoLinkStatus.needs_reconnect
    assert connection.access_token_encrypted is None
    assert connection.refresh_token_encrypted is None
    assert connection.last_error == "refresh_refused"
    calls = len(setup.fake.calls)
    assert (await setup.reader.catch_up()).outcome == ReadOutcome.idle
    assert len(setup.fake.calls) == calls


# ── An outage ─────────────────────────────────────────────────────────────────


async def test_a_monzo_outage_is_recorded_and_manual_entry_still_works(setup: Setup) -> None:
    await _connect(setup)
    assert setup.league.monzo_link_id is not None
    setup.fake.add(app_payment("tx_00009Late", setup.league.monzo_link_id))
    setup.fake.down = True
    setup.clock.at = NOW + timedelta(minutes=5)

    assert (await setup.reader.catch_up()).outcome == ReadOutcome.failed
    assert (
        await _webhook(setup, {"type": "transaction.created", "data": {"id": "tx_00009Late"}})
    ).status_code == 200
    connection = await _connection(setup)
    assert (connection.last_error, connection.last_error_at) == (
        "monzo_unavailable",
        NOW + timedelta(minutes=5),
    )
    assert await _entries(setup) == []

    # The organiser records cash on the API, which never depends on Monzo.
    jamie = setup.members[1]
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as api:
        cash = await api.post(
            f"/api/v1/leagues/{setup.league.slug}/payments/cash",
            json={"player_id": str(jamie.id), "amount_pence": FEE},
            headers=_auth(setup.admin),
        )
    assert cash.status_code == 201, cash.text

    # Monzo back: the next catch-up reads from the last complete read, so nothing is lost.
    setup.fake.down = False
    setup.clock.at = NOW + timedelta(minutes=10)
    assert (await setup.reader.catch_up()).outcome == ReadOutcome.read
    assert {entry.monzo_transaction_id for entry in await _entries(setup)} == {
        None,
        "tx_00009Late",
    }


async def test_no_transaction_body_reaches_the_log(
    setup: Setup, caplog: pytest.LogCaptureFixture, live_loggers: None
) -> None:
    await _connect(setup)
    assert setup.league.monzo_link_id is not None
    setup.fake.add(card_payment("tx_00009Quiet", setup.league.monzo_link_id, name="Quiet Payer"))
    setup.clock.at = NOW + timedelta(minutes=5)
    with caplog.at_level(logging.DEBUG):
        await setup.reader.catch_up()
        setup.fake.down = True
        setup.clock.at = NOW + timedelta(minutes=10)
        await setup.reader.catch_up()
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "queued=1" in logged
    for marker in ("Quiet Payer", "DESCRIPTION-MARKER", "MESSAGE-MARKER", "anonuser_", "access-"):
        assert marker not in logged


# ── The API: the link id, and link health for the organiser ───────────────────


async def test_only_a_site_admin_sets_the_monzo_link_id_and_it_is_audited(
    setup: Setup,
) -> None:
    runner = setup.members[0]
    league = await _league(setup.world, [runner], None)
    link = _link()
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as api:
        refused = await api.patch(
            f"/api/v1/leagues/{league.slug}", json={"monzo_link_id": link}, headers=_auth(runner)
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["detail"] == "SITE_ADMIN_REQUIRED"

        for bad in ("pot_0000", "unipaylink_has space", "unipaylink_", "x" * 65):
            malformed = await api.patch(
                f"/api/v1/leagues/{league.slug}",
                json={"monzo_link_id": bad},
                headers=_auth(setup.admin),
            )
            assert malformed.status_code == 422, (bad, malformed.text)

        taken = await api.patch(
            f"/api/v1/leagues/{league.slug}",
            json={"monzo_link_id": setup.league.monzo_link_id},
            headers=_auth(setup.admin),
        )
        assert taken.status_code == 409, taken.text
        assert taken.json()["detail"] == "MONZO_LINK_IN_USE"

        accepted = await api.patch(
            f"/api/v1/leagues/{league.slug}",
            json={"monzo_link_id": link},
            headers=_auth(setup.admin),
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["monzo_link_id"] == link

        # A league admin does not see it; a site admin does.
        hidden = await api.get(f"/api/v1/leagues/{league.slug}", headers=_auth(runner))
        assert hidden.json()["monzo_link_id"] is None
        shown = await api.get(f"/api/v1/leagues/{league.slug}", headers=_auth(setup.admin))
        assert shown.json()["monzo_link_id"] == link

    async with setup.world.sessions() as db:
        audits = (
            await db.scalars(
                select(AuditLog).where(
                    AuditLog.target_id == league.id,
                    AuditLog.action_type == ActionType.league_updated,
                )
            )
        ).all()
    assert [audit.changes for audit in audits] == [{"monzo_link_id": {"from": None, "to": link}}]


async def test_the_organisers_screen_reports_link_health_and_never_a_token(
    setup: Setup,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as api:
        before = await api.get(
            f"/api/v1/leagues/{setup.league.slug}/payments", headers=_auth(setup.admin)
        )
        assert before.status_code == 200, before.text
        assert before.json()["monzo_link"] is None
        assert before.json()["monzo_link_id"] == setup.league.monzo_link_id

        await _connect(setup)
        setup.fake.down = True
        setup.clock.at = NOW + timedelta(minutes=5)
        await setup.reader.catch_up()

        after = await api.get(
            f"/api/v1/leagues/{setup.league.slug}/payments", headers=_auth(setup.admin)
        )
    health = after.json()["monzo_link"]
    assert health == {
        "status": "connected",
        "last_success_at": "2026-10-16T12:00:00Z",
        "last_error": "monzo_unavailable",
        "last_error_at": "2026-10-16T12:05:00Z",
        "token_expires_at": "2026-10-17T18:00:00Z",
        "counting_since": "2026-10-16T12:00:00Z",
        "webhook_registered": True,
        "approval_lapses_at": "2027-01-14T12:00:00Z",
    }
    assert not re.search(r"access-|refresh-|gAAAA", after.text)


# ── Batch 214: the owner's own top-ups into the league's pot ──────────────────
#
# Shaped like the owner's July samples (`~/monzo-spike/out/`): a pot deposit is a
# `uk_retail_pot` debit naming the pot in `pot_id`, its ledger in `pot_account_id` and
# the mover in `user_id`. Where a link payment names its collection pot was never
# recorded, so these cases put it in each place the parser reads.

LEAGUE_POT = "collectionpot_00009League"
LINK_FIELD = "universal_payment_link_id"


def _pot_account(pot: str) -> str:
    return "acc_" + pot.split("_", 1)[1]


def paid_into(
    transaction: dict[str, Any], pot: str, field_name: str = "collection_pot_id"
) -> dict[str, Any]:
    """A link payment that names the pot Monzo filed it into, under ``field_name``."""
    return {**transaction, "metadata": {**transaction["metadata"], field_name: pot}}


def pot_deposit(
    tx_id: str,
    pot: str,
    *,
    user: str | None = OWNER,
    amount: int = FEE,
    created: datetime = NOW + timedelta(minutes=2),
) -> dict[str, Any]:
    """The owner moving money from the current account into a pot."""
    plain = tx_id.removeprefix("tx_")
    metadata: dict[str, Any] = {
        "pot_id": pot,
        "pot_account_id": _pot_account(pot),
        "pot_deposit_id": f"potdep_{plain}",
        "external_id": f"user_pot_deposit_{plain}",
        "trigger": "user",
    }
    if user is not None:
        metadata["user_id"] = user
    return {
        "id": tx_id,
        "created": _rfc3339(created),
        "amount": -amount,
        "currency": "GBP",
        "description": pot,
        "scheme": "uk_retail_pot",
        "notes": "",
        "metadata": metadata,
        "counterparty": {},
        "account_id": "acc_00009Main",
    }


def _holders(fake: FakeMonzo, name: str = "Pat Owner") -> None:
    """Give the main account one holder, the owner, as ``/accounts`` lists owners."""
    fake.accounts[0]["owners"] = [
        {"user_id": OWNER, "preferred_name": name, "preferred_first_name": name.split()[0]}
    ]


async def _pots(s: Setup) -> dict[str, uuid.UUID]:
    async with s.world.sessions() as db:
        rows = await db.execute(select(MonzoPot.pot_ref, MonzoPot.league_id))
        return {row.pot_ref: row.league_id for row in rows if row.league_id in s.world.leagues}


async def _learn_the_pot(s: Setup, *, at: datetime = NOW + timedelta(minutes=5)) -> None:
    """A member's link payment names the league's pot, and a catch-up learns it."""
    link = s.league.monzo_link_id
    assert link is not None
    s.fake.add(paid_into(app_payment(f"tx_00009Link{uuid.uuid4().hex[:6]}", link), LEAGUE_POT))
    s.clock.at = at
    await s.reader.catch_up()


def test_a_top_up_into_a_pot_is_read_as_a_payment_from_whoever_moved_it() -> None:
    top_up = pot_top_up(pot_deposit("tx_00009Top", LEAGUE_POT))
    assert top_up is not None
    assert (top_up.amount_pence, top_up.payer_user_id) == (FEE, OWNER)
    assert top_up.pot_refs == {LEAGUE_POT, _pot_account(LEAGUE_POT)}
    assert top_up.occurred_at == NOW + timedelta(minutes=2)


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"amount": FEE}, "money taken back out of the pot"),
        ({"amount": 0}, "nothing moved"),
        ({"decline_reason": "INSUFFICIENT_FUNDS"}, "declined"),
        ({"currency": "EUR"}, "not sterling"),
        ({"scheme": "mastercard"}, "not a pot transfer"),
        ({"metadata": {"trigger": "user"}, "description": "Weekly coupon"}, "names no pot"),
        ({"metadata": {"pot_id": LEAGUE_POT, LINK_FIELD: "unipaylink_00009X"}}, "a link's"),
        ({"created": "2026-10-16T12:02:00"}, "no time zone"),
        ({"id": "not-a-transaction"}, "not a transaction id"),
    ],
)
def test_anything_but_money_into_a_pot_is_not_a_top_up(change: dict[str, Any], why: str) -> None:
    assert pot_top_up({**pot_deposit("tx_00009Top", LEAGUE_POT), **change}) is None, why


@pytest.mark.parametrize(
    ("where", "found_in"),
    [
        ({"metadata": {"collection_pot_id": LEAGUE_POT}}, "metadata.collection_pot_id"),
        ({"metadata": {"pot_id": LEAGUE_POT}}, "metadata.pot_id"),
        ({"metadata": {"pot_account_id": "acc_00009Ledger"}}, "metadata.pot_account_id"),
        ({"description": LEAGUE_POT}, "description"),
    ],
)
def test_a_link_payment_names_its_pot_wherever_monzo_puts_it(
    where: dict[str, Any], found_in: str
) -> None:
    base = app_payment("tx_00009Named", _link())
    transaction = {**base, **where}
    transaction["metadata"] = {**base["metadata"], **where.get("metadata", {})}
    payment = link_payment(transaction)
    assert payment is not None
    assert [field_name for _ref, field_name in payment.pots] == [found_in]


def test_the_current_account_and_a_deposit_id_are_never_taken_for_a_pot() -> None:
    transaction = {**app_payment("tx_00009Plain", _link()), "account_id": "acc_00009Main"}
    transaction["metadata"] = {
        **transaction["metadata"],
        "pot_deposit_id": "potdep_00009X",
        "account_id": "acc_00009Main",
    }
    assert pot_ref_fields(transaction) == {}


def test_a_sole_holder_is_known_and_a_joint_account_has_none() -> None:
    holders = account_holders(
        [
            {"id": "acc_00009Main", "owners": [{"user_id": OWNER, "preferred_name": " Pat "}]},
            {
                "id": "acc_00009Joint",
                "owners": [
                    {"user_id": OWNER},
                    {"user_id": "user_00009Two", "preferred_name": "Sam"},
                ],
            },
            {"id": "acc_00009Odd", "owners": "nobody"},
        ]
    )
    assert holders.sole_holder == {"acc_00009Main": OWNER}
    assert holders.names == {OWNER: "Pat", "user_00009Two": "Sam"}


def test_the_shape_of_an_unplaced_pot_move_carries_no_value() -> None:
    transaction = {
        **pot_deposit("tx_00009Shape", "pot_00009Savings", amount=12_345),
        "notes": "MESSAGE-MARKER",
    }
    transaction["metadata"]["note"] = "NOTE-MARKER"
    shape = transaction_shape(transaction, {LEAGUE_POT})
    assert shape.startswith("scheme=uk_retail_pot sign=- description=pot_…")
    assert (
        "ids=external_id=user_…,pot_account_id=acc_…,pot_deposit_id=potdep_…,pot_id=pot_…,"
        "user_id=user_…"
    ) in shape
    assert "kinds=trigger=user" in shape
    assert "pot_fields=description,metadata.pot_account_id,metadata.pot_id" in shape
    assert shape.endswith("league_pot=no")
    for marker in ("12345", "123.45", "00009Savings", "00009Owner", "MARKER", "tx_00009Shape"):
        assert marker not in shape


async def test_a_refused_call_carries_its_status_and_only_a_real_monzo_code() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tx_00009Coded"):
            return httpx.Response(
                404,
                json={"code": "not_found.transaction_not_found", "message": "MESSAGE-MARKER"},
            )
        return httpx.Response(400, json={"code": "Bad Request <b>MARKER</b>"})

    client = MonzoClient(httpx.MockTransport(answer))
    with pytest.raises(MonzoRefused) as coded:
        await client.transaction("access", "tx_00009Coded")
    assert (coded.value.status, coded.value.monzo_code) == (404, "not_found.transaction_not_found")
    assert coded.value.code == "refused"
    with pytest.raises(MonzoRefused) as odd:
        await client.transaction("access", "tx_00009Odd")
    assert (odd.value.status, odd.value.monzo_code) == (400, None)


async def test_the_owners_first_top_up_waits_once_and_every_later_one_books_itself(
    setup: Setup,
) -> None:
    _holders(setup.fake)
    await _connect(setup)
    await _learn_the_pot(setup)
    owner_member = setup.members[0]

    setup.fake.add(pot_deposit("tx_00009Top1", LEAGUE_POT, created=NOW + timedelta(minutes=6)))
    setup.clock.at = NOW + timedelta(minutes=10)
    await setup.reader.catch_up()
    queued = [e for e in await _entries(setup) if e.monzo_transaction_id == "tx_00009Top1"]
    assert [(e.player_id, e.amount_pence, e.payer_monzo_user_id, e.payer_name) for e in queued] == [
        (None, FEE, OWNER, "Pat Owner")
    ]

    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as api:
        assigned = await api.post(
            f"/api/v1/leagues/{setup.league.slug}/payments/{queued[0].id}/assign",
            json={"player_id": str(owner_member.id)},
            headers=_auth(setup.admin),
        )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["remembered_by"] == "monzo_user"

    setup.fake.add(
        pot_deposit("tx_00009Top2", LEAGUE_POT, amount=2 * FEE, created=NOW + timedelta(minutes=11))
    )
    setup.clock.at = NOW + timedelta(minutes=15)
    await setup.reader.catch_up()
    entries = await _entries(setup)
    (later,) = (e for e in entries if e.monzo_transaction_id == "tx_00009Top2")
    assert (later.kind, later.player_id, later.amount_pence) == (
        LedgerKind.payment,
        owner_member.id,
        2 * FEE,
    )


async def test_a_top_up_counts_only_into_the_leagues_pot_and_only_once_it_is_known(
    setup: Setup,
) -> None:
    await _connect(setup)
    # Before any link payment names the pot, a top-up into it is not counted...
    setup.fake.add(pot_deposit("tx_00009Early", LEAGUE_POT, created=NOW + timedelta(minutes=1)))
    setup.clock.at = NOW + timedelta(minutes=3)
    await setup.reader.catch_up()
    assert await _entries(setup) == []
    # ...nor once it is known, because it was made before then: that week was by hand.
    await _learn_the_pot(setup, at=NOW + timedelta(minutes=5))
    later = NOW + timedelta(minutes=6)
    setup.fake.add(pot_deposit("tx_00009Savings", "pot_00009Savings", created=later))
    setup.fake.add({**pot_deposit("tx_00009Back", LEAGUE_POT, created=later), "amount": FEE})
    setup.fake.add(pot_deposit("tx_00009Counted", LEAGUE_POT, created=later))
    setup.clock.at = NOW + timedelta(minutes=10)
    await setup.reader.catch_up()

    mine = [e.monzo_transaction_id for e in await _entries(setup) if e.payer_monzo_user_id == OWNER]
    assert mine == ["tx_00009Counted"]
    assert await _pots(setup) == {LEAGUE_POT: setup.league.id}


async def test_a_new_process_learns_the_pot_from_history_once(setup: Setup) -> None:
    await _connect(setup)
    link = setup.league.monzo_link_id
    assert link is not None
    setup.fake.add(paid_into(app_payment("tx_00009Old", link), LEAGUE_POT))
    setup.clock.at = NOW + timedelta(minutes=5)
    await setup.reader.catch_up()
    setup.clock.at = NOW + timedelta(hours=3)
    await setup.reader.catch_up()
    # As the shipment finds it: the payment long recorded, no pot kept.
    async with setup.world.sessions() as db:
        await db.execute(delete(MonzoPot).where(MonzoPot.league_id == setup.league.id))
        await db.commit()

    restarted = PaymentsReader(
        setup.reader.settings,
        setup.world.sessions,
        MonzoClient(httpx.MockTransport(setup.fake)),
        now=setup.clock,
    )
    setup.clock.at = NOW + timedelta(hours=3, minutes=5)
    await restarted.catch_up()
    assert setup.fake.since_asked[-1] == _rfc3339(NOW), "read back to the counting start"
    assert await _pots(setup) == {LEAGUE_POT: setup.league.id}
    assert [e.monzo_transaction_id for e in await _entries(setup)] == ["tx_00009Old"]

    # Once per process, even while a pot is still unknown: never history every five minutes.
    async with setup.world.sessions() as db:
        await db.execute(delete(MonzoPot).where(MonzoPot.league_id == setup.league.id))
        await db.commit()
    setup.clock.at = NOW + timedelta(hours=3, minutes=10)
    await restarted.catch_up()
    assert setup.fake.since_asked[-1] == _rfc3339(NOW + timedelta(hours=2, minutes=5))


async def test_a_top_up_named_by_a_webhook_is_written_once(setup: Setup) -> None:
    _holders(setup.fake)
    await _connect(setup)
    await _learn_the_pot(setup)
    top_up = pot_deposit("tx_00009Hook", LEAGUE_POT, created=NOW + timedelta(minutes=6))
    setup.fake.add(top_up)
    setup.clock.at = NOW + timedelta(minutes=7)
    for event in ("transaction.created", "transaction.updated"):
        assert (await _webhook(setup, {"type": event, "data": top_up})).status_code == 200
    setup.clock.at = NOW + timedelta(minutes=10)
    await setup.reader.catch_up()

    hooked = [e for e in await _entries(setup) if e.monzo_transaction_id == "tx_00009Hook"]
    assert [(e.amount_pence, e.payer_name) for e in hooked] == [(FEE, "Pat Owner")]


async def test_a_refused_webhook_re_read_is_logged_for_its_reason_and_is_no_link_problem(
    setup: Setup, caplog: pytest.LogCaptureFixture, live_loggers: None
) -> None:
    await _connect(setup)
    with caplog.at_level(logging.INFO, logger="payments.reader"):
        answered = await _webhook(
            setup, {"type": "transaction.created", "data": {"id": "tx_00009Hidden"}}
        )
    assert answered.status_code == 200
    connection = await _connection(setup)
    assert (connection.last_error, connection.last_error_at) == (None, None)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "monzo webhook re-read refused: status=404 code=none" in logged


async def test_approval_is_dated_when_monzo_first_answers_and_again_on_a_reconnect(
    setup: Setup,
) -> None:
    await _connect(setup, approve=False)
    assert (await _connection(setup)).approved_at is None
    setup.fake.approved = True
    setup.clock.at = NOW + timedelta(minutes=5)
    await setup.reader.catch_up()
    assert (await _connection(setup)).approved_at == NOW + timedelta(minutes=5)

    # Connecting again, as the 90-day renewal asks, dates the new approval.
    setup.clock.at = NOW + timedelta(days=85)
    await _connect(setup)
    assert (await _connection(setup)).approved_at == NOW + timedelta(days=85)


async def test_unplaced_pot_moves_are_described_once_until_a_top_up_is_recognised(
    setup: Setup, caplog: pytest.LogCaptureFixture, live_loggers: None
) -> None:
    _holders(setup.fake)
    await _connect(setup)
    link = setup.league.monzo_link_id
    assert link is not None
    setup.fake.add(pot_deposit("tx_00009Savings1", "pot_00009Savings", amount=4_321))
    with caplog.at_level(logging.INFO, logger="payments.reader"):
        for minutes in (5, 10):
            setup.clock.at = NOW + timedelta(minutes=minutes)
            await setup.reader.catch_up()

        # The league's link payments name no pot: said once, by shape alone.
        setup.fake.add(app_payment("tx_00009NoPot1", link, created=NOW + timedelta(minutes=11)))
        setup.fake.add(app_payment("tx_00009NoPot2", link, created=NOW + timedelta(minutes=12)))
        setup.clock.at = NOW + timedelta(minutes=15)
        await setup.reader.catch_up()

        # Once a top-up is recognised, the capture stops.
        await _learn_the_pot(setup, at=NOW + timedelta(minutes=20))
        moved = NOW + timedelta(minutes=21)
        setup.fake.add(pot_deposit("tx_00009Mine", LEAGUE_POT, created=moved))
        setup.fake.add(pot_deposit("tx_00009Savings2", "pot_00009Savings", created=moved))
        setup.clock.at = NOW + timedelta(minutes=25)
        await setup.reader.catch_up()

    messages = [record.getMessage() for record in caplog.records]
    described = [m for m in messages if m.startswith("monzo pot move not placed: ")]
    assert len(described) == 1
    assert "scheme=uk_retail_pot sign=-" in described[0]
    assert len([m for m in messages if m.startswith("monzo link payment names no pot: ")]) == 1
    assert "monzo pot learned from a league's link payment: fields=metadata.collection_pot_id" in (
        messages
    )
    assert "monzo top-up recorded: queued" in messages
    logged = "\n".join(messages)
    for marker in ("4321", "43.21", "00009Savings", "Pat Owner", "DESCRIPTION-MARKER"):
        assert marker not in logged


async def test_a_pot_stays_with_the_first_league_whose_link_named_it(setup: Setup) -> None:
    await _connect(setup)
    await _learn_the_pot(setup)
    other_link = _link()
    await _league(setup.world, [setup.members[1]], other_link)
    theirs = app_payment("tx_00009Theirs", other_link, created=NOW + timedelta(minutes=6))
    setup.fake.add(paid_into(theirs, LEAGUE_POT))
    setup.fake.add(pot_deposit("tx_00009Which", LEAGUE_POT, created=NOW + timedelta(minutes=7)))
    setup.clock.at = NOW + timedelta(minutes=10)
    await setup.reader.catch_up()

    assert await _pots(setup) == {LEAGUE_POT: setup.league.id}
    async with setup.world.sessions() as db:
        booked = (
            await db.scalars(
                select(LedgerEntry.league_id).where(
                    LedgerEntry.monzo_transaction_id == "tx_00009Which"
                )
            )
        ).all()
    assert booked == [setup.league.id]
