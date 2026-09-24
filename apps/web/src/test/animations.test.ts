/**
 * Batch 164 — the transitions that replaced framer-motion, and the dependency staying out.
 *
 * 107 KB of JavaScript for five transitions, 62% of it unused on home. Each one is now a
 * CSS class. Two things can silently undo that and neither shows up as a failure anywhere
 * else: someone importing the library again, and a class name that does not match the
 * stylesheet — a typo'd `animate-*` renders a perfectly good element with no animation on
 * it, which looks like a design decision rather than a bug.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const CSS = readFileSync(resolve(SRC, 'index.css'), 'utf8');

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(name) ? [path] : [];
  });
}

const FILES = sourceFiles(SRC);

describe('the animations that replaced framer-motion', () => {
  it('leaves framer-motion unimported anywhere in the app', () => {
    // The dependency is still declared in package.json, which is a protected gate file
    // this batch may not edit. Nothing imports it, so nothing bundles it — and this is
    // what keeps that true. Removing the declaration needs a gate-maintenance batch.
    const importers = FILES.filter((path) =>
      /from\s+['"]framer-motion['"]|require\(['"]framer-motion['"]\)|vi\.mock\(['"]framer-motion['"]/.test(
        readFileSync(path, 'utf8'),
      ),
    ).map((path) => path.slice(SRC.length + 1));

    expect(importers, 'framer-motion is back in the bundle').toEqual([]);
  });

  it('defines every animation class the components ask for', () => {
    // A class that does not exist in the stylesheet is not an error — the element just
    // renders without the animation, indistinguishable from a deliberate choice.
    const used = new Set<string>();
    for (const path of FILES) {
      for (const match of readFileSync(path, 'utf8').matchAll(/['"\s`](animate-[a-z-]+)/g)) {
        used.add(match[1]);
      }
    }
    // Tailwind core ships the first four; `tailwindcss-animate` (a configured plugin)
    // ships `animate-in`/`animate-out` and their modifiers. The rest are ours, declared
    // in index.css, and are the ones this can meaningfully check.
    const provided = new Set([
      'animate-spin',
      'animate-pulse',
      'animate-bounce',
      'animate-ping',
      'animate-in',
      'animate-out',
    ]);
    const ours = [...used].filter((name) => !provided.has(name));

    expect(ours.length).toBeGreaterThanOrEqual(4);
    for (const name of ours) {
      expect(CSS.includes(`.${name}`), `${name} is used but not defined in index.css`).toBe(true);
    }
  });

  it('gives each of its keyframes a definition', () => {
    for (const name of ['page-enter', 'label-enter', 'draw-check', 'value-pulse']) {
      expect(CSS.includes(`@keyframes ${name}`), `@keyframes ${name} is missing`).toBe(true);
    }
  });

  it('still answers prefers-reduced-motion, and now for the slide as well', () => {
    const block = CSS.slice(CSS.indexOf('@media (prefers-reduced-motion: reduce)'));
    expect(block).toContain('animation-duration: 0.01ms !important');
    expect(block).toContain('transition-duration: 0.01ms !important');
    // Collapsing the duration is not enough on its own: an animation that starts 16px to
    // one side still shows a frame of displacement before it snaps.
    expect(block).toContain('--page-enter-x: 0px');
  });

  it('asks for no font weight the stylesheet does not serve', () => {
    // Batch 164 dropped JetBrains Mono 700, which nothing used and the service worker
    // precached anyway. If a bold mono ever comes back it needs its face back too.
    const monoBold = FILES.filter((path) =>
      /font-mono[^"'`]*font-(bold|extrabold|black)|font-(bold|extrabold|black)[^"'`]*font-mono/.test(
        readFileSync(path, 'utf8'),
      ),
    ).map((path) => path.slice(SRC.length + 1));

    expect(monoBold, 'bold mono is used but its @font-face was removed').toEqual([]);
    expect(CSS).not.toContain('jetbrains-mono-700');
  });
});
