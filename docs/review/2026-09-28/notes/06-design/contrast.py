"""WCAG 2.x contrast of every colour lens 06 proposes, on every surface it sits on, both themes.

Token values are read from apps/web/src/index.css as of this review (dark = :root/html.dark,
light = html.light). Composites (a token at N% over a surface) are alpha-blended in sRGB,
which is what the browser does for `color-mix`-free rgba fills. Output: contrast.txt.
Text needs 4.5:1 (3:1 at >= 24px or >= 18.66px bold); non-text UI (icons, bars, borders that
carry meaning) needs 3:1.
"""
import re
from pathlib import Path

CSS = Path("/Users/craigrobinson/the-coupon/apps/web/src/index.css").read_text()
def block(sel):
    i = CSS.index(sel); j = CSS.index("}", CSS.index("{", i))
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", CSS[i:j]))
T = {"dark": block(":root,\n  html.dark {"), "light": block("html.light {")}

def rgb(h): h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
def hexs(c): return "#%02X%02X%02X" % c
def lum(c):
    f = lambda v: (v/255)/12.92 if v/255 <= 0.03928 else ((v/255 + 0.055)/1.055) ** 2.4
    r, g, b = c; return 0.2126*f(r) + 0.7152*f(g) + 0.0722*f(b)
def cr(a, b):
    x, y = sorted([lum(a), lum(b)], reverse=True); return (x + 0.05)/(y + 0.05)
def over(fg, a, bg): return tuple(round(fg[i]*a + bg[i]*(1-a)) for i in range(3))

out = []
def row(group, theme, what, fg, bg, need):
    r = cr(fg, bg)
    out.append(f"{group:34s} {theme:5s} {what:58s} {hexs(fg)} on {hexs(bg)}  {r:5.2f}:1  need {need}  {'PASS' if r >= need else 'FAIL'}")
    return r

