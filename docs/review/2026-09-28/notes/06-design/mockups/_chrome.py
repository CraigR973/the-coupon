"""Header, tab bar and shared component CSS for the lens 06 mockups (phone + desktop)."""
TICKET = '<svg viewBox="0 0 40 28" width="34" height="24" aria-hidden="true"><rect x="1.5" y="1.5" width="37" height="25" rx="5" fill="none" stroke="var(--primary)" stroke-width="2.4"/><path d="M8 10h11M8 14h8M8 18h6" stroke="var(--primary)" stroke-width="2.4" stroke-linecap="round"/><path d="M27 4v20" stroke="var(--primary)" stroke-width="2" stroke-dasharray="2 3"/><circle cx="32.5" cy="14" r="2.6" fill="var(--primary)"/></svg>'
CSS = """
.hdr{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid var(--border)}
.hdr .in{height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 16px;max-width:1280px;margin:0 auto}
.brand{display:flex;align-items:center;gap:8px}
.word{font-family:'JetBrains Mono',monospace;font-weight:600;font-size:15px;letter-spacing:.28em;background:var(--wordmark-gradient-h, linear-gradient(90deg,#F0DDA6,#D4A24A 50%,#A77C2A));-webkit-background-clip:text;background-clip:text;color:transparent}
html.light .word{background:linear-gradient(90deg,#D9A968,#A77C2A 50%,#6E4F18);-webkit-background-clip:text;background-clip:text}
.av{width:32px;height:32px;border-radius:50%;background:var(--metal);color:var(--bg);display:grid;place-items:center;font:600 12px Outfit}
.icon-btn{width:32px;height:32px;display:grid;place-items:center;color:var(--text-secondary)}
.nav{display:none;gap:24px;font-size:14px;color:var(--text-secondary);margin-left:32px;flex:1}
.nav .on{color:var(--primary-ink)}
.tabbar{position:fixed;left:0;right:0;bottom:0;height:60px;background:var(--surface);border-top:1px solid var(--border);display:flex;z-index:5}
.tabbar a{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:12px;color:var(--text-muted);text-decoration:none;position:relative}
.tabbar a.on{color:var(--primary-ink)}
.tabbar a.on::before{content:'';position:absolute;top:0;left:22%;right:22%;height:2px;border-radius:2px;background:var(--primary)}
.tabbar svg{width:20px;height:20px}
.ctx{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 16px;border-bottom:1px solid var(--border);background:var(--bg)}
.league-btn{display:flex;align-items:center;gap:6px;font:600 15px Outfit;color:var(--text-primary);background:none;border:0;min-height:36px}
.league-btn span.c{color:var(--text-muted);font-size:13px}
.chip{display:inline-flex;align-items:center;height:24px;padding:0 9px;border-radius:999px;font:600 12px Outfit;border:1px solid var(--border-strong);color:var(--text-secondary)}
.chip.open{color:var(--primary-ink);border-color:var(--primary-ink)}
.chip.warn{color:var(--warning-ink);border-color:var(--warning-ink)}
.chip.lost{color:var(--error-ink);border-color:var(--error-ink)}
.chip.won{color:var(--success-ink);border-color:var(--success-ink)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg)}
@media(min-width:900px){.hdr .in{height:56px;padding:0 24px}.nav{display:flex}.tabbar{display:none}.mob{display:none!important}}
@media(max-width:899px){.desk{display:none!important}}
"""
def header(active='Coupon', initials='AL', name='Alice'):
    items = ''.join(f'<span class="{ "on" if x==active else ""}">{x}</span>' for x in ['Home','Coupon','Football','Leagues','Settings'])
    sun = '<svg viewBox="0 0 20 20" width="18" height="18"><circle cx="10" cy="10" r="3.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M4.3 15.7l1.4-1.4M14.3 5.7l1.4-1.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>'
    return f'''<header class="hdr"><div class="in"><span class="icon-btn mob">{sun}</span><div class="brand">{TICKET}<span class="word">THE COUPON</span></div><nav class="nav">{items}</nav><div style="display:flex;align-items:center;gap:12px"><span class="icon-btn desk">{sun}</span><span class="desk" style="font-size:14px;color:var(--text-secondary)">{name}</span><span class="av">{initials}</span></div></div></header>'''
def tabbar(active='Coupon'):
    I = {
     'Home':'<path d="M3 9l7-6 7 6v8H3z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
     'Coupon':'<rect x="2.5" y="5" width="15" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M13 5v10" stroke="currentColor" stroke-width="1.4" stroke-dasharray="1.5 2"/>',
     'Football':'<circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 6.5l3 2.2-1.1 3.5H8.1L7 8.7z" fill="currentColor"/>',
     'Leagues':'<path d="M6 3h8v4a4 4 0 0 1-8 0zM10 11v4M7 17h6M6 5H3.5a2.5 2.5 0 0 0 2.6 3M14 5h2.5a2.5 2.5 0 0 1-2.6 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
     'More':'<circle cx="4.5" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="15.5" cy="10" r="1.5" fill="currentColor"/>',
    }
    return '<nav class="tabbar mob">' + ''.join(f'<a class="{ "on" if k==active else ""}"><svg viewBox="0 0 20 20">{v}</svg>{k}</a>' for k,v in I.items()) + '</nav>'
