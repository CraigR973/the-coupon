// axe-core 4.10.2 + screenshot per route × state × width × theme, in real Chromium,
// against the production bundle on :4330 and the seeded API on :8130.
//
//   node sweep.mjs --phase open [--only name,name] [--widths 390,1280] [--themes light,dark]
//                  [--noshot] [--noaxe] [--tag rerun]
//
// Writes one JSON per run to notes/03-ux/axe/<phase>/<file>.json and appends a line to
// notes/03-ux/axe/<phase>-summary.tsv. Screenshots go to screenshots/ as
// <name>--<state>--<width>--<theme>[--full].png. Every run records a `proof` object —
// DOM facts checked at capture time (skeleton count, error-state count, toast count,
// offline banner, locked/settled markers, h1 text) — which INDEX.md cites.
import { writeFileSync, appendFileSync } from 'node:fs';
import {
  chromium, newContext, settle, runAxe, saveJSON, ensureDir, sessions, api,
  WEB, API, NOTES, SHOTS,
} from './lib.mjs';

const argv = process.argv.slice(2);
const arg = (k, d) => {
  const i = argv.indexOf(`--${k}`);
  return i >= 0 ? argv[i + 1] : d;
};
const flag = (k) => argv.includes(`--${k}`);
const PHASE = arg('phase', 'open');
const ONLY = arg('only', '') ? arg('only').split(',') : null;
const WIDTHS = arg('widths', '390,1280').split(',').map(Number);
const THEMES = arg('themes', 'light,dark').split(',');
const TAG = arg('tag', '');

const S = sessions();
const ids = {
  alice: S.Alice.player.id,
  bob: S.Bob.player.id,
};
const tables = (await api('/api/v1/football/tables')).json;
const arsenal = tables[0].rows.find((r) => /Arsenal/.test(r.team)) ?? tables[0].rows[0];
ids.team = arsenal.team_id;
ids.comp = tables[0].competition_id;
ids.season = tables[0].season;

