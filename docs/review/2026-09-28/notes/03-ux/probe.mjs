// Objective probes that axe cannot run (lens 03). Each section writes notes/03-ux/probe-<section>.json
// and prints a one-line verdict per measurement.
//
//   node probe.mjs reflow|zoom|targets|motion|contrast|gate
//
// reflow   320×720 and the WCAG 1.4.12 text-spacing override on every route: page overflow and
//          clipped content (the repo's own `clipped()` definition, prod-bundle-reflow.spec.ts).
// zoom     1280×800 at 200% = CSS viewport 640×400 at deviceScaleFactor 2: which chrome shows,
//          and how much height is left for content.
// targets  every visible interactive element at 390 and 1280: SC 2.5.8 (24px, with the spacing
//          and inline exceptions) and which primary actions miss 44px.
// motion   running animations / smooth scrollers with and without prefers-reduced-motion.
// contrast rendered-pixel contrast of specific text (UX-13, UX-18, UX-21): darkest-vs-mode pixel.
// gate     the mobile install gate over /login: is the page behind it hidden from AT?
import { writeFileSync } from 'node:fs';
import { chromium, newContext, settle, sessions, api, WEB, NOTES } from './lib.mjs';

const section = process.argv[2];
const S = sessions();
const bob = S.Bob.player.id;
const tables = (await api('/api/v1/football/tables')).json;
const team = tables[0].rows[0].team_id;
const teamPath = `/football/teams/${team}?competition=${tables[0].competition_id}&season=${tables[0].season}`;

const MEMBER_ROUTES = [
  '/', '/leagues/the-coupon/predictions', '/leagues/sunday-club/predictions', '/leagues/the-coupon/predictions/results',
  '/leagues/the-coupon/leaderboard', '/leagues/the-coupon/leaderboard?season=2025', `/leagues/the-coupon/players/${bob}`,
  '/profile', '/football', '/football?view=results', teamPath, '/settings', '/about', '/offline', '/leagues', '/leagues/new',
  '/leagues/discover', '/leagues/join',
  '/leagues/the-coupon/admin/members', '/leagues/the-coupon/admin/settings', '/leagues/the-coupon/admin/requests',
  '/leagues/the-coupon/admin/invites', '/leagues/the-coupon/admin/audit-log',
  '/admin/dashboard', '/admin/calendar', '/admin/players', '/admin/results', '/admin/sync', '/admin/invites', '/admin/leagues',
];
const PUBLIC_ROUTES = ['/login', '/register', '/forgot-pin', '/set-pin?name=Dana', '/join/REVIEWINVITE1', '/welcome'];
const out = {};
const lines = [];
const browser = await chromium.launch();

async function open(route, opts) {
  const persona = PUBLIC_ROUTES.includes(route) ? null : opts.persona ?? 'Alice';
  const ctx = await newContext(browser, { ...opts, persona });
  const page = await ctx.newPage();
  await page.goto(`${WEB}${route}`);
  await settle(page);
  return { ctx, page };
}

const CLIPPED = () => {
  const out = [];
  for (const el of Array.from(document.body.querySelectorAll('*'))) {
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    const hiddenX = style.overflowX === 'hidden' || style.overflowX === 'clip';
    const hiddenY = style.overflowY === 'hidden' || style.overflowY === 'clip';
    const cutX = hiddenX && el.scrollWidth > el.clientWidth + 1;
    const cutY = hiddenY && el.scrollHeight > el.clientHeight + 1;
    if (!cutX && !cutY) continue;
    if (el.classList.contains('sr-only')) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const text = (el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 60);
    out.push(`<${el.tagName.toLowerCase()} class="${String(el.className).slice(0, 80)}"> ${cutX ? 'X' : ''}${cutY ? 'Y' : ''} sw=${el.scrollWidth}/${el.clientWidth} sh=${el.scrollHeight}/${el.clientHeight} "${text}"`);
  }
  return out;
};
const TEXT_SPACING = `* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; } p { margin-bottom: 2em !important; }`;

if (section === 'reflow') {
  out.reflow = [];
  for (const route of [...PUBLIC_ROUTES, ...MEMBER_ROUTES]) {
    const { ctx, page } = await open(route, { width: 320, height: 720, theme: 'dark' });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const clipped = await page.evaluate(CLIPPED);
    await page.addStyleTag({ content: TEXT_SPACING });
    await page.waitForTimeout(300);
    const overflowTS = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const clippedTS = (await page.evaluate(CLIPPED)).filter((c) => !clipped.includes(c));
    out.reflow.push({ route, overflow, clipped, overflowTS, clippedTS });
    lines.push(`reflow ${route}: overflow320=${overflow} clipped=${clipped.length} | text-spacing overflow=${overflowTS} newlyClipped=${clippedTS.length}`);
    await ctx.close();
  }
}

