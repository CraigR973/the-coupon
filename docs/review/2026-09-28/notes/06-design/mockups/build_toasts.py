from _base import HEAD
from pathlib import Path
ICON = {
 'success': '<path d="M5 10.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
 'warning': '<path d="M10 3.5l7.5 13h-15z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M10 8.5v3.5M10 14.6v.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
 'error': '<circle cx="10" cy="10" r="7.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M10 6.2v4.6M10 13.6v.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
 'info': '<path d="M4 13.5a4 4 0 0 1 1-7.9 5 5 0 0 1 9.6 1.4A3.3 3.3 0 0 1 14.5 14H6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M3 3l14 14" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
}
INK = {'success':'var(--success-ink)','warning':'var(--warning-ink)','error':'var(--error-ink)','info':'var(--primary-ink)'}
T = [
 ('success','Grabbed Arsenal @ 1.90','Win 19 pts if it lands. You can change it until 14:30.',None),
 ('warning','Someone got there first','The Draw is taken now — pick another.','Refresh the card'),
 ('warning','That price moved to 4.60','It was 4.30 when you tapped. Take the new price, or pick something else.','Take 4.60'),
 ('error','Your pick wasn’t saved','Too many picks are being made in your league right now. Try again in a few minutes.','Try again'),
 ('info','Saved on this phone','You’re offline — we’ll send Forfar Athletic @ 2.40 the moment you’re back.',None),
]
def toast(kind,title,body,action):
    a = f'<button class="act">{action}</button>' if action else ''
    return f'''<div class="toast" style="--ink:{INK[kind]}"><span class="ic"><svg viewBox="0 0 20 20" width="20" height="20">{ICON[kind]}</svg></span>
<div class="tx"><div class="tt">{title}</div><div class="bd">{body}</div></div>{a}<button class="x" aria-label="Dismiss">×</button></div>'''
def panel(theme):
    return f'''<section class="panel {theme}"><div class="overline">{'Dark' if theme=='dark' else 'Light'} — proposed (app tokens)</div>{''.join(toast(*t) for t in T)}
<div class="overline" style="margin-top:18px">{'Dark' if theme=='dark' else 'Light'} — today (Sonner light palette + forced title)</div>
<div class="toast before" style="background:#FFFCF0;border-color:#FDF5D3"><span class="ic" style="color:#DC7609"><svg viewBox="0 0 20 20" width="20" height="20">{ICON['warning']}</svg></span><div class="tx"><div class="tt" style="color:var(--text-primary)">Someone in your league just grabbed that selection — pick another.</div></div><button class="act" style="background:#171717;color:#fff">Refresh the card</button></div></section>'''
html = f'''<!doctype html><html class="dark"><head>{HEAD}<title>Toasts on tokens</title><style>
body{{padding:16px}}
h1{{font-size:20px;font-weight:600;margin-bottom:4px}}
.lead{{font-size:13px;color:var(--text-secondary);margin-bottom:16px;max-width:760px}}
.grid{{display:grid;gap:16px}}
@media(min-width:900px){{.grid{{grid-template-columns:1fr 1fr}}}}
.panel{{background:var(--bg);color:var(--text-primary);padding:16px;border-radius:var(--radius-lg);border:1px solid var(--border)}}
.panel.dark{{{''}}}
.toast{{display:flex;gap:12px;align-items:flex-start;background:var(--surface-overlay);border:1px solid var(--border);border-left:3px solid var(--ink);
 border-radius:var(--radius-md);padding:12px 12px 12px 12px;margin-top:10px;box-shadow:var(--shadow-lg);position:relative;max-width:420px}}
.ic{{color:var(--ink);flex:none;margin-top:1px}}
.tx{{flex:1;min-width:0}}
.tt{{font-size:14px;font-weight:600;line-height:20px;color:var(--text-primary)}}
.bd{{font-size:13px;line-height:18px;color:var(--text-secondary);margin-top:2px}}
.act{{flex:none;align-self:center;font:600 13px Outfit;background:var(--primary);color:var(--on-primary);border:0;border-radius:10px;padding:0 12px;height:36px;margin-left:4px}}
.x{{position:absolute;top:6px;right:8px;background:none;border:0;color:var(--text-muted);font-size:16px;line-height:1;display:none}}
.note b{{color:var(--text-secondary)}}
</style></head><body>
<h1>Toasts on the app's own tokens (DES-10)</h1>
<p class="lead">Fill <code>--surface-overlay</code>, 3 px edge and icon in the semantic <code>-ink</code>, title <code>--text-primary</code>, body <code>--text-secondary</code>, action <code>--primary</code>/<code>--on-primary</code>. The title says what happened, the body what to do. Contrast (contrast.txt): title 13.17:1 dark / 17.79:1 light; body 5.65 / 7.56; edge + icon 4.54–6.75 dark, 5.02–5.07 light (3:1 needed); action 7.62 / 5.13. Today's dark title: 1.01–1.07:1.</p>
<div class="grid">
<div class="dark-wrap">{panel('dark')}</div>
<div class="light-wrap">{panel('light')}</div>
</div>
<script>
// Render the second panel in the light palette regardless of the page theme: copy html.light's variables onto it.
(function(){{var s=[...document.styleSheets[0].cssRules].find(r=>r.selectorText==='html.light');var d=[...document.styleSheets[0].cssRules].find(r=>r.selectorText===':root, html.dark');
 document.querySelector('.panel.light').style.cssText=s.style.cssText;document.querySelector('.panel.dark').style.cssText=d.style.cssText;}})();
</script>
</body></html>'''
Path(__file__).with_name('toasts.html').write_text(html)
print('toasts.html')
