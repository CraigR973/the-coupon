"""Print one fixture of the slate JSON and the per-field byte split (diagnostic)."""
import asyncio, json, os, sys
sys.argv = [sys.argv[0], "peek"]
sys.path.insert(0, os.path.dirname(__file__))
import measure_api as m

async def main():
    toks = await m.tokens()
    async with m.AsyncClient(transport=m.ASGITransport(app=m.app), base_url="http://t") as c:
        r = await c.get("/api/v1/leagues/the-coupon/gameweek/current",
                        headers={"Authorization": f"Bearer {toks['Alice'][1]}", "Accept-Encoding": "identity"})
        body = r.json()
        fx = body["fixtures"]
        print("fixtures", len(fx), "members", len(body["members"]), "total bytes", len(r.content))
        print(json.dumps(fx[0], indent=1)[:2500])
        sel = sum(len(json.dumps(f["selections"])) for f in fx)
        print("selections bytes", sel, "per fixture", sel // len(fx))
    await m.engine.dispose()
asyncio.run(main())