if (section === 'zoom') {
  out.zoom = [];
  for (const route of ['/', '/leagues/the-coupon/predictions', '/leagues/the-coupon/leaderboard', '/login']) {
    for (const theme of ['dark']) {
      const ctx = await browser.newContext({ viewport: { width: 640, height: 400 }, deviceScaleFactor: 2, reducedMotion: 'reduce', serviceWorkers: 'block', colorScheme: theme });
      const s = S.Alice;
      await ctx.addInitScript((i) => {
        localStorage.setItem('coupon_theme', 'dark');
        if (!i.pub) {
          localStorage.setItem('coupon_access', i.a); localStorage.setItem('coupon_refresh', i.r);
          localStorage.setItem('coupon_player', i.p); localStorage.setItem(`coupon_notif_prompt_seen_${i.id}`, '1');
        }
      }, { pub: route === '/login', a: s.access_token, r: s.refresh_token, id: s.player.id,
        p: JSON.stringify({ id: s.player.id, displayName: s.player.display_name, role: s.player.role, timezone: s.player.timezone, oddsFormat: s.player.odds_format, avatarUrl: null }) });
      const page = await ctx.newPage();
      await page.goto(`${WEB}${route}`);
      await settle(page);
      const m = await page.evaluate(() => {
        const vis = (el) => el && getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().height > 0;
        const header = document.querySelector('header');
        const tab = document.querySelector('nav[aria-label="Primary"]');
        const mainNav = document.querySelector('nav[aria-label="Main navigation"]');
        const fixedTop = header && ['fixed', 'sticky'].includes(getComputedStyle(header).position) ? header.getBoundingClientRect().height : 0;
        const fixedBottom = vis(tab) && getComputedStyle(tab.closest('[class*="fixed"]') ?? tab).position !== 'static' ? tab.getBoundingClientRect().height : 0;
        return { innerWidth, innerHeight, headerH: header?.getBoundingClientRect().height ?? 0, headerPos: header ? getComputedStyle(header).position : null,
          desktopNav: vis(mainNav), tabBar: vis(tab), tabBarH: vis(tab) ? tab.getBoundingClientRect().height : 0,
          usable: innerHeight - fixedTop - fixedBottom, hScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth };
      });
      await page.screenshot({ path: `${NOTES}/zoom200-${route.replace(/\W+/g, '_') || 'home'}.png` });
      out.zoom.push({ route, ...m });
      lines.push(`zoom200 ${route}: ${JSON.stringify(m)}`);
      await ctx.close();
    }
  }
}

if (section === 'targets') {
  out.targets = [];
  const routes = [...PUBLIC_ROUTES, ...MEMBER_ROUTES];
  for (const width of [390, 1280]) {
    for (const route of routes) {
      const { ctx, page } = await open(route, { width, theme: 'dark', persona: route.includes('/predictions') && !route.includes('sunday') ? 'Carol' : 'Alice' });
      const r = await page.evaluate(() => {
        const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=tab], [role=switch], [role=checkbox], [role=menuitem], summary, [tabindex]:not([tabindex="-1"])';
        const els = [...document.querySelectorAll(sel)].filter((e) => {
          const cs = getComputedStyle(e);
          const b = e.getBoundingClientRect();
          return cs.visibility !== 'hidden' && cs.display !== 'none' && b.width > 0 && b.height > 0 && !e.closest('.sr-only') && !e.disabled;
        });
        const boxes = els.map((e) => ({ e, b: e.getBoundingClientRect() }));
        const name = (e) => (e.getAttribute('aria-label') || e.textContent || e.getAttribute('placeholder') || e.getAttribute('name') || '').replace(/\s+/g, ' ').trim().slice(0, 40);
        const inline = (e) => {
          if (e.tagName !== 'A') return false;
          const p = e.parentElement;
          if (!p) return false;
          const own = (p.textContent || '').replace(/\s+/g, ' ').trim();
          const mine = (e.textContent || '').replace(/\s+/g, ' ').trim();
          return getComputedStyle(e).display === 'inline' && own.length > mine.length + 10;
        };
        const small = [];
        for (const { e, b } of boxes) {
          if (b.width >= 24 && b.height >= 24) continue;
          if (inline(e)) continue;
          if (e.tagName === 'INPUT' && ['checkbox', 'radio'].includes(e.type) && e.closest('label')) {
            const lb = e.closest('label').getBoundingClientRect();
            if (lb.width >= 24 && lb.height >= 24) continue;
          }
          const cx = b.x + b.width / 2, cy = b.y + b.height / 2;
          // SC 2.5.8 spacing exception: a 24px circle on this target must not intersect another target or its circle
          const crowded = boxes.some(({ e: o, b: ob }) => {
            if (o === e || o.contains(e) || e.contains(o)) return false;
            const ox = ob.x + ob.width / 2, oy = ob.y + ob.height / 2;
            const oSmall = ob.width < 24 || ob.height < 24;
            const dx = Math.max(ob.x - cx, 0, cx - (ob.x + ob.width));
            const dy = Math.max(ob.y - cy, 0, cy - (ob.y + ob.height));
            const toRect = Math.hypot(dx, dy);
            return oSmall ? Math.hypot(ox - cx, oy - cy) < 24 : toRect < 12;
          });
          small.push({ name: name(e), tag: e.tagName, w: Math.round(b.width), h: Math.round(b.height), crowded });
        }
        const primary = boxes.filter(({ e }) => {
          const c = String(e.className);
          return /\bbg-primary\b|\bbg-accent\b/.test(c) || (e.dataset.testid || '').startsWith('selection-') || e.closest('nav[aria-label="Primary"]') || e.type === 'submit';
        }).map(({ e, b }) => ({ name: name(e), w: Math.round(b.width), h: Math.round(b.height) }));
        return { small, primaryUnder44: primary.filter((p) => p.h < 44 || p.w < 44), primaryCount: primary.length, total: boxes.length };
      });
      out.targets.push({ route, width, ...r });
      const fails = r.small.filter((s) => s.crowded);
      lines.push(`targets ${width} ${route}: ${r.total} targets; <24px ${r.small.length} (fail 2.5.8: ${fails.length} ${fails.map((f) => `"${f.name}" ${f.w}×${f.h}`).join(', ')}); primary <44: ${r.primaryUnder44.length}/${r.primaryCount}`);
      await ctx.close();
    }
  }
}

