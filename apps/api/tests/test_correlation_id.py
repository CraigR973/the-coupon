import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app

UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_correlation_id_generated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert "x-correlation-id" in response.headers
    assert UUID4_RE.match(response.headers["x-correlation-id"])


async def test_correlation_id_passthrough(client: AsyncClient) -> None:
    """A supplied id is honoured — as long as it is a UUID.

    This used to pass any string straight through. Batch 58 narrowed it: the value is
    bound into every log line of the request and echoed on the response, so an arbitrary
    caller-chosen string was a free log-volume multiplier. A real UUID still round-trips,
    which is the case the header exists for.
    """
    cid = str(uuid.uuid4())
    response = await client.get("/api/v1/health", headers={"X-Correlation-ID": cid})
    assert response.headers["x-correlation-id"] == cid


# ── Batch 58: the header is data, not a promise ──────────────────────────────


async def test_a_non_uuid_correlation_id_is_replaced_not_echoed() -> None:
    """It used to be taken as sent, bound into every log line, and reflected back.

    Unbounded and attacker-chosen, on a plan whose log retention is already thin: a
    megabyte of header multiplied across every line the request emits. JSON rendering
    escapes the content, so this was always volume rather than injection.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/health", headers={"X-Correlation-ID": "not-a-uuid-" + "x" * 2000}
        )

    returned = resp.headers["X-Correlation-ID"]
    assert returned != "not-a-uuid-" + "x" * 2000
    uuid.UUID(returned)  # a real one was minted instead


async def test_a_well_formed_correlation_id_is_still_honoured() -> None:
    """The useful case survives: a client correlating its own request with the logs."""
    supplied = str(uuid.uuid4())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health", headers={"X-Correlation-ID": supplied})

    assert resp.headers["X-Correlation-ID"] == supplied


async def test_every_response_forbids_shared_caching() -> None:
    """Authenticated JSON should say no rather than rely on the default being silence."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")

    assert resp.headers["Cache-Control"] == "no-store"
