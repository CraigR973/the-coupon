// Bundle and precache facts from a production build (load-independent).
//   node bundle.mjs <dist-dir>   -> writes bundle.json beside this file, prints a summary
import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = process.argv[2];
const here = dirname(fileURLToPath(import.meta.url));
const walk = (d) => readdirSync(d).flatMap((f) => {
  const p = join(d, f);
  return statSync(p).isDirectory() ? walk(p) : [p];
});
const files = walk(dist).map((p) => p.slice(dist.length + 1));
const size = (f) => statSync(join(dist, f)).size;
const gz = (f) => gzipSync(readFileSync(join(dist, f)), { level: 9 }).length;
const js = files.filter((f) => f.startsWith('assets/') && f.endsWith('.js'));
const css = files.filter((f) => f.startsWith('assets/') && f.endsWith('.css'));
const kb = (n) => Math.round((n / 1024) * 10) / 10;

// The precache manifest vite-plugin-pwa injected into sw.js, and the runtime filter.
const sw = readFileSync(join(dist, 'sw.js'), 'utf8');
const urls = [...sw.matchAll(/"url":"([^"]+)"/g)].map((m) => m[1]);
const SITE_ADMIN = /(^|\/)Admin[A-Za-z]*(Page|Nav)-[A-Za-z0-9_-]+\.js$/;
const LEAGUE_ADMIN = /(^|\/)(LeagueMembersPage|LeagueSettingsPage|LeagueJoinRequestsPage|LeagueAdminInvitesPage|LeagueAuditLogPage)-[A-Za-z0-9_-]+\.js$/;
const gated = (u) => SITE_ADMIN.test(u) || LEAGUE_ADMIN.test(u);
const exists = (u) => files.includes(u);
const kept = urls.filter((u) => !gated(u));
const dropped = urls.filter(gated);
const sum = (list) => list.filter(exists).reduce((a, u) => a + size(u), 0);
const byType = (list) => {
  const out = {};
  for (const u of list) {
    const t = u.endsWith('.js') ? 'js' : u.endsWith('.css') ? 'css' : u.endsWith('.woff2') ? 'font'
      : /\.(png|svg|ico)$/.test(u) ? 'icon' : u.endsWith('.html') ? 'html' : 'other';
    out[t] = out[t] || { n: 0, kib: 0 };
    out[t].n += 1;
    out[t].kib = kb(out[t].kib * 1024 + (exists(u) ? size(u) : 0));
  }
  return out;
};
const framer = js.filter((f) => /framer-motion|motion-dom|useReducedMotion|AnimatePresence/.test(readFileSync(join(dist, f), 'utf8')));
const index = readFileSync(join(dist, 'index.html'), 'utf8');
const result = {
  js_chunks: js.length,
  js_raw_kib: kb(js.reduce((a, f) => a + size(f), 0)),
  js_gzip_kib: kb(js.reduce((a, f) => a + gz(f), 0)),
  css_raw_kib: kb(css.reduce((a, f) => a + size(f), 0)),
  largest_js: js.map((f) => [f, kb(size(f)), kb(gz(f))]).sort((a, b) => b[1] - a[1]).slice(0, 8),
  precache_manifest_entries: urls.length,
  precache_manifest_kib: kb(sum(urls)),
  precache_after_role_filter_entries: kept.length,
  precache_after_role_filter_kib: kb(sum(kept)),
  precache_kept_by_type: byType(kept),
  precache_dropped: dropped,
  chunks_mentioning_framer_motion: framer,
  index_html_preloads: [...index.matchAll(/<link[^>]+(modulepreload|preload)[^>]+href="([^"]+)"/g)].map((m) => m[2]),
  fonts_in_dist: files.filter((f) => f.endsWith('.woff2')).map((f) => [f, kb(size(f))]),
};
writeFileSync(join(here, 'bundle.json'), JSON.stringify(result, null, 1));
console.log(JSON.stringify({ ...result, largest_js: undefined, precache_dropped: dropped.length }, null, 0));