if (section === 'motion') {
  out.motion = [];
  for (const rm of ['no-preference', 'reduce']) {
    for (const route of ['/', '/leagues/the-coupon/predictions', '/leagues/the-coupon/leaderboard', '/login', '/welcome']) {
      const { ctx, page } = await open(route, { width: 390, theme: 'dark', reducedMotion: rm, persona: 'Carol' });
      await page.goto(`${WEB}${route}`);
      await page.waitForTimeout(150);
      const early = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running').map((a) => a.animationName || a.transitionProperty || a.constructor.name));
      await settle(page);
      const m = await page.evaluate(() => {
        const running = document.getAnimations().filter((a) => a.playState === 'running');
        const infinite = running.filter((a) => a.effect?.getTiming?.().iterations === Infinity).map((a) => a.animationName);
        const smooth = [document.documentElement, document.body, ...document.querySelectorAll('*')].filter((e) => getComputedStyle(e).scrollBehavior === 'smooth').length;
        return { running: running.map((a) => a.animationName || a.transitionProperty), infinite, smooth };
      });
      // a route change (PageTransition) — navigate by the tab bar
      let transition = null;
      const link = page.locator('nav[aria-label="Primary"] a').nth(1);
      if (await link.count()) {
        await link.click();
        await page.waitForTimeout(60);
        transition = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running').map((a) => `${a.animationName || a.transitionProperty}:${a.effect?.getTiming?.().duration}`));
      }
      out.motion.push({ rm, route, early, ...m, transition });
      lines.push(`motion ${rm} ${route}: early=${early.length} running=${m.running.length} infinite=${m.infinite.length} smooth=${m.smooth} onNav=${transition?.length ?? '-'} ${JSON.stringify(transition)}`);
      await ctx.close();
    }
  }
}

