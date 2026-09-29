"""Secret scan over the tracked tree and the full git history. Never prints a secret:
each hit is reported as commit/file/pattern plus a masked fingerprint (first 4 chars and
length) and, for JWT-shaped strings, only the decoded `role`/`iss`/`ref` claims.

    ~/.cache/the-coupon/ci-local-venv/bin/python secret_scan.py > secret-scan.txt
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from collections import defaultdict

REPO = "/Users/craigrobinson/the-coupon"
PATTERNS = {
    "jwt_secret_assign": r"JWT_(?:ACCESS|REFRESH)_SECRET\s*[=:]\s*['\"]?([^\s'\"#]{16,})",
    "dsn_with_password": r"postgres(?:ql)?(?:\+asyncpg)?://[^:\s/@]+:([^@\s'\"]{6,})@",
    "vapid_private": r"VAPID_PRIVATE_KEY\s*[=:]\s*['\"]?([A-Za-z0-9_\-+/=]{20,})",
    "pem_private_key": r"(-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----)",
    "jwt_token": r"(eyJhbGciOi[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,})",
    "supabase_secret": r"(sb_secret_[A-Za-z0-9_-]{10,})",
    "aws_access_key": r"((?:AKIA|ASIA)[0-9A-Z]{16})",
    "s3_secret_assign": r"(?:AWS_SECRET_ACCESS_KEY|BACKUP_[A-Z_]*SECRET[A-Z_]*|R2_SECRET[A-Z_]*)\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{20,})",
    "odds_api_key_assign": r"(?:ODDS_API_KEY|API_FOOTBALL_KEY|FOOTBALL_DATA_[A-Z_]*KEY|RAPIDAPI_KEY)\s*[=:]\s*['\"]?([A-Za-z0-9]{16,})",
    "betfair_secret_assign": r"BETFAIR_(?:PASSWORD|APP_KEY|USERNAME)\s*[=:]\s*['\"]?([^\s'\"#]{6,})",
    "github_token": r"((?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,})",
    "generic_key_assign": r"(?i)(?:secret|api[_-]?key|token|password)['\"]?\s*[:=]\s*['\"]([A-Za-z0-9_\-+/=]{24,})['\"]",
}
BENIGN = re.compile(r"(?i)review-|test|example|dummy|placeholder|changeme|xxxx|fake|local|dev-|sample|<|\$\{|your", re.I)


def mask(v: str) -> str:
    return f"{v[:4]}…(len {len(v)})"


def jwt_claims(tok: str) -> str:
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        d = json.loads(base64.urlsafe_b64decode(p))
        keep = {k: d[k] for k in ("role", "iss", "ref", "sub") if k in d}
        if "sub" in keep:
            keep["sub"] = str(keep["sub"])[:8] + "…"
        return json.dumps(keep)
    except Exception:
        return "undecodable"


def scan(stream: str, where_fn) -> dict:
    hits = defaultdict(set)
    for name, pat in PATTERNS.items():
        for m in re.finditer(pat, stream):
            val = m.group(1)
            where = where_fn(m.start())
            benign = bool(BENIGN.search(val)) or bool(BENIGN.search(stream[max(0, m.start() - 80): m.start()]))
            extra = f" claims={jwt_claims(val)}" if name == "jwt_token" else ""
            hits[(name, mask(val), "benign-looking" if benign else "REVIEW")].add(where + extra)
    return hits


# 1. tracked tree at HEAD
tree = subprocess.run(["git", "-C", REPO, "grep", "-I", "-n", "-E", "--no-color", "."],
                      capture_output=True, text=True).stdout
lines = tree.splitlines()
offsets, pos = [], 0
for ln in lines:
    offsets.append(pos)
    pos += len(ln) + 1
import bisect  # noqa: E402


def tree_where(i: int) -> str:
    ln = lines[bisect.bisect_right(offsets, i) - 1]
    f, n, _ = ln.split(":", 2)
    return f"HEAD:{f}:{n}"


print("## tracked tree (HEAD)")
for k, v in sorted(scan(tree, tree_where).items()):
    if "node_modules" in " ".join(v):
        continue
    print(f"{k[0]:22} {k[1]:18} {k[2]:15} {sorted(v)[:4]}{' +' + str(len(v) - 4) if len(v) > 4 else ''}")

# 2. full history: every added line in every commit on every ref
log = subprocess.run(["git", "-C", REPO, "log", "--all", "-p", "--no-color", "-U0",
                      "--format=@@COMMIT %h"], capture_output=True, text=True, errors="replace").stdout
marks = [(m.start(), m.group(1)) for m in re.finditer(r"^@@COMMIT (\w+)", log, re.M)]
files = [(m.start(), m.group(1)) for m in re.finditer(r"^\+\+\+ b/(.*)$", log, re.M)]
added = "\n".join(l for l in log.splitlines() if l.startswith("+") or l.startswith("@@COMMIT") or l.startswith("+++ b/"))
# re-index on the filtered text
log = added
marks = [(m.start(), m.group(1)) for m in re.finditer(r"^@@COMMIT (\w+)", log, re.M)]
files = [(m.start(), m.group(1)) for m in re.finditer(r"^\+\+\+ b/(.*)$", log, re.M)]
mo = [m[0] for m in marks]
fo = [f[0] for f in files]


def hist_where(i: int) -> str:
    c = marks[bisect.bisect_right(mo, i) - 1][1] if marks else "?"
    fi = bisect.bisect_right(fo, i) - 1
    f = files[fi][1] if fi >= 0 else "?"
    return f"{c}:{f}"


n_commits = subprocess.run(["git", "-C", REPO, "rev-list", "--all", "--count"], capture_output=True, text=True).stdout.strip()
print(f"\n## full history ({n_commits} commits, added lines only)")
for k, v in sorted(scan(log, hist_where).items()):
    print(f"{k[0]:22} {k[1]:18} {k[2]:15} {sorted(v)[:4]}{' +' + str(len(v) - 4) if len(v) > 4 else ''}")
