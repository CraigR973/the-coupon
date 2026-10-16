"""What the payments service reads from its own environment. Batch 208.

Never ``src.config``: in production that demands the API's secrets, and this process holds
none of them. These are the four sealed ``MONZO_*`` variables Batch 207 declared on the
``payments`` service alone, plus the one public address Monzo is told to send the owner
back to.

A missing or malformed value does not stop the boot. The health pair keeps answering and
every Monzo route says the service is not configured, which is visible from the outside;
a crash loop over a mistyped secret would hide which one it was.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

#: The production payments origin, the same value ``PAYMENTS_ORIGINS`` records in
#: ``.railway/railway.ts`` (a test holds the two together). Monzo compares the redirect
#: address byte for byte with the one registered on the owner's OAuth client.
PRODUCTION_ORIGIN = "https://payments-production-0aa1.up.railway.app"
CALLBACK_PATH = "/monzo/oauth/callback"
CONNECT_PATH = "/monzo/oauth/start"
WEBHOOK_PATH_PREFIX = "/monzo/webhook/"

CLIENT_ID_ENV = "MONZO_CLIENT_ID"
CLIENT_SECRET_ENV = "MONZO_CLIENT_SECRET"
ENCRYPTION_KEY_ENV = "MONZO_TOKEN_ENCRYPTION_KEY"
WEBHOOK_PATH_SECRET_ENV = "MONZO_WEBHOOK_PATH_SECRET"

#: URL-safe base64, as ``secrets.token_urlsafe`` or a Fernet key produces it. At least 32
#: characters, so it cannot be guessed by walking the path.
_PATH_SECRET = re.compile(r"^[A-Za-z0-9_=-]{32,}$")


@dataclass(frozen=True)
class MonzoSettings:
    client_id: str
    client_secret: str
    encryption_key: str
    webhook_path_secret: str
    origin: str = PRODUCTION_ORIGIN

    @property
    def redirect_uri(self) -> str:
        return f"{self.origin}{CALLBACK_PATH}"

    @property
    def webhook_url(self) -> str:
        return f"{self.origin}{WEBHOOK_PATH_PREFIX}{self.webhook_path_secret}"

    def secrets(self) -> tuple[str, ...]:
        """Every value a log line must never carry."""
        return (self.client_secret, self.encryption_key, self.webhook_path_secret)


_NAMES = (CLIENT_ID_ENV, CLIENT_SECRET_ENV, ENCRYPTION_KEY_ENV, WEBHOOK_PATH_SECRET_ENV)
_QUOTES = ('"', "'")


def monzo_settings_problems(environ: Mapping[str, str] | None = None) -> list[str]:
    """Why :func:`monzo_settings` refuses, by variable name and reason only.

    The four values are sealed on Railway, so nobody can read them back to see which is
    wrong: the boot log is the only place that can say. It names the variable and the
    rule it breaks, and never repeats any part of a value.
    """
    values = os.environ if environ is None else environ
    problems: list[str] = []
    for name in _NAMES:
        raw = values.get(name)
        value = (raw or "").strip()
        if raw is None:
            problems.append(f"{name} is not set")
        elif not value:
            problems.append(f"{name} is empty")
        elif value[0] in _QUOTES or value[-1] in _QUOTES:
            problems.append(f"{name} is wrapped in quotes")
    path_secret = (values.get(WEBHOOK_PATH_SECRET_ENV) or "").strip()
    if path_secret and path_secret[0] not in _QUOTES and path_secret[-1] not in _QUOTES:
        if not re.fullmatch(r"[A-Za-z0-9_=-]+", path_secret):
            problems.append(
                f"{WEBHOOK_PATH_SECRET_ENV} has characters other than letters, digits, "
                "'-', '_' and '='"
            )
        elif len(path_secret) < 32:
            problems.append(f"{WEBHOOK_PATH_SECRET_ENV} is shorter than 32 characters")
    return problems


def monzo_settings(environ: Mapping[str, str] | None = None) -> MonzoSettings | None:
    """The service's Monzo settings, or ``None`` when any is missing or malformed."""
    values = os.environ if environ is None else environ
    if monzo_settings_problems(values):
        return None
    client_id = values.get(CLIENT_ID_ENV, "").strip()
    client_secret = values.get(CLIENT_SECRET_ENV, "").strip()
    encryption_key = values.get(ENCRYPTION_KEY_ENV, "").strip()
    path_secret = values.get(WEBHOOK_PATH_SECRET_ENV, "").strip()
    if not _PATH_SECRET.fullmatch(path_secret):
        return None
    return MonzoSettings(
        client_id=client_id,
        client_secret=client_secret,
        encryption_key=encryption_key,
        webhook_path_secret=path_secret,
    )