if (section === 'contrast') {
  // Rendered-pixel contrast: screenshot each element; background = the modal colour;
  // text = the pixel with the greatest contrast to it. Reported alongside axe's computed figure.
  const scorer = await (await browser.newContext()).newPage();
  await scorer.setContent('<canvas id=c></canvas>');
  const measure = (b64) => scorer.evaluate(async (s) => {
    const i = await new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.src = 'data:image/png;base64,' + s; });
    const c = document.getElementById('c'); c.width = i.width; c.height = i.height;
    const x = c.getContext('2d'); x.drawImage(i, 0, 0);
    const d = x.getImageData(0, 0, c.width, c.height).data;
    const count = new Map();
    for (let k = 0; k < d.length; k += 4) { const key = (d[k] << 16) | (d[k + 1] << 8) | d[k + 2]; count.set(key, (count.get(key) || 0) + 1); }
    const bg = [...count.entries()].sort((a, b) => b[1] - a[1])[0][0];
    const rgb = (v) => [(v >> 16) & 255, (v >> 8) & 255, v & 255];
    const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    const L = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    const lb = L(rgb(bg));
    let best = 1, fg = bg;
    for (const key of count.keys()) { const l = L(rgb(key)); const cr = (Math.max(l, lb) + 0.05) / (Math.min(l, lb) + 0.05); if (cr > best) { best = cr; fg = key; } }
    const hex = (v) => '#' + v.toString(16).padStart(6, '0');
    return { bg: hex(bg), fg: hex(fg), ratio: Math.round(best * 100) / 100 };
  }, b64);
  const targets = [
    { id: 'UX-18 locked selection caption ("win N pts")', route: '/leagues/sunday-club/predictions', persona: 'Alice', sel: '[data-testid^="selection-"][disabled] .text-caption' },
    { id: 'UX-18 locked selection odds', route: '/leagues/sunday-club/predictions', persona: 'Alice', sel: '[data-testid^="selection-"][disabled] .font-mono.text-xs' },
    { id: 'UX-21 player-profile lost row text', route: `/leagues/the-coupon/players/${bob}?season=2025`, persona: 'Alice', sel: '.opacity-60 p' },
    { id: 'UX-21 player-profile lost badge', route: `/leagues/the-coupon/players/${bob}?season=2025`, persona: 'Alice', sel: '.opacity-60 .bg-error\\/20' },
    { id: 'UX-13 team-season kick-off time', route: teamPath, persona: 'Alice', sel: '[data-testid^="team-match-"] .w-16' },
    { id: 'UX-13 season strip "now" badge', route: '/leagues/the-coupon/leaderboard?season=2025', persona: 'Alice', sel: 'button span.uppercase:text-is("now")' },
  ];
  out.contrast = [];
  for (const t of targets) {
    for (const theme of ['light', 'dark']) {
      for (const width of [390]) {
        const { ctx, page } = await open(t.route, { width, theme, persona: t.persona });
        const loc = page.locator(t.sel);
        const n = await loc.count();
        const res = [];
        for (let i = 0; i < Math.min(n, 3); i++) {
          const el = loc.nth(i);
          await el.scrollIntoViewIfNeeded().catch(() => {});
          const buf = await el.screenshot().catch(() => null);
          if (!buf) continue;
          const m = await measure(buf.toString('base64'));
          res.push({ text: (await el.innerText().catch(() => '')).slice(0, 30), ...m });
        }
        out.contrast.push({ ...t, theme, width, found: n, res });
        lines.push(`contrast ${t.id} ${theme}: found ${n} ${res.map((r) => `"${r.text}" ${r.fg} on ${r.bg} = ${r.ratio}:1`).join('; ')}`);
        await ctx.close();
      }
    }
  }
}

if (section === 'gate') {
  const ctx = await newContext(browser, { width: 390, theme: 'dark', persona: null, mobileUA: true });
  const page = await ctx.newPage();
  await page.goto(`${WEB}/login`);
  await settle(page);
  const m = await page.evaluate(() => {
    const overlay = document.querySelector('.fixed.inset-0.z-\\[70\\]');
    const form = document.querySelector('form');
    const hiddenFromAT = (el) => { for (let e = el; e; e = e.parentElement) { if (e.getAttribute?.('aria-hidden') === 'true' || e.inert) return true; } return false; };
    return { overlay: !!overlay, overlayRole: overlay?.getAttribute('role') ?? null, overlayModal: overlay?.getAttribute('aria-modal') ?? null,
      overlayInMain: !!overlay?.closest('main'), overlayLandmarks: overlay ? overlay.querySelectorAll('main,[role=main],section[aria-label],nav,header,footer').length : 0,
      formPresent: !!form, formHiddenFromAT: form ? hiddenFromAT(form) : null, h1s: [...document.querySelectorAll('h1')].map((h) => h.textContent.trim()) };
  });
  // Can Tab reach the hidden login form behind the overlay?
  const reached = [];
  for (let i = 0; i < 25; i++) {
    await page.keyboard.press('Tab');
    const f = await page.evaluate(() => { const e = document.activeElement; if (!e || e === document.body) return null;
      const r = e.getBoundingClientRect(); const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return { tag: e.tagName, name: (e.getAttribute('aria-label') || e.textContent || e.getAttribute('placeholder') || '').trim().slice(0, 30), coveredByOverlay: !!(top && !e.contains(top) && top.closest('.fixed.inset-0')) }; });
    if (f) reached.push(f);
  }
  out.gate = { ...m, tabStops: reached };
  lines.push(`gate: ${JSON.stringify(m)}; tab stops covered by overlay: ${reached.filter((r) => r.coveredByOverlay).map((r) => r.tag + ' ' + r.name).join(' | ')}`);
  await ctx.close();
}

writeFileSync(`${NOTES}/probe-${section}.json`, JSON.stringify(out, null, 1));
writeFileSync(`${NOTES}/probe-${section}.txt`, lines.join('\n') + '\n');
console.log(lines.join('\n'));
await browser.close();
