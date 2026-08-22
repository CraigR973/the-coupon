"""Version floors that exist for a reason, held to that reason.

A pin is a decision, and the decision is only as durable as the note beside it. This
module reads ``requirements.in`` and asserts the floors that were chosen because a
specific advisory is *reachable in this application* — so lowering one fails here with
the reason attached, rather than passing quietly because the tests never exercise the
path the advisory covers.

It deliberately does not assert "newest available". Most advisories in a dependency tree
are unreachable, and chasing them is how a lock file becomes untrustworthy.
"""

from __future__ import annotations

import re
from pathlib import Path

REQUIREMENTS_IN = Path(__file__).resolve().parents[1] / "requirements.in"


def _pin(package: str) -> tuple[int, ...]:
    """The version pinned for ``package`` in requirements.in, as a comparable tuple."""
    text = REQUIREMENTS_IN.read_text()
    match = re.search(rf"^{re.escape(package)}==([0-9][0-9.]*)", text, re.MULTILINE)
    assert match, f"{package} is not pinned with == in requirements.in"
    return tuple(int(part) for part in match.group(1).split("."))


def test_cryptography_validates_elliptic_curve_subgroups() -> None:
    """GHSA-r6ph-v2qm-q3c2, fixed in 46.0.5 — and reachable here.

    ``POST /api/v1/notifications/push/subscribe`` stores ``keys`` exactly as the browser
    sends it (``routers/notifications.py``), and ``send_notification`` hands that to
    ``webpush()``, which parses the caller's ``p256dh`` as an EC public key. Below 46.0.5
    ``load_der_public_key`` and ``EllipticCurvePublicNumbers.public_key()`` do not check
    that the point lies in the expected prime-order subgroup.

    This is the advisory that overturned the old ``cryptography<=46.0.3`` bound, whose
    stated premise was that no untrusted input reaches the library. It does — a member has
    to be signed in to send it, which bounds the exposure, but does not remove it.
    """
    assert _pin("cryptography") >= (46, 0, 5)


def test_cryptography_rejects_non_contiguous_buffers_safely() -> None:
    """PYSEC-2026-36, fixed in 46.0.7: buffer overflow via a non-contiguous buffer.

    Reaches any ``Hash.update`` path, which VAPID signing uses on every push send.
    """
    assert _pin("cryptography") >= (46, 0, 7)


def test_cryptography_wheels_carry_a_patched_openssl() -> None:
    """GHSA-537c-gmf6-5ccf, fixed in 48.0.1.

    The wheels statically link OpenSSL, so this is not a transitive dependency that could
    be patched underneath — the version of cryptography *is* the version of OpenSSL.
    """
    assert _pin("cryptography") >= (48, 0, 1)


def test_the_cryptography_ceiling_is_a_wheel_decision_not_a_security_one() -> None:
    """48.0.1 is deliberate, and the two advisories above it are unreachable.

    49.0.0 fixes exponential X.509 path-building on chains with duplicate self-signed
    intermediates; 50.0.0 fixes a Bleichenbacher oracle in PKCS#7 ``EnvelopedData``
    decryption. This application validates no certificate chains and decrypts no PKCS#7.

    48.0.1 is also the last release publishing a macOS ``universal2`` wheel, so it is the
    highest version the local gate can install on either Intel or Apple silicon without a
    Rust toolchain. If either advisory above ever becomes reachable, that trade changes and
    this test should be deleted rather than relaxed.
    """
    assert _pin("cryptography") <= (48, 0, 1)


def test_python_dotenv_cannot_follow_a_symlink_out_of_the_project() -> None:
    """CVE-2026-28684, fixed in 1.2.2.

    Not reachable — the app only ever reads ``.env`` and never calls ``set_key`` — so this
    floor is hygiene rather than a fix, and is recorded as such.
    """
    assert _pin("python-dotenv") >= (1, 2, 2)
