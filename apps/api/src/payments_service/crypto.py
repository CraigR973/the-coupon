"""The Monzo tokens, encrypted at rest with a key only the payments service holds. Batch 208.

ADR 0009 option B. The database is shared with the member-facing API, so the tokens are
stored as Fernet ciphertexts (AES-128-CBC with an HMAC-SHA256, from ``cryptography``)
under ``MONZO_TOKEN_ENCRYPTION_KEY``: a database reader without that key, the API
included, holds nothing it can spend.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class TokenCipherUnavailable(RuntimeError):
    """The key is not a Fernet key, so no token can be sealed or opened."""


class TokenUnreadable(RuntimeError):
    """A stored token did not open under this key: a different key, or a tampered row."""


class TokenCipher:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError):
            # The key's own text is never part of the message.
            raise TokenCipherUnavailable(
                "MONZO_TOKEN_ENCRYPTION_KEY is not URL-safe base64 of 32 bytes."
            ) from None

    def seal(self, token: str) -> str:
        return self._fernet.encrypt(token.encode()).decode()

    def open(self, sealed: str) -> str:
        try:
            return self._fernet.decrypt(sealed.encode()).decode()
        except InvalidToken:
            raise TokenUnreadable("a stored Monzo token does not open under this key") from None
