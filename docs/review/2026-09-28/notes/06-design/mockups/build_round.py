from pathlib import Path
from _base import HEAD
from _chrome import CSS, header, tabbar
def sel(label, price, meta, state=''):
    return f'<button class="sel {state}"><span class="lb">{label}</span><span class="pr mono">{price}</span><span class="mt">{meta}</span></button>'
def form(s):
    return ''.join(f'<i class="f {c}">{c}</i>' for c in s)
fixture1 = f'''<article class="fx card">
 <div class="fxh"><div class="teams"><div><b>Arsenal</b><span class="pos mono">1st</span>{form('WDWW')}</div><div><b>Chelsea</b><span class="pos mono">2nd</span>{form('DWWL')}</div></div><div class="ko mono">15:00</div></div>
 <div class="mk">Match result</div>
 <div class="row3">{sel('Arsenal','1.90','Win 19 pts')}{sel('Draw','3.75','Bob has it','taken')}{sel('Chelsea','4.30','Win 43 pts')}</div>
 <div class="mk">Both teams to score</div>
 <div class="row2">{sel('Yes','1.80','Win 18 pts')}{sel('No','2.05','Win 21 pts')}</div>
</article>'''
fixture2 = f'''<article class="fx card">
 <div class="fxh"><div class="teams"><div><b>Forfar Athletic</b><span class="pos mono">1st</span>{form('WWL')}</div><div><b>Brechin City</b><span class="pos mono">2nd</span>{form('WDWD')}</div></div><div class="ko mono">15:00</div></div>
 <div class="mk">Match result</div>
 <div class="row3">{sel('Forfar','2.40','Win 24 pts')}{sel('Draw','3.20','Carol has it','taken')}{sel('Brechin','3.10','Win 31 pts')}</div>
</article>'''
status = '''<div class="status card"><div class="s1"><span class="chip warn">Pick required</span><span class="lock mono">Locks in 2d 20h 13m</span></div><div class="s2">3 of 8 picked · 5 to go</div></div>'''
coupon = '''<div class="coupon card"><div class="ch"><span class="overline">The coupon</span><span class="mono cp">14.51</span></div>
<ol class="legs"><li><span>Brechin City</span><span class="who">Bob</span><span class="mono">3.10</span></li><li><span>Yes · BTTS</span><span class="who">Carol</span><span class="mono">1.95</span></li><li><span>Both teams score</span><span class="who">Ivan</span><span class="mono">1.80</span></li></ol>
<div class="cf">3-fold · frozen at pick time</div></div>'''
html = f'''<!doctype html><html class="dark"><head>{HEAD}<title>Pick screen</title><style>{CSS}
body{{padding-bottom:76px}}
.wrap{{max-width:1200px;margin:0 auto}}
.main{{padding:12px 16px}}
.status{{padding:12px 14px;margin-bottom:14px}}
.s1{{display:flex;justify-content:space-between;align-items:center}}
.lock{{font-size:13px;color:var(--text-secondary)}}
.s2{{font-size:14px;color:var(--text-secondary);margin-top:8px}}
.comp{{display:flex;justify-content:space-between;align-items:baseline;margin:6px 2px 8px}}
.comp .d{{font-size:13px;color:var(--text-muted)}}
.fx{{padding:14px;margin-bottom:12px}}
.fxh{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}}
.teams div{{display:flex;align-items:center;gap:6px;font-size:16px;line-height:26px}}
.teams b{{font-weight:600}}
.pos{{font-size:12px;color:var(--text-muted);margin-left:2px}}
.f{{font:600 12px 'JetBrains Mono';font-style:normal;width:16px;text-align:center;color:var(--text-muted)}}
.f.W{{color:var(--success-ink)}}.f.L{{color:var(--error-ink)}}
.ko{{font-size:13px;color:var(--text-secondary)}}
.mk{{font-size:12px;color:var(--text-muted);margin:10px 0 6px;font-weight:600}}
.row3,.row2{{display:grid;gap:8px}}.row3{{grid-template-columns:repeat(3,1fr)}}.row2{{grid-template-columns:repeat(3,1fr)}}
.sel{{min-height:64px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:1px;padding:8px 10px;border-radius:12px;background:var(--surface-elevated);border:1px solid var(--border);color:var(--text-primary);text-align:left;font-family:Outfit}}
.sel .lb{{font-size:14px;line-height:18px;color:var(--text-secondary)}}
.sel .pr{{font-size:17px;line-height:22px;color:var(--text-primary)}}
.sel .mt{{font-size:12px;line-height:16px;color:var(--text-muted)}}
.sel.taken{{background:transparent;border-style:dashed}}
.sel.taken .pr{{color:var(--text-muted);text-decoration:line-through;text-decoration-thickness:1px}}
.coupon{{padding:14px;margin-top:6px}}
.ch{{display:flex;justify-content:space-between;align-items:baseline}}
.cp{{font-size:22px}}
.legs{{list-style:none;margin:10px 0 6px}}
.legs li{{display:grid;grid-template-columns:1fr auto 52px;gap:8px;font-size:14px;padding:7px 0;border-top:1px solid var(--border)}}
.legs .who{{color:var(--text-muted)}}.legs .mono{{text-align:right}}
.cf{{font-size:12px;color:var(--text-muted)}}
.side{{display:none}}
@media(min-width:900px){{
 body{{padding-bottom:0}}
 .ctx{{max-width:1200px;margin:0 auto;border:0;padding:16px 24px 8px;background:none}}
 .grid .wrap{{max-width:none;margin:0}}.grid{{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:24px;padding:0 24px}}
 .main{{padding:8px 0}}
 .side{{display:block;position:sticky;top:72px;align-self:start;padding-top:8px}}
 .main .status,.main .coupon{{display:none}}
 .fx{{padding:16px 18px}}
 .row2{{grid-template-columns:repeat(3,1fr)}}
 .sel{{min-height:60px}}
}}
.note{{position:relative;margin-top:10px}}
</style></head><body>
{header('Coupon')}
<div class="ctx"><button class="league-btn">The Coupon Test League <span class="c">▾</span></button><div style="display:flex;gap:8px;align-items:center"><span class="mono" style="font-size:13px;color:var(--text-secondary)">GW 1b</span><span class="chip open">Open</span></div></div>
<div class="wrap grid">
<main class="main">
{status}
<div class="comp"><span class="overline">English Premier League</span><span class="d">Sat 1 Aug</span></div>
{fixture1}
<div class="comp"><span class="overline">Scottish League Two</span><span class="d">Sat 1 Aug</span></div>
{fixture2}
{coupon}
<p class="note">Lens 06 mockup (DES-13, DES-14). One context row replaces the breadcrumb, the "Your leagues" card and the Current round / Season pills; the pick count appears once; the price is 17/600 tabular in --text-primary (16.30:1 dark, 17.79:1 light on --surface-elevated: 14.73 / 16.00); label 14, meta 12. Taken selections are dashed with the price struck, and say who holds them. Tab bar: solid --surface, the marker under the active tab, "Football".</p>
</main>
<aside class="side">{status}{coupon}</aside>
</div>
{tabbar('Coupon')}
</body></html>'''
Path(__file__).with_name('round.html').write_text(html)
print('round.html')
