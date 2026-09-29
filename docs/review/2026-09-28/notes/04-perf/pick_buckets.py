"""PERF-09: N leagues each spending their pick bucket cannot exceed the installation plan.

Drives the real limiter the pick route charges (league bucket, then installation bucket,
in the route's order) for N leagues x 50 submissions in one hour, and reports how many
were allowed in total. Writes pick-buckets.txt.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from src.rate_limit import consume_shared_limit, limiter  # noqa: E402
from src.routers.picks import (  # noqa: E402
    PICK_SUBMIT_INSTALLATION_KEY, PICK_SUBMIT_INSTALLATION_LIMIT, PICK_SUBMIT_INSTALLATION_SCOPE,
    PICK_SUBMIT_SHARED_LIMIT, PICK_SUBMIT_SHARED_SCOPE)

lines = [f"league limit {PICK_SUBMIT_SHARED_LIMIT}, installation limit {PICK_SUBMIT_INSTALLATION_LIMIT}"]
for leagues in (1, 2, 5, 20):
    limiter.reset()
    allowed = 0
    for n in range(leagues):
        for _ in range(60):
            if not consume_shared_limit(f"league:{n}", PICK_SUBMIT_SHARED_LIMIT, PICK_SUBMIT_SHARED_SCOPE):
                continue
            if not consume_shared_limit(PICK_SUBMIT_INSTALLATION_KEY, PICK_SUBMIT_INSTALLATION_LIMIT,
                                        PICK_SUBMIT_INSTALLATION_SCOPE):
                continue
            allowed += 1
    lines.append(f"{leagues:2d} leagues x 60 attempts: {allowed} provider-spending submissions allowed in the hour")
Path(__file__).with_name("pick-buckets.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
