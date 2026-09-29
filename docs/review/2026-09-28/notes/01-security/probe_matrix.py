"""Route-by-route authorisation matrix, probed against the running stack on :8110.

    ~/.cache/the-coupon/ci-local-venv/bin/python probe_matrix.py

Columns are roles relative to league A (`the-coupon`):
  anon, bob (member A), alice (league admin A), erin (member B), dave (league admin B),
  frank (outsider), sam (site admin, member of nothing).

Every route gets a concrete request. Destructive routes are aimed at a random target id,
so an *authorised* caller reaches the handler's own lookup (404) while an unauthorised one
is refused by the dependency first (401/403) — which is the authz decision being tested —
without mutating anything. The handful of routes that cannot be probed that way are
listed in SPECIAL and handled by hand (see probes.txt).

Writes matrix.csv and matrix.txt next to this file.
"""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path

import httpx

HERE = Path(__file__).parent
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-craigrobinson-the-coupon/"
    "3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad"
)
API = "http://127.0.0.1:8110"
M = json.loads((SCRATCH / "matrix-actors.json").read_text())
A = M["leagues"]["a"]
B = M["leagues"]["b"]
ROLES = ["anon", "bob", "alice", "erin", "dave", "frank", "sam"]
RND = str(uuid.uuid4())
BOB = M["actors"]["bob"]["id"]

# (class, method, path, json-body or None)
#   public | self | member_read | member_write | league_admin | site_admin
ROUTES: list[tuple[str, str, str, object]] = [
    ("public", "GET", "/api/v1/health", None),
    ("public", "GET", "/api/v1/health/ready", None),
    ("self", "GET", "/api/v1/config", None),
    ("self", "GET", "/api/v1/auth/me", None),
    ("self", "PATCH", "/api/v1/auth/me", {}),
    ("self", "PUT", "/api/v1/auth/me/pin", {"current_pin": "9998", "new_pin": "8351"}),
    ("self", "POST", "/api/v1/auth/me/avatar", None),
    ("self", "DELETE", "/api/v1/auth/me/avatar", None),
    ("site_admin", "DELETE", f"/api/v1/auth/players/{RND}/avatar", None),
    ("self", "GET", "/api/v1/me/profile", None),
    ("self", "GET", "/api/v1/me/cross-league-summary", None),
    ("self", "GET", "/api/v1/me/export", None),
    ("self", "POST", "/api/v1/me/delete", {"pin": "9998"}),
    ("self", "GET", "/api/v1/me/rename-notice", None),
    ("self", "POST", "/api/v1/me/rename-notice/seen", None),
    ("public", "GET", "/api/v1/push/vapid-public-key", None),
    ("self", "POST", "/api/v1/push/subscribe", {"endpoint": "https://127.0.0.1/x", "keys": {}}),
    ("self", "DELETE", "/api/v1/push/unsubscribe", {"endpoint": "https://fcm.googleapis.com/fcm/send/none"}),
    ("self", "GET", "/api/v1/notifications/preferences", None),
    ("self", "PATCH", "/api/v1/notifications/preferences", {"league_mutes": {B["id"]: True}}),
    ("self", "POST", "/api/v1/leagues", {"name": ""}),
    ("self", "GET", "/api/v1/leagues/mine", None),
    ("self", "GET", "/api/v1/leagues/discover", None),
    ("public", "GET", "/api/v1/leagues/by-code/ZZZZZZ", None),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}", None),
    ("league_admin", "PATCH", f"/api/v1/leagues/{A['slug']}", {}),
    ("league_admin", "GET", f"/api/v1/leagues/{A['slug']}/audit-log", None),
    ("league_admin", "GET", f"/api/v1/leagues/{A['slug']}/competitions", None),
    ("league_admin", "POST", f"/api/v1/leagues/{A['slug']}/gameweeks/refresh", None),
    ("self", "POST", f"/api/v1/leagues/{A['slug']}/join", None),
    ("self", "POST", "/api/v1/leagues/claim-invite", {"token": "bogus"}),
    ("self", "POST", "/api/v1/leagues/join-by-code", {"code": "ZZZZZZ"}),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}/members", None),
    ("league_admin", "POST", f"/api/v1/leagues/{A['slug']}/members/{RND}/promote", None),
    ("league_admin", "POST", f"/api/v1/leagues/{A['slug']}/members/{RND}/demote", None),
    ("league_admin", "DELETE", f"/api/v1/leagues/{A['slug']}/members/{RND}", None),
    ("member_write", "PUT", f"/api/v1/leagues/{A['slug']}/members/me/display-name", {"display_name_override": None}),
    ("league_admin", "GET", f"/api/v1/leagues/{A['slug']}/invites", None),
    ("league_admin", "DELETE", f"/api/v1/leagues/{A['slug']}/invites/{RND}", None),
    ("league_admin", "POST", f"/api/v1/leagues/{A['slug']}/members/{RND}/reset-pin", None),
    ("league_admin", "GET", f"/api/v1/leagues/{A['slug']}/join-requests", None),
    ("league_admin", "POST", f"/api/v1/leagues/{A['slug']}/join-requests/{RND}/approve", {}),
    ("league_admin", "POST", f"/api/v1/leagues/{A['slug']}/join-requests/{RND}/reject", {}),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}/gameweeks", None),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}/gameweek/current", None),
    ("self", "GET", "/api/v1/football/tables", None),
    ("self", "GET", "/api/v1/football/results", None),
    ("self", "GET", "/api/v1/football/teams/1/season?competition=x", None),
    ("member_write", "POST", f"/api/v1/leagues/{A['slug']}/picks", {"fixture_id": RND, "market": "MATCH_ODDS", "outcome": "HOME", "odds": 2.0}),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}/gameweeks/{A['gameweek_id']}/pick", None),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}/coupon", None),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}/standings", None),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}/seasons", None),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}/results", None),
    ("member_read", "GET", f"/api/v1/leagues/{A['slug']}/players/{BOB}/profile", None),
    ("site_admin", "GET", "/api/v1/admin/calendar", None),
    ("site_admin", "PUT", "/api/v1/admin/calendar/anchor", {}),
    ("site_admin", "POST", "/api/v1/admin/calendar/extra-weeks", {}),
    ("site_admin", "DELETE", "/api/v1/admin/calendar/extra-weeks", {}),
    ("site_admin", "GET", "/api/v1/admin/players", None),
    ("site_admin", "POST", f"/api/v1/admin/players/{RND}/reset-pin", None),
    ("site_admin", "POST", f"/api/v1/admin/players/{RND}/unlock", None),
    ("site_admin", "DELETE", f"/api/v1/admin/players/{RND}", None),
    ("site_admin", "GET", "/api/v1/admin/invites", None),
    ("site_admin", "DELETE", f"/api/v1/admin/invites/{RND}", None),
    ("site_admin", "GET", "/api/v1/admin/leagues", None),
    ("site_admin", "POST", f"/api/v1/admin/leagues/{RND}/rotate-join-code", None),
    ("site_admin", "GET", "/api/v1/admin/dashboard", None),
    ("site_admin", "GET", "/api/v1/admin/jobs", None),
    ("site_admin", "POST", "/api/v1/admin/jobs/no-such-job/run", None),
    ("site_admin", "GET", "/api/v1/admin/results/pending", None),
    ("site_admin", "POST", f"/api/v1/admin/results/{RND}/settle", {"results": []}),
    ("site_admin", "POST", f"/api/v1/admin/picks/{RND}/correct", {"home_goals": 1, "away_goals": 0, "reason": "probe"}),
]

