"""Shared head for lens 06 mockups: the app's own tokens, read from apps/web/src/index.css at
build time and inlined, plus its self-hosted fonts by relative path. Run build.py to regenerate."""
import re
from pathlib import Path
CSS = Path("/Users/craigrobinson/the-coupon/apps/web/src/index.css").read_text()
def block(sel):
    i = CSS.index(sel); j = CSS.index("}", CSS.index("{", i))
    return "\n".join(l.strip() for l in CSS[i:j].splitlines() if re.match(r"\s*--[\w-]+:\s*[^;]+;", l))
DARK = block(":root,\n  html.dark {")
LIGHT = block("html.light {")
F = "../../../../../../apps/web/public/fonts"
HEAD = f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@font-face{{font-family:Outfit;font-weight:400;src:url('{F}/outfit-400.woff2') format('woff2')}}
@font-face{{font-family:Outfit;font-weight:600;src:url('{F}/outfit-600.woff2') format('woff2')}}
@font-face{{font-family:'JetBrains Mono';font-weight:600;src:url('{F}/jetbrains-mono-600.woff2') format('woff2')}}
:root,html.dark{{{DARK}
--radius-sm:10px;--radius-md:14px;--radius-lg:18px;color-scheme:dark}}
html.light{{{LIGHT}
color-scheme:light}}
*{{box-sizing:border-box;margin:0;padding:0;border-color:var(--border)}}
html,body{{background:var(--bg);color:var(--text-primary);font-family:Outfit,system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
.mono{{font-family:'JetBrains Mono',ui-monospace,monospace;font-weight:600;font-variant-numeric:tabular-nums}}
.overline{{font-family:'JetBrains Mono',monospace;font-weight:600;font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--text-muted)}}
.note{{font:12px/1.4 Outfit;color:var(--text-muted);padding:10px 16px;border-top:1px dashed var(--border-strong)}}
</style>
<script>if(location.search.includes('light'))document.documentElement.className='light';else document.documentElement.className='dark'</script>"""