for th in ("dark", "light"):
    t = {k: rgb(v) for k, v in T[th].items()}
    surfaces = {k: t[k] for k in ("bg", "surface", "surface-elevated", "surface-overlay")}
    # 1. Toast on app tokens (DES-10 fix)
    for name in ("success", "warning", "error", "primary"):
        pass
    row("1 toast title", th, "--text-primary on --surface-overlay", t["text-primary"], t["surface-overlay"], 4.5)
    row("1 toast body/description", th, "--text-secondary on --surface-overlay", t["text-secondary"], t["surface-overlay"], 4.5)
    for ink in ("success-ink", "warning-ink", "error-ink", "primary-ink"):
        row("1 toast icon + 3px edge", th, f"--{ink} on --surface-overlay (non-text)", t[ink], t["surface-overlay"], 3.0)
    row("1 toast action button", th, "--on-primary on --primary", t["on-primary"], t["primary"], 4.5)
    row("1 toast action (secondary)", th, "--text-primary on --surface-elevated", t["text-primary"], t["surface-elevated"], 4.5)
    # today's failure, for the record
    sonner_light = {"success": (236, 253, 243), "warning": (255, 252, 240), "error": (255, 240, 240)}
    for k, bg in sonner_light.items():
        row("1 TODAY (measured)", th, f"--text-primary on Sonner light {k} bg", t["text-primary"], bg, 4.5)
    # 2. Tints once opacity modifiers compile (DES-11)
    for s in ("bg", "surface", "surface-elevated"):
        comp = over(t["primary"], 0.15, t[s])
        row("2 active pill bg-primary/15", th, f"--primary-ink on primary@15% over --{s}", t["primary-ink"], comp, 4.5)
        row("2 active pill label", th, f"--text-primary on primary@15% over --{s}", t["text-primary"], comp, 4.5)
    for s in ("surface", "surface-elevated"):
        comp = over(t["success"], 0.20, t[s])
        row("2 picked button bg-success/20", th, f"--success-ink on success@20% over --{s}", t["success-ink"], comp, 4.5)
        row("2 picked button caption", th, f"--text-muted on success@20% over --{s}", t["text-muted"], comp, 4.5)
        comp = over(t["error"], 0.10, t[s])
        row("2 error panel bg-error/10", th, f"--error-ink on error@10% over --{s}", t["error-ink"], comp, 4.5)
        row("2 error panel body", th, f"--text-secondary on error@10% over --{s}", t["text-secondary"], comp, 4.5)
        comp = over(t["warning"], 0.10, t[s])
        row("2 warning panel bg-warning/10", th, f"--warning-ink on warning@10% over --{s}", t["warning-ink"], comp, 4.5)
    # header / tab bar at 90/95% over the worst content behind them (text-primary glyphs)
    for a, where in ((0.90, "header bg-surface/90"), (0.95, "tab bar bg-surface/95")):
        worst = over(t["surface"], a, t["text-primary"])
        row(f"2 {where}", th, "--text-secondary on surface@%d%% over --text-primary" % int(a*100), t["text-secondary"], worst, 4.5)
        row(f"2 {where}", th, "--primary-ink (active tab) on the same", t["primary-ink"], worst, 4.5)
    # 3. Price as hero + settled marks (DES-14, DES-15)
    for s in ("surface", "surface-elevated"):
        row("3 price 16px/600", th, f"--text-primary on --{s}", t["text-primary"], t[s], 4.5)
        row("3 settled mark WON", th, f"--success-ink on --{s}", t["success-ink"], t[s], 4.5)
        row("3 settled mark LOST", th, f"--error-ink on --{s}", t["error-ink"], t[s], 4.5)
        row("3 settled mark VOID / muted pts", th, f"--text-muted on --{s}", t["text-muted"], t[s], 4.5)
    # 4. Settled coupon headline (DES-15): outcome word at 24px/600 = large text (3:1), price muted
    row("4 coupon headline LOST 24px", th, "--error-ink on --surface", t["error-ink"], t["surface"], 3.0)
    row("4 coupon headline WON 24px", th, "--success-ink on --surface", t["success-ink"], t["surface"], 3.0)
    row("4 coupon price (struck) 20px", th, "--text-secondary on --surface", t["text-secondary"], t["surface"], 4.5)
    # 5. Standings rank medals as a 3px bar (non-text) and rank numerals in ink
    for m in ("gold", "silver", "bronze"):
        row("5 medal bar 3px", th, f"--{m} on --surface (non-text)", t[m], t["surface"], 3.0)
    row("5 rank numeral 1", th, "--gold-ink on --surface", t["gold-ink"], t["surface"], 4.5)
    row("5 rank numeral 3", th, "--bronze-ink on --surface", t["bronze-ink"], t["surface"], 4.5)
    row("5 rank numeral 2 (proposed --silver-ink = --text-secondary)", th, "--text-secondary on --surface", t["text-secondary"], t["surface"], 4.5)
    row("5 points 17px/600", th, "--text-primary on --surface", t["text-primary"], t["surface"], 4.5)
    row("5 own row tint primary@8%", th, "--text-primary on primary@8% over --surface", t["text-primary"], over(t["primary"], 0.08, t["surface"]), 4.5)
    row("5 own row name", th, "--primary-ink on primary@8% over --surface", t["primary-ink"], over(t["primary"], 0.08, t["surface"]), 4.5)
    # 6. Offline banner on tokens (DES-21)
    comp = over(t["warning"], 0.12, t["bg"])
    row("6 offline banner", th, "--text-primary on warning@12% over --bg", t["text-primary"], comp, 4.5)
    row("6 offline banner icon", th, "--warning-ink on warning@12% over --bg (non-text)", t["warning-ink"], comp, 3.0)
    # 7. League switcher compact strip (DES-13): chip text on surface-elevated
    row("7 league chip (inactive)", th, "--text-secondary on --surface-elevated", t["text-secondary"], t["surface-elevated"], 4.5)
    row("7 league chip (active)", th, "--on-primary on --primary", t["on-primary"], t["primary"], 4.5)
    out.append("")

fails = [l for l in out if l.endswith("FAIL")]
hdr = f"lens 06 contrast — {len([l for l in out if l])} pairs, {len(fails)} FAIL (the 'TODAY (measured)' rows are the defect, not a proposal)\n"
Path(__file__).with_name("contrast.txt").write_text(hdr + "\n".join(out) + "\n")
print(hdr); print("\n".join(fails))


# ── Max tint alpha that keeps each tinted pairing at >= 4.5:1 (the DES-11 fix must cap alphas) ──
lines = ["", "max tint alpha keeping >= 4.5:1 (search in 1% steps)"]
cases = [
    ("primary", "primary-ink", ("bg", "surface", "surface-elevated")),
    ("success", "success-ink", ("surface", "surface-elevated")),
    ("success", "text-muted", ("surface", "surface-elevated")),
    ("error", "error-ink", ("surface", "surface-elevated")),
    ("warning", "warning-ink", ("surface", "surface-elevated")),
]
for th in ("dark", "light"):
    t = {k: rgb(v) for k, v in T[th].items()}
    for fill, ink, surfs in cases:
        for s in surfs:
            best = 0
            for pct in range(0, 41):
                if cr(t[ink], over(t[fill], pct/100, t[s])) >= 4.5: best = pct
                else: break
            lines.append(f"  {th:5s} --{ink} on {fill}@N% over --{s}: max N = {best}%")
    # header over worst content: max transparency for active tab
    for a in range(80, 101):
        if cr(t["primary-ink"], over(t["surface"], a/100, t["text-primary"])) >= 4.5:
            lines.append(f"  {th:5s} header/tab bar: --primary-ink passes over the worst content from surface@{a}%"); break
with open(Path(__file__).with_name("contrast.txt"), "a") as f: f.write("\n".join(lines) + "\n")
print("\n".join(lines))
