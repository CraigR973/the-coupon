/**
 * Batch 163 — the precache filter, held against the routes it claims to describe.
 *
 * The filter is a list of names, and a list of names goes stale silently: add an admin
 * page, forget the list, and the service worker quietly starts precaching it again for
 * everyone. Worse in the other direction — match too much and a member-facing route
 * stops being available offline, which nobody notices until they are on a train.
 *
 * So these read `App.tsx` and `src/pages/admin/` rather than restating what they say.
 */

import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { isRoleGatedChunk, LEAGUE_ADMIN_PAGES } from '@/lib/precacheFilter';

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const APP = readFileSync(resolve(SRC, 'App.tsx'), 'utf8');

/** A chunk filename as Rollup emits it, which is the basename plus a content hash. */
function chunk(name: string): string {
  return `assets/${name}-AbC123_x.js`;
}

describe('the precache filter', () => {
  it('excludes every page in the site-admin console', () => {
    const pages = readdirSync(resolve(SRC, 'pages/admin')).filter((f) => f.endsWith('.tsx'));
    expect(pages.length).toBeGreaterThan(5);
    for (const file of pages) {
      const name = file.replace(/\.tsx$/, '');
      expect(isRoleGatedChunk(chunk(name)), `${name} would still be precached`).toBe(true);
    }
  });

  it('keeps the site-admin console named so that it can be matched by prefix', () => {
    // The load-bearing convention. Two of these were once `DashboardPage.tsx` and
    // `ResultsPage.tsx`, colliding with the member-facing pages of the same name — a
    // prefix filter written against that layout would have stopped precaching home.
    const pages = readdirSync(resolve(SRC, 'pages/admin')).filter((f) => f.endsWith('.tsx'));
    const stray = pages.filter((f) => !f.startsWith('Admin'));
    expect(stray, 'a page under pages/admin/ must be named Admin*').toEqual([]);
  });

  it('excludes every per-league admin route App.tsx declares', () => {
    // `<Route path="/leagues/:slug/admin/..." element={<XPage />} />`
    const declared = [...APP.matchAll(/path="\/leagues\/:slug\/admin\/[^"]*"[\s\S]{0,120}?element=\{<(\w+)\s*\/>\}/g)]
      .map((m) => m[1]);
    expect(declared.length).toBeGreaterThanOrEqual(5);
    for (const component of declared) {
      expect(
        isRoleGatedChunk(chunk(component)),
        `${component} is a per-league admin route but would still be precached — add it to LEAGUE_ADMIN_PAGES`,
      ).toBe(true);
    }
  });

  it('names no league-admin page that App.tsx does not route there', () => {
    // The other direction: a stale entry here would stop precaching a page that has since
    // become member-facing, and nothing else would notice.
    for (const name of LEAGUE_ADMIN_PAGES) {
      expect(APP.includes(name), `${name} is in the filter but not in App.tsx`).toBe(true);
    }
  });

  it('precaches the member-facing pages, including the ones sharing a name with an admin page', () => {
    const memberFacing = [
      'DashboardPage',
      'ResultsPage',
      'CurrentRoundPage',
      'LeaderboardPage',
      'CareerProfilePage',
      'SettingsPage',
      'OfflinePage',
      'Layout',
      'index',
      'react-vendor',
    ];
    for (const name of memberFacing) {
      expect(isRoleGatedChunk(chunk(name)), `${name} must still be precached`).toBe(false);
    }
  });

  it('leaves the shell alone', () => {
    for (const url of ['index.html', 'assets/index-a1b2c3d4.css', 'manifest.webmanifest', 'icon-512.png']) {
      expect(isRoleGatedChunk(url), `${url} must still be precached`).toBe(false);
    }
  });
});
