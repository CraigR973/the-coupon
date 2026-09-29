"""SEC-16, SEC-17, SEC-20, SEC-23 (port), SEC-26 re-drives."""

from lib import M, call, ids, note, section

A = M["leagues"]["a"]
B = M["leagues"]["b"]
C = M["leagues"]["c"]

section("SEC-16: removal rotates the join code; public_request is gated at both doors")
old = call("GET", f"/api/v1/leagues/{B['slug']}", "dave").json()["join_code"]
note(f"league B code before: {old}")
call("POST", "/api/v1/leagues/join-by-code", "frank", body={"code": old})
call("DELETE", f"/api/v1/leagues/{B['slug']}/members/{ids('frank')}", "dave")
new = call("GET", f"/api/v1/leagues/{B['slug']}", "dave").json()["join_code"]
note(f"league B code after removal: {new} (rotated: {new != old})")
call("POST", "/api/v1/leagues/join-by-code", "frank", body={"code": old})
call("POST", f"/api/v1/leagues/{B['slug']}/join", "frank")
call("GET", f"/api/v1/leagues/{B['slug']}", "frank")
note("public_request league C: join-by-code as v5 (no membership) must create a request")
call("POST", "/api/v1/leagues/join-by-code", "v5", body={"code": C["join_code"]})
call("GET", f"/api/v1/leagues/{C['slug']}/members", "v5")
call("GET", f"/api/v1/leagues/{C['slug']}/join-requests", "dave")
note("second attempt by code while pending:")
call("POST", "/api/v1/leagues/join-by-code", "v5", body={"code": C["join_code"]})

section("SEC-17: non-member site admin on every write route into league A")
note("member-level writes (require_league_member_write):")
call("POST", f"/api/v1/leagues/{A['slug']}/picks", "sam",
     body={"fixture_id": "00000000-0000-0000-0000-000000000000", "market": "MATCH_ODDS",
           "outcome": "HOME", "odds": 2.0})
call("PUT", f"/api/v1/leagues/{A['slug']}/members/me/display-name", "sam",
     body={"display_name_override": "Overseer"})
call("DELETE", f"/api/v1/leagues/{A['slug']}/membership", "sam")
call("PATCH", "/api/v1/notifications/preferences", "sam", body={"league_mutes": {A["id"]: True}})
note("league-admin writes (require_league_admin keeps the site-admin bypass):")
call("PATCH", f"/api/v1/leagues/{A['slug']}", "sam", body={"description": "edited by a non-member site admin"})
call("POST", f"/api/v1/leagues/{A['slug']}/invites", "sam", body={})
call("POST", f"/api/v1/leagues/{A['slug']}/join-code/rotate", "sam")
note("reads still allowed:")
call("GET", f"/api/v1/leagues/{A['slug']}/standings", "sam", quiet_body=True)
call("GET", f"/api/v1/leagues/{A['slug']}/coupon", "sam", quiet_body=True)
note("audit trail for the admin writes above (actor shown to league A's admin):")
r = call("GET", f"/api/v1/leagues/{A['slug']}/audit-log?page_size=5", "alice", quiet_body=True)
for e in r.json()["entries"]:
    note(f"  {e['action_type']:28} actor={e['actor_name']!r} changes={e['changes']}")

section("SEC-20: per-league name override")
for name in ["Carol", "carol", "  Carol  ", "CAROL", "CaroI", "Car0l", "Carо l", "Former member",
             "Sam", "Erin"]:
    call("PUT", f"/api/v1/leagues/{A['slug']}/members/me/display-name", "bob",
         body={"display_name_override": name})
note("bob is now shown as 'Erin' in league A. Erin (league B only) joins league A by code:")
a_code = call("GET", f"/api/v1/leagues/{A['slug']}", "alice").json()["join_code"]
call("POST", "/api/v1/leagues/join-by-code", "erin", body={"code": a_code})
r = call("GET", f"/api/v1/leagues/{A['slug']}/members", "alice", quiet_body=True)
names = [m["display_name"] for m in r.json()]
note(f"league A roster names: {names}")
note(f"'Erin' appears {names.count('Erin')} times")
call("PUT", f"/api/v1/leagues/{A['slug']}/members/me/display-name", "bob",
     body={"display_name_override": None})

section("SEC-23: push endpoint port")
for ep in ["https://fcm.googleapis.com:8443/fcm/send/abc", "https://fcm.googleapis.com:443/fcm/send/abc",
           "https://updates.push.services.mozilla.com:22/wpush/v2/abc"]:
    call("POST", "/api/v1/push/subscribe", "bob",
         body={"endpoint": ep, "keys": {"p256dh": "x", "auth": "y"}})

section("SEC-26: invite to a soft-deleted league")
call("POST", "/api/v1/leagues/claim-invite", "frank", body={"token": M["invite_d"]["token"]})
