from pathlib import Path
from _base import HEAD
from _chrome import CSS, header, tabbar
def sel(label, price, meta, state):
    return f'<div class="sel {state}"><span class="lb">{label}</span><span class="pr mono">{price}</span><span class="mt">{meta}</span></div>'
legs = [('Arsenal','Alice · you','1.90','won','Won','19'),('No — not both score','Hana','2.05','won','Won','21'),('Yes · BTTS (Forfar)','Carol','1.95','won','Won','20'),
        ('Both teams score','Ivan','1.80','void','Void','—'),('Draw','Former member','3.75','lost','Lost','0'),('Chelsea','Jo','4.30','lost','Lost','0'),('Brechin City','Bob','3.10','lost','Lost','0'),('Draw (Forfar)','Lee','3.20','lost','Lost','0')]
lis = ''.join(f'<li class="{"me" if "you" in w else ""}"><span class="dot {s}"></span><span class="nm"><b>{n}</b><span>{w}</span></span><span class="mono o">{o}</span><span class="res {s}">{r}{"" if p in ("—","0") else f" · {p}"}</span></li>' for n,w,o,s,r,p in legs)
html = f'''<!doctype html><html class="dark"><head>{HEAD}<title>Settled coupon</title><style>{CSS}
body{{padding-bottom:76px}}
.wrap{{max-width:1200px;margin:0 auto;padding:12px 16px}}
.res-card{{padding:16px}}
.head{{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}}
.outcome{{font-size:24px;font-weight:600;line-height:30px}}
.outcome.lost{{color:var(--error-ink)}}.outcome.won{{color:var(--success-ink)}}
.landed{{font-size:15px;color:var(--text-secondary)}}
.price{{margin-top:6px;font-size:20px;color:var(--text-secondary)}}
.price s{{text-decoration-thickness:1.5px}}
.price small{{font:400 13px Outfit;color:var(--text-muted);margin-left:6px}}
.void-note{{font-size:13px;color:var(--text-muted);margin-top:4px}}
.legs{{list-style:none;margin-top:12px}}
.legs li{{display:grid;grid-template-columns:10px 1fr 52px 78px;align-items:center;gap:10px;min-height:52px;border-top:1px solid var(--border);font-size:14px}}
.legs li.me .nm b{{color:var(--primary-ink)}}
.nm b{{display:block;font-weight:600;line-height:19px}}.nm span{{font-size:12px;color:var(--text-muted)}}
.o{{text-align:right;color:var(--text-secondary)}}
.res{{text-align:right;font-weight:600;font-size:13px}}
.res.won{{color:var(--success-ink)}}.res.lost{{color:var(--error-ink)}}.res.void{{color:var(--text-muted)}}
.dot{{width:8px;height:8px;border-radius:50%}}.dot.won{{background:var(--success)}}.dot.lost{{background:var(--error)}}.dot.void{{background:var(--text-muted)}}
.won-card{{padding:16px;margin-top:12px}}
.slate{{margin-top:16px}}
.fx{{padding:14px}}
.teams{{display:flex;justify-content:space-between;font-size:16px;font-weight:600;line-height:26px}}
.score{{font:600 17px 'JetBrains Mono';color:var(--text-primary)}}
.row3{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}}
.sel{{min-height:64px;display:flex;flex-direction:column;justify-content:center;gap:1px;padding:8px 10px;border-radius:12px;border:1px solid var(--border);background:var(--surface-elevated)}}
.sel .lb{{font-size:14px;color:var(--text-secondary)}}.sel .pr{{font-size:17px}}.sel .mt{{font-size:12px;font-weight:600}}
.sel.won{{border-color:var(--success-ink)}}.sel.won .mt{{color:var(--success-ink)}}
.sel.lost .pr{{color:var(--text-muted)}}.sel.lost .mt{{color:var(--error-ink)}}
.sel.void .pr{{color:var(--text-muted)}}.sel.void .mt{{color:var(--text-muted)}}
.sel.none .mt{{color:var(--text-muted);font-weight:400}}
.foot{{font-size:12px;color:var(--text-muted);margin-top:12px;line-height:1.5}}
@media(min-width:900px){{body{{padding-bottom:0}}.ctx{{max-width:1200px;margin:0 auto;border:0;padding:16px 24px 8px;background:none}}
 .grid .wrap{{max-width:none;margin:0}}.grid{{display:grid;grid-template-columns:420px minmax(0,1fr);gap:24px;padding:0 24px}}.wrap{{padding:8px 0}}.slate{{margin-top:0}}}}
</style></head><body>
{header('Coupon')}
<div class="ctx"><button class="league-btn">The Coupon Test League <span class="c">▾</span></button><div style="display:flex;gap:8px;align-items:center"><span class="mono" style="font-size:13px;color:var(--text-secondary)">GW 1b</span><span class="chip">Settled</span></div></div>
<div class="grid" style="max-width:1200px;margin:0 auto">
<div class="wrap">
<section class="res-card card"><div class="overline">Gameweek 1b · result</div>
<div class="head" style="margin-top:6px"><span class="outcome lost">Coupon lost</span><span class="landed">3 of 8 landed</span></div>
<div class="price mono"><s>1214.94</s><small>combined odds</small></div>
<div class="void-note">1 leg void — not in the combined price</div>
<ol class="legs">{lis}</ol></section>
<section class="won-card card"><div class="overline">The same card when every leg lands</div><div class="head" style="margin-top:6px"><span class="outcome won">Coupon won</span><span class="landed">8 of 8 landed</span></div><div class="price mono" style="color:var(--text-primary)">1214.94<small>combined odds</small></div></section>
</div>
<div class="wrap slate">
<div class="overline" style="margin:4px 2px 8px">English Premier League · full time</div>
<article class="fx card"><div class="teams"><span>Arsenal</span><span class="score">2 – 1</span><span>Chelsea</span></div>
<div class="row3">{sel('Arsenal','1.90','Won · 19 pts','won')}{sel('Draw','3.75','Lost · Former member','lost')}{sel('Chelsea','4.30','Lost · Jo','lost')}</div>
<div class="row3" style="grid-template-columns:repeat(3,1fr)">{sel('BTTS Yes','1.80','Void · Ivan','void')}{sel('BTTS No','2.05','Won · Hana','won')}</div></article>
<p class="foot">Lens 06 mockup (DES-15). The result is the headline: "Coupon lost" 24/600 in --error-ink (5.62:1 dark / 5.02 light, 3:1 needed at this size), "Coupon won" in --success-ink (7.07 / 5.02); the price struck through in --text-secondary (6.99 / 7.56). Settled selections say Won / Lost / Void and who held them, never potential points. The full-time score (2 – 1) is text and needs a results source per fixture — the football section already has one; if it cannot be joined, drop the score and keep the marks.</p>
</div></div>
{tabbar('Coupon')}
</body></html>'''
Path(__file__).with_name('settled.html').write_text(html)
print('settled.html')
