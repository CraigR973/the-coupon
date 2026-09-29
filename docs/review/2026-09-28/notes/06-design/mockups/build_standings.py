from pathlib import Path
from _base import HEAD
from _chrome import CSS, header, tabbar
rows = [
 (1,'Hana','W','1','1','2.05',21,'gold',False),
 (2,'Carol','W','1','1','1.95',20,'silver',False),
 (3,'Alice','W','1','1','1.90',19,'bronze',True),
 (4,'Bob','L','1','0','3.10',0,'',False),
 (4,'Former member','L','1','0','3.75',0,'',False),
 (4,'Ivan','V','1','0','—',0,'',False),
 (4,'Jo','L','1','0','4.30',0,'',False),
 (4,'Lee','L','1','0','3.20',0,'',False),
]
def f(c): return f'<i class="f {c}">{c}</i>'
trs = ''.join(f'''<tr class="{'me' if me else ''}"><td class="rk mono {m}">{r}</td><td class="nm"><b>{n}</b><span class="mob sub">{f(fm)}<span class="wn">{w}/{p} won</span></span></td>
<td class="desk c">{f(fm)}</td><td class="desk c mono">{p}</td><td class="desk c mono">{w}</td><td class="desk c mono">{o}</td><td class="pt mono">{pts}</td></tr>''' for r,n,fm,p,w,o,pts,m,me in rows)
html = f'''<!doctype html><html class="dark"><head>{HEAD}<title>Standings table</title><style>{CSS}
body{{padding-bottom:76px}}
.seg{{display:inline-flex;border:1px solid var(--border);border-radius:999px;padding:2px;background:var(--surface)}}
.seg span{{font:600 12px Outfit;padding:5px 10px;border-radius:999px;color:var(--text-secondary)}}
.seg .on{{background:var(--surface-elevated);color:var(--text-primary)}}
.wrap{{max-width:1200px;margin:0 auto;padding:12px 16px}}
.tbl{{width:100%;border-collapse:separate;border-spacing:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden}}
th{{font:600 12px 'JetBrains Mono';letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted);text-align:left;padding:10px 12px;border-bottom:1px solid var(--border)}}
td{{height:52px;padding:0 12px;border-bottom:1px solid var(--border);font-size:15px}}
tr:last-child td{{border-bottom:0}}
.rk{{width:40px;font-size:14px;color:var(--text-secondary);position:relative}}
.rk.gold::before,.rk.silver::before,.rk.bronze::before{{content:'';position:absolute;left:0;top:10px;bottom:10px;width:3px;border-radius:0 3px 3px 0}}
.rk.gold::before{{background:var(--gold)}}.rk.silver::before{{background:var(--silver)}}.rk.bronze::before{{background:var(--bronze)}}
.rk.gold{{color:var(--gold-ink)}}.rk.bronze{{color:var(--bronze-ink)}}
.nm b{{font-weight:600;display:block;line-height:20px}}
.sub{{display:flex;gap:6px;align-items:center;font-size:12px;color:var(--text-muted)}}
.f{{font:600 12px 'JetBrains Mono';font-style:normal;color:var(--text-muted)}}.f.W{{color:var(--success-ink)}}.f.L{{color:var(--error-ink)}}
.pt{{text-align:right;font-size:17px;width:64px}}
.c{{text-align:center}}
tr.me td{{background:color-mix(in srgb,var(--primary) 8%,var(--surface))}}
tr.me .nm b{{color:var(--primary-ink)}}
.foot{{font-size:12px;color:var(--text-muted);margin-top:10px;line-height:1.5}}
.side{{display:none}}
@media(min-width:900px){{body{{padding-bottom:0}}.ctx{{max-width:1200px;margin:0 auto;border:0;padding:16px 24px 8px;background:none}}
 .grid .wrap{{max-width:none;margin:0}}.grid{{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:24px;padding:0 24px}}.wrap{{padding:8px 0}}.side{{display:block;padding-top:8px}}
 td{{height:48px}}}}
.side .card{{padding:16px;margin-bottom:12px}}
.side h3{{font-size:15px;font-weight:600;margin:6px 0 10px}}
.kv{{display:flex;justify-content:space-between;font-size:14px;padding:6px 0;border-top:1px solid var(--border)}}
.kv span:first-child{{color:var(--text-secondary)}}
</style></head><body>
{header('Leagues')}
<div class="ctx"><button class="league-btn">The Coupon Test League <span class="c">▾</span></button><div class="seg"><span class="on">2026/27</span><span>2025/26</span></div></div>
<div class="grid" style="max-width:1200px;margin:0 auto">
<div class="wrap">
<table class="tbl"><thead><tr><th>#</th><th>Member</th><th class="desk c">Form</th><th class="desk c">Played</th><th class="desk c">Won</th><th class="desk c">Avg odds</th><th style="text-align:right">Pts</th></tr></thead><tbody>{trs}</tbody></table>
<p class="foot">Lens 06 mockup (DES-12, DES-13). One column at every width, 52 px rows (all 8 members fit at 390); at 1280 columns instead of a second column of cards. Medal bar 3 px: --gold 10.62:1 dark / 3.24 light, --silver 9.78 / 3.10, --bronze 6.10 / 4.93 (non-text, 3:1). Rank 1 and 3 numerals in --gold-ink / --bronze-ink (≥ 5.03). Own row: --primary at 8% over --surface, name --primary-ink 6.32 / 4.57, points --text-primary 14.56 / 16.21. Odds figures and the void note move to the side card / an info sheet.</p>
</div>
<aside class="side"><div class="card"><div class="overline">Gameweek 1b · settled</div><h3>Hana won the round · 21 pts</h3><div class="kv"><span>Landed</span><span class="mono">3 of 8</span></div><div class="kv"><span>Coupon</span><span class="chip lost">Lost</span></div><div class="kv"><span>Your pick</span><span>Arsenal <span class="mono">1.90</span> · <span style="color:var(--success-ink)">Won 19</span></span></div></div>
<div class="card"><div class="overline">How the table works</div><p class="foot" style="margin-top:8px">Odds figures cover the 7 picks that ran; 1 void pick counts as played but is not priced. Form: last five settled rounds.</p></div></aside>
</div>
{tabbar('Leagues')}
</body></html>'''
Path(__file__).with_name('standings.html').write_text(html)
print('standings.html')
