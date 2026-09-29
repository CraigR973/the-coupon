"""Cross-league IDOR: league B / C ids pushed through league A's slug (and id-only routes)."""

import json

from lib import M, call, ids, note, section

A, B, C = M["leagues"]["a"], M["leagues"]["b"], M["leagues"]["c"]
a = A["slug"]

section("IDOR: league-B round id through league A")
call("GET", f"/api/v1/leagues/{a}/gameweeks/{B['gameweek_id']}/pick", "alice")
call("GET", f"/api/v1/leagues/{a}/coupon?gameweek_id={B['gameweek_id']}", "alice")
call("GET", f"/api/v1/leagues/{a}/gameweek/current?gameweek_id={B['gameweek_id']}", "alice", quiet_body=True)

section("IDOR: a league-B-only member's id through league A's admin routes")
dave = ids("dave")
for verb, path in [("POST", "promote"), ("POST", "demote"), ("POST", "reset-pin")]:
    call(verb, f"/api/v1/leagues/{a}/members/{dave}/{path}", "alice")
call("DELETE", f"/api/v1/leagues/{a}/members/{dave}", "alice")
call("GET", f"/api/v1/leagues/{a}/players/{dave}/profile", "alice")

section("IDOR: league-B invite and league-C join request through league A")
call("DELETE", f"/api/v1/leagues/{a}/invites/{M['invite_b']['id']}", "alice")
call("POST", f"/api/v1/leagues/{a}/join-requests/{M['join_request_c']}/approve", "alice", body={})
call("POST", f"/api/v1/leagues/{a}/join-requests/{M['join_request_c']}/reject", "alice", body={})

section("IDOR: audit isolation")
r = call("GET", f"/api/v1/leagues/{a}/audit-log?page_size=100", "alice", quiet_body=True)
blob = json.dumps(r.json())
note(f"  league A audit mentions league B id: {B['id'] in blob}; league-b slug: {'league-b' in blob}; league C id: {C['id'] in blob}")
r = call("GET", f"/api/v1/leagues/{B['slug']}/audit-log?page_size=100", "dave", quiet_body=True)
blob = json.dumps(r.json())
note(f"  league B audit mentions league A id: {A['id'] in blob}; 'the-coupon' slug: {'the-coupon' in blob}")

section("IDOR: muting a league you are not in")
r = call("PATCH", "/api/v1/notifications/preferences", "bob", body={"league_mutes": {B["id"]: True}})
note(f"  bob's leagues after muting league B: {[l['league_name'] for l in r.json()['leagues']]}")
