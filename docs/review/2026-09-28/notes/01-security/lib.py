"""Shared helpers for the lens-01 probe scripts. Every exchange is appended to probes.txt."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).parent
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-craigrobinson-the-coupon/"
    "3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad"
)
API = "http://127.0.0.1:8110"
LOG = HERE / "probes.txt"


def actors() -> dict:
    return json.loads((SCRATCH / "matrix-actors.json").read_text())


M = actors()
client = httpx.Client(base_url=API, timeout=60)


def section(title: str) -> None:
    line = f"\n## {title}  ({datetime.now():%d %b %H:%M:%S})\n"
    print(line)
    with LOG.open("a") as f:
        f.write(line)


def note(text: str) -> None:
    print(text)
    with LOG.open("a") as f:
        f.write(text + "\n")


def tok(who: str) -> str:
    return M["actors"][who]["token"]


def call(method: str, path: str, who: str | None = None, body=None, headers=None,
         bearer: str | None = None, quiet_body: bool = False, **kw) -> httpx.Response:
    h = dict(headers or {})
    if bearer:
        h["Authorization"] = f"Bearer {bearer}"
    elif who and who != "anon":
        h["Authorization"] = f"Bearer {tok(who)}"
    r = client.request(method, path, headers=h, json=body, **kw)
    text = r.text
    if quiet_body:
        text = f"<{len(text)} bytes>"
    elif len(text) > 400:
        text = text[:400] + f"... <{len(r.text)} bytes>"
    xff = f" XFF={h['X-Forwarded-For']}" if "X-Forwarded-For" in h else ""
    b = "" if body is None else " " + json.dumps(body)[:200]
    note(f"{method} {path} as {who or ('bearer' if bearer else 'anon')}{xff}{b} -> {r.status_code} {text}")
    return r


def ids(who: str) -> str:
    return M["actors"][who]["id"]


def login(name: str, pin: str, xff: str | None = None) -> httpx.Response:
    h = {"X-Forwarded-For": xff} if xff else {}
    return call("POST", "/api/v1/auth/login", body={"display_name": name, "pin": pin},
                headers=h, quiet_body=True)


def wait_for_fresh_window(span: int = 900, need: int = 120) -> None:
    """Sleep until at least `need` seconds remain in the current epoch-aligned window."""
    now = int(time.time())
    left = span - (now % span)
    if left < need:
        note(f"(waiting {left + 2}s for a fresh {span}s limiter window)")
        time.sleep(left + 2)