# Probed by hand in probes.txt, because a random id cannot stand in for the target:
SPECIAL = [
    "POST /api/v1/auth/login, /register, /refresh, /logout, /pin/reset-request, /pin/set (auth lifecycle)",
    "DELETE /api/v1/leagues/{slug} (would delete league A for alice/sam)",
    "DELETE /api/v1/leagues/{slug}/membership (would remove a real member)",
    "POST /api/v1/leagues/{slug}/join-code/rotate (mutates; probed by hand)",
    "POST /api/v1/leagues/{slug}/invites (mutates; probed by hand)",
]

ALLOWED = {
    "public": set(ROLES),
    "self": set(ROLES) - {"anon"},
    "member_read": {"bob", "alice", "sam"},
    "member_write": {"bob", "alice"},
    "league_admin": {"alice", "sam"},
    "site_admin": {"sam"},
}


def refused(code: int) -> bool:
    return code in (401, 403)


def main() -> None:
    rows = []
    with httpx.Client(base_url=API, timeout=30) as c:
        for cls, method, path, body in ROUTES:
            codes = {}
            for role in ROLES:
                headers = {}
                if role != "anon":
                    headers["Authorization"] = f"Bearer {M['actors'][role]['token']}"
                kw = {"headers": headers}
                if body is not None:
                    kw["json"] = body
                r = c.request(method, path, **kw)
                codes[role] = r.status_code
            verdicts = []
            for role in ROLES:
                want_allowed = role in ALLOWED[cls]
                got = codes[role]
                # A private league answers 404 to a non-member on GET /leagues/{slug}.
                got_refused = refused(got) or (
                    cls == "member_read" and path.endswith(A["slug"]) and got == 404
                )
                ok = (not got_refused) if want_allowed else got_refused
                verdicts.append("ok" if ok else "MISMATCH")
            rows.append((cls, method, path.replace(RND, "{rnd}"), codes, verdicts))

    with (HERE / "matrix.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["class", "method", "path", *ROLES, "verdict"])
        for cls, method, path, codes, verdicts in rows:
            w.writerow([cls, method, path, *(codes[r] for r in ROLES),
                        "ok" if all(v == "ok" for v in verdicts) else "MISMATCH"])

    lines = [f"{'class':13} {'method':6} {'path':70} " + " ".join(f"{r:>5}" for r in ROLES)]
    mismatches = 0
    for cls, method, path, codes, verdicts in rows:
        mark = "" if all(v == "ok" for v in verdicts) else "  <-- MISMATCH"
        mismatches += bool(mark)
        lines.append(f"{cls:13} {method:6} {path:70} " + " ".join(f"{codes[r]:>5}" for r in ROLES) + mark)
    lines.append("")
    lines.append(f"{len(rows)} routes x {len(ROLES)} roles probed; {mismatches} mismatches")
    lines.append("Hand-probed (see probes.txt): " + "; ".join(SPECIAL))
    (HERE / "matrix.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
