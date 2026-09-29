"""Live OSV query over the API's full Python lock and the pnpm lockfile.

    ~/.cache/the-coupon/ci-local-venv/bin/python osv_query.py > osv.txt

Public endpoint, no key: https://api.osv.dev/v1/querybatch (then /v1/vulns/{id} for detail).
Also classifies each npm package as runtime (reachable from apps/web's `dependencies`)
or dev/build/test only, by walking the pnpm `snapshots` graph from the importer.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import httpx
import yaml

ROOT = Path("/Users/craigrobinson/the-coupon")

py = []
for line in (ROOT / "apps/api/requirements.txt").read_text().splitlines():
    m = re.match(r"^([A-Za-z0-9_.\-\[\]]+)==([^\s;]+)", line)
    if m:
        py.append((re.sub(r"\[.*\]", "", m.group(1)).lower(), m.group(2)))

lock = yaml.safe_load((ROOT / "pnpm-lock.yaml").read_text())


def split_key(key: str) -> tuple[str, str]:
    key = key.split("(")[0]
    at = key.rfind("@")
    return key[:at], key[at + 1:]


npm = sorted({split_key(k) for k in lock["packages"]})

# Runtime closure: apps/web `dependencies` (not devDependencies), through snapshots.
importer = lock["importers"].get("apps/web", {})
snap = lock.get("snapshots", {})
runtime: set[str] = set()
stack = []
for name, spec in (importer.get("dependencies") or {}).items():
    stack.append(f"{name}@{spec['version']}")
while stack:
    k = stack.pop()
    if k in runtime:
        continue
    runtime.add(k)
    node = snap.get(k) or {}
    for section in ("dependencies", "optionalDependencies"):
        for dn, dv in (node.get(section) or {}).items():
            stack.append(f"{dn}@{dv}")
runtime_pkgs = {split_key(k) for k in runtime}

queries = [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in py]
queries += [{"package": {"name": n, "ecosystem": "npm"}, "version": v} for n, v in npm]

hits: dict[tuple[str, str, str], list[str]] = defaultdict(list)
with httpx.Client(timeout=60) as c:
    for i in range(0, len(queries), 500):
        batch = queries[i:i + 500]
        r = c.post("https://api.osv.dev/v1/querybatch", json={"queries": batch})
        r.raise_for_status()
        for q, res in zip(batch, r.json()["results"]):
            for v in res.get("vulns") or []:
                hits[(q["package"]["ecosystem"], q["package"]["name"], q["version"])].append(v["id"])

    detail = {}
    for ids in hits.values():
        for vid in ids:
            if vid not in detail:
                d = c.get(f"https://api.osv.dev/v1/vulns/{vid}").json()
                sev = (d.get("database_specific") or {}).get("severity") or ""
                fixed = sorted({
                    e["fixed"]
                    for a in d.get("affected", [])
                    for rg in a.get("ranges", [])
                    for e in rg.get("events", [])
                    if "fixed" in e
                })
                detail[vid] = (d.get("aliases") or [], sev, (d.get("summary") or "")[:110], fixed, d.get("withdrawn"))

print(f"PyPI pins: {len(py)}   npm packages in lockfile: {len(npm)}   npm runtime closure: {len(runtime_pkgs)}")
print(f"packages with hits: {len(hits)}   advisories: {len(detail)}")
print()
for (eco, name, ver), ids in sorted(hits.items()):
    scope = "" if eco == "PyPI" else ("RUNTIME" if (name, ver) in runtime_pkgs else "dev/build")
    print(f"{eco} {name}=={ver} {scope}")
    for vid in ids:
        aliases, sev, summ, fixed, wd = detail[vid]
        print(f"    {vid} {','.join(a for a in aliases if a.startswith('CVE'))} [{sev}] fixed={fixed[-3:]} {'WITHDRAWN ' if wd else ''}{summ}")
