// Shared Playwright helpers for lens 06 (copied from lens 03 lib.mjs; ports, notes dir and sessions file changed). Run scripts with Node 24:
//   . ~/.nvm/nvm.sh && nvm use 24 --silent && node docs/review/2026-09-28/notes/06-design/<script>.mjs
// Chromium only (WebKit cannot be installed on this Mac). The bundle on :4360 is the
// production build pointed at the local API on :8160 (harness web.sh).
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { chromium } from '/Users/craigrobinson/the-coupon/apps/web/node_modules/@playwright/test/index.mjs';

export { chromium };
export const WEB = 'http://127.0.0.1:4360';
export const API = 'http://127.0.0.1:8160';
export const ROOT = '/Users/craigrobinson/the-coupon';
export const NOTES = `${ROOT}/docs/review/2026-09-28/notes/06-design`;
export const SHOTS = `${ROOT}/docs/review/2026-09-28/screenshots`;
export const SCRATCH =
  '/private/tmp/claude-501/-Users-craigrobinson-the-coupon/3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad';
export const AXE_PATH = `${ROOT}/apps/web/node_modules/axe-core/axe.min.js`;
export const WIDTHS = { 390: { width: 390, height: 844 }, 1280: { width: 1280, height: 800 } };

export function sessions() {
  return JSON.parse(readFileSync(`${SCRATCH}/design-sessions.json`, 'utf8'));
}

/** The login response's player, in the camelCase shape `lib/tokens.ts` stores. */
function storedPlayer(p) {
  return {
    id: p.id,
    displayName: p.display_name,
    role: p.role,
    timezone: p.timezone,
    oddsFormat: p.odds_format,
    avatarUrl: p.avatar_url,
  };
}

/**
 * A fresh context: theme and session seeded before first paint (ThemeContext and
 * AuthContext both read localStorage during their first render), the notifications
 * prompt marked seen, service workers blocked, deviceScaleFactor 1.
 */
export async function newContext(browser, opts = {}) {
  const {
    width = 390,
    theme = 'dark',
    persona = null,
    reducedMotion = 'reduce',
    mobileUA = false,
    extraInit = null,
  } = opts;
  const vp = WIDTHS[width] ?? { width, height: opts.height ?? 800 };
  const ctxOpts = {
    viewport: { width: vp.width, height: opts.height ?? vp.height },
    deviceScaleFactor: 1,
    reducedMotion,
    colorScheme: theme,
    serviceWorkers: 'block',
  };
  if (mobileUA) {
    ctxOpts.userAgent =
      'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36';
    ctxOpts.isMobile = true;
    ctxOpts.hasTouch = true;
  }
  const ctx = await browser.newContext(ctxOpts);
  let init = { theme };
  if (persona) {
    const s = sessions()[persona];
    init = {
      theme,
      access: s.access_token,
      refresh: s.refresh_token,
      player: JSON.stringify(storedPlayer(s.player)),
      pid: s.player.id,
    };
  }
  await ctx.addInitScript((i) => {
    try {
      if (!sessionStorage.getItem('__ux_init')) {
        localStorage.setItem('coupon_theme', i.theme);
        if (i.access) {
          localStorage.setItem('coupon_access', i.access);
          localStorage.setItem('coupon_refresh', i.refresh);
          localStorage.setItem('coupon_player', i.player);
          localStorage.setItem(`coupon_notif_prompt_seen_${i.pid}`, '1');
        }
        sessionStorage.setItem('__ux_init', '1');
      }
    } catch {
      /* about:blank */
    }
  }, init);
  if (extraInit) await ctx.addInitScript(extraInit);
  return ctx;
}

/** Wait for the app to settle: network idle-ish, no skeletons, fonts loaded. */
export async function settle(page, { ready = null, timeout = 15000, allowSkeleton = false } = {}) {
  try {
    await page.waitForLoadState('networkidle', { timeout });
  } catch {
    /* long-poll free app; fall through */
  }
  if (ready) await page.locator(ready).first().waitFor({ state: 'visible', timeout });
  if (!allowSkeleton) {
    await page
      .waitForFunction(() => !document.querySelector('[data-skeleton], .animate-shimmer, [aria-busy="true"]'), null, {
        timeout: 8000,
      })
      .catch(() => {});
  }
  await page.evaluate(() => document.fonts && document.fonts.ready);
  await page.waitForTimeout(250);
}

export async function runAxe(page, options = {}) {
  const has = await page.evaluate(() => typeof window.axe !== 'undefined');
  if (!has) await page.addScriptTag({ path: AXE_PATH });
  return page.evaluate(async (o) => {
    const r = await window.axe.run(document, o);
    const slim = (list) =>
      list.map((v) => ({
        id: v.id,
        impact: v.impact,
        nodes: v.nodes.length,
        targets: v.nodes.slice(0, 8).map((n) => ({
          target: n.target.join(' '),
          summary: (n.failureSummary || '').slice(0, 300),
          html: n.html.slice(0, 200),
          data: n.any && n.any[0] && n.any[0].data ? n.any[0].data : undefined,
        })),
      }));
    return {
      url: location.pathname + location.search + location.hash,
      title: document.title,
      lang: document.documentElement.lang,
      htmlClass: document.documentElement.className,
      violations: slim(r.violations),
      incomplete: r.incomplete.map((v) => ({ id: v.id, nodes: v.nodes.length })),
      passes: r.passes.length,
    };
  }, options);
}

export function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

export function ensureDir(p) {
  if (!existsSync(p)) mkdirSync(p, { recursive: true });
}

export function saveJSON(path, obj) {
  writeFileSync(path, JSON.stringify(obj, null, 2));
}

export async function api(path, { persona = 'Alice', method = 'GET', body } = {}) {
  const s = sessions()[persona];
  const r = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${s.access_token}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = text;
  }
  return { status: r.status, json };
}

/** WCAG relative luminance / contrast from sRGB 0-255 triples. */
export function lum([r, g, b]) {
  const f = (c) => {
    c /= 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
export function contrast(a, b) {
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}
