"""Enumerate every route on the app, with its dependencies, for the authz matrix.

FastAPI 0.141 wraps included routers in _IncludedRouter; recurse via original_router.
Run: ~/.cache/the-coupon/ci-local-venv/bin/python list_routes.py > routes.tsv
"""
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x@localhost/x")
os.environ.setdefault("JWT_ACCESS_SECRET", "a" * 40)
os.environ.setdefault("JWT_REFRESH_SECRET", "b" * 40)
os.environ["ODDS_PROVIDER"] = "fake"
os.environ["SCHEDULER_ENABLED"] = "false"
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from tests.e2e_server import app  # noqa
from fastapi.routing import APIRoute


def deps(dependant, acc):
    for d in dependant.dependencies:
        if d.call is not None:
            acc.add(getattr(d.call, "__name__", repr(d.call)))
        deps(d, acc)
    return acc


def walk(routes, prefix=""):
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            p = (r.include_context.prefix if hasattr(r.include_context, "prefix") else "") or ""
            yield from walk(r.original_router.routes, prefix + p)
        elif isinstance(r, APIRoute):
            yield prefix, r
        else:
            yield prefix, r


for prefix, r in walk(app.routes):
    if isinstance(r, APIRoute):
        ds = sorted(deps(r.dependant, set()) - {"get_db", "get_session"})
        mod = r.endpoint.__module__.split(".")[-1]
        print(f"{','.join(sorted(r.methods))}\t{prefix}{r.path}\t{mod}.{r.endpoint.__name__}\t{' '.join(ds)}")
    else:
        print(f"-\t{prefix}{getattr(r, 'path', '?')}\t{type(r).__name__}\t")