const hold = () => new Promise(() => {});
const fail500 = (route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Internal Server Error"}' });
const emptyList = (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
const apiPath = (p) => `${API}/api/v1/${p}`;

// ---------- the catalogue ----------
// name, path, persona, state, optional: setup(page), after(page), full, axe=false, waitFor
const J = [];
const add = (o) => J.push({ persona: 'Alice', state: 'happy', ...o });

if (PHASE === 'open') {
  // public
  for (const [name, path] of [
    ['login', '/login'], ['register', '/register'], ['forgot-pin', '/forgot-pin'],
    ['set-pin', '/set-pin?name=Dana'], ['join', '/join/REVIEWINVITE1'], ['welcome', '/welcome'],
  ]) add({ name, path, persona: null });
  add({ name: 'join', path: '/join/NOSUCHTOKEN', persona: null, state: 'invalid' });
  add({ name: 'install-gate', path: '/login', persona: null, state: 'mobile-browser', mobileUA: true, widths: [390] });

  // member core
  add({ name: 'home', path: '/', full: true });
  add({ name: 'home', path: '/', persona: 'Bob', state: 'member' });
  add({ name: 'home', path: '/', persona: 'Dave', state: 'firstrun', full: true });
  add({ name: 'current-round', path: '/leagues/the-coupon/predictions', state: 'open', full: true });
  add({ name: 'current-round', path: '/leagues/the-coupon/predictions', persona: 'Bob', state: 'open-picked', full: true });
  add({ name: 'current-round', path: '/leagues/sunday-club/predictions', state: 'locked', full: true });
  add({ name: 'coupon', path: '/leagues/the-coupon/predictions#coupon', state: 'open' });
  add({ name: 'results', path: '/leagues/the-coupon/predictions/results', state: 'archive-season', full: true });
  add({ name: 'results', path: '/leagues/sunday-club/predictions/results', state: 'empty' });
  add({ name: 'standings', path: '/leagues/the-coupon/leaderboard', full: true });
  add({ name: 'standings', path: '/leagues/the-coupon/leaderboard?season=2025', state: 'archive', full: true });
  add({ name: 'standings', path: '/leagues/sunday-club/leaderboard', state: 'no-settled-rounds' });
  add({ name: 'player-profile', path: `/leagues/the-coupon/players/${ids.bob}` });
  add({ name: 'career-profile', path: '/profile' });
  add({ name: 'football', path: '/football' });
  add({ name: 'football', path: '/football?view=results', state: 'results' });
  add({ name: 'team-season', path: `/football/teams/${ids.team}?competition=${ids.comp}&season=${ids.season}`, full: true });
  add({ name: 'settings', path: '/settings', full: true });
  add({ name: 'about', path: '/about', full: true });
  add({ name: 'offline-route', path: '/offline' });
  add({ name: 'my-leagues', path: '/leagues' });
  add({ name: 'my-leagues', path: '/leagues', persona: 'Dave', state: 'firstrun' });
  add({ name: 'create-league', path: '/leagues/new' });
  add({ name: 'discover-leagues', path: '/leagues/discover', persona: 'Dave' });
  add({ name: 'join-by-code', path: '/leagues/join', persona: 'Dave' });

  // league admin (Alice on the-coupon)
  for (const s of ['members', 'settings', 'requests', 'invites', 'audit-log'])
    add({ name: `league-${s}`, path: `/leagues/the-coupon/admin/${s}`, full: s === 'settings' });
  add({ name: 'league-members', path: '/leagues/sunday-club/admin/members', persona: 'Alice', state: 'not-admin' });

  // site admin
  for (const s of ['dashboard', 'calendar', 'players', 'results', 'sync', 'invites', 'leagues'])
    add({ name: `admin-${s}`, path: `/admin/${s}` });
  add({ name: 'admin-dashboard', path: '/admin/dashboard', persona: 'Bob', state: 'not-site-admin' });

  // loading (held request), error (500), forced-empty (200 [])
  const states = [
    ['home', '/', 'me/cross-league-summary'],
    ['current-round', '/leagues/the-coupon/predictions', 'leagues/the-coupon/gameweek/current'],
    ['standings', '/leagues/the-coupon/leaderboard', 'leagues/the-coupon/standings'],
    ['results', '/leagues/the-coupon/predictions/results', 'leagues/the-coupon/results'],
    ['my-leagues', '/leagues', 'leagues/mine'],
    ['football', '/football', 'football/tables'],
    ['career-profile', '/profile', 'me/profile'],
    ['team-season', `/football/teams/${ids.team}?competition=${ids.comp}&season=${ids.season}`, `football/teams/${ids.team}/season`],
    ['player-profile', `/leagues/the-coupon/players/${ids.bob}`, `leagues/the-coupon/players/${ids.bob}/profile`],
    ['league-members', '/leagues/the-coupon/admin/members', 'leagues/the-coupon/members'],
    ['league-audit-log', '/leagues/the-coupon/admin/audit-log', 'leagues/the-coupon/audit-log'],
    ['admin-players', '/admin/players', 'admin/players'],
    ['admin-dashboard', '/admin/dashboard', 'admin/dashboard'],
  ];
  for (const [name, path, ep] of states) {
    add({ name, path, state: 'loading', allowSkeleton: true, axe: true,
      setup: (page) => page.route((u) => u.href.startsWith(apiPath(ep)), hold) });
    add({ name, path, state: 'error', waitMs: 4500,
      setup: (page) => page.route((u) => u.href.startsWith(apiPath(ep)), fail500) });
  }
  for (const [name, path, ep] of [
    ['standings', '/leagues/the-coupon/leaderboard', 'leagues/the-coupon/standings'],
    ['results', '/leagues/the-coupon/predictions/results', 'leagues/the-coupon/results'],
    ['my-leagues', '/leagues', 'leagues/mine'],
    ['football', '/football', 'football/tables'],
  ]) add({ name, path, state: 'forced-empty',
    setup: (page) => page.route((u) => u.href.startsWith(apiPath(ep)), emptyList) });

  // offline: load online, then drop the network
  for (const [name, path] of [['home', '/'], ['current-round', '/leagues/the-coupon/predictions'], ['standings', '/leagues/the-coupon/leaderboard']])
    add({ name, path, state: 'offline',
      after: async (page, ctx) => { await ctx.setOffline(true); await page.evaluate(() => window.dispatchEvent(new Event('offline'))); await page.waitForTimeout(800); } });
}

if (PHASE === 'settled') {
  add({ name: 'current-round', path: '/leagues/the-coupon/predictions', state: 'settled', full: true });
  add({ name: 'coupon', path: '/leagues/the-coupon/predictions#coupon', state: 'settled' });
  add({ name: 'home', path: '/', state: 'settled', full: true });
  add({ name: 'results', path: '/leagues/the-coupon/predictions/results', state: 'settled', full: true });
  add({ name: 'standings', path: '/leagues/the-coupon/leaderboard', state: 'settled', full: true });
  add({ name: 'player-profile', path: `/leagues/the-coupon/players/${ids.bob}`, state: 'settled' });
  add({ name: 'career-profile', path: '/profile', state: 'settled' });
  add({ name: 'admin-results', path: '/admin/results', state: 'settled' });
}

if (PHASE === 'locked') {
  add({ name: 'current-round', path: '/leagues/the-coupon/predictions', state: 'locked-own', full: true });
  add({ name: 'home', path: '/', state: 'locked' });
  add({ name: 'admin-results', path: '/admin/results', state: 'pending-settlement' });
}

// ---------- run ----------
const proofFn = () => {
  const q = (s) => document.querySelectorAll(s).length;
  const h1 = [...document.querySelectorAll('h1')].map((e) => e.textContent.trim()).slice(0, 3);
  const text = document.body.innerText;
  return {
    h1,
    mains: q('main'),
    skeletons: q('[aria-busy="true"]'),
    errorState: q('[data-testid="query-error-state"]'),
    toasts: q('[data-sonner-toast]'),
    offlineText: /offline/i.test(text),
    lockedText: /\block(ed|s)\b/i.test(text),
    settledText: /\b(won|lost|settled|void)\b/i.test(text),
    emptyText: /(no |not in any|nothing|yet)/i.test(text),
    hScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    url: location.pathname + location.search,
    snippet: text.replace(/\s+/g, ' ').slice(0, 220),
  };
};

const outDir = `${NOTES}/axe/${PHASE}${TAG ? '-' + TAG : ''}`;
ensureDir(outDir);
ensureDir(SHOTS);
const summary = `${outDir}-summary.tsv`;
writeFileSync(summary, 'file\tpath\tpersona\tviolations\tproof\n');

const browser = await chromium.launch();
let n = 0;
for (const job of J) {
  if (ONLY && !ONLY.includes(job.name) && !ONLY.includes(`${job.name}--${job.state}`)) continue;
  for (const width of job.widths ?? WIDTHS) {
    for (const theme of THEMES) {
      const base = `${job.name}--${job.state}--${width}--${theme}`;
      const ctx = await newContext(browser, { width, theme, persona: job.persona, mobileUA: job.mobileUA });
      const page = await ctx.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)));
      try {
        if (job.setup) await job.setup(page);
        await page.goto(`${WEB}${job.path}`, { waitUntil: 'domcontentloaded' });
        if (job.state === 'loading') {
          await page.waitForSelector('[aria-busy="true"]', { timeout: 10000 }).catch(() => {});
          await page.waitForTimeout(1200);
        } else {
          await settle(page, { allowSkeleton: job.allowSkeleton });
          if (job.waitMs) {
            await page.waitForSelector('[data-testid="query-error-state"]', { timeout: job.waitMs }).catch(() => {});
            await page.waitForTimeout(500);
          }
        }
        if (job.after) await job.after(page, ctx);
        const proof = await page.evaluate(proofFn);
        let axe = null;
        if (!flag('noaxe') && job.axe !== false) axe = await runAxe(page);
        if (!flag('noshot')) {
          await page.screenshot({ path: `${SHOTS}/${base}.png` });
          if (job.full) await page.screenshot({ path: `${SHOTS}/${base}--full.png`, fullPage: true });
        }
        saveJSON(`${outDir}/${base}.json`, { job: { ...job, setup: !!job.setup, after: !!job.after }, width, theme, proof, axe, errors });
        const v = axe ? axe.violations.map((x) => `${x.id}(${x.impact[0]}):${x.nodes}`).join(' ') || '0' : '—';
        appendFileSync(summary, `${base}\t${proof.url}\t${job.persona}\t${v}\t${JSON.stringify({ sk: proof.skeletons, err: proof.errorState, h1: proof.h1, hs: proof.hScroll })}\n`);
        n++;
        console.log(base, v);
      } catch (e) {
        console.log('FAILED', base, String(e).slice(0, 300));
        appendFileSync(summary, `${base}\t${job.path}\t${job.persona}\tFAILED ${String(e).slice(0, 120)}\t\n`);
      }
      await ctx.close();
    }
  }
}
await browser.close();
console.log('runs', n);
