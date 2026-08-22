import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

/**
 * The two halves of "a member can zoom".
 *
 * `index.html` used to carry `maximum-scale=1.0, user-scalable=no`, which is a
 * WCAG 2.1 SC 1.4.4 failure and the one violation axe reported on every screen.
 * Removing it is a one-line change; *keeping* it removed is the hard part,
 * because the attribute is usually added back the first time someone notices
 * iOS Safari zooming when an input takes focus.
 *
 * So this file asserts both the removal and the reason it is safe: every input
 * a member can type into renders at >= 16px on mobile, which is what actually
 * stops iOS zooming. Break the second and the first will not survive review.
 */

const ROOT = resolve(process.cwd());

// ── Half one: the meta tag ──────────────────────────────────────────────────

describe('viewport meta', () => {
  const html = readFileSync(join(ROOT, 'index.html'), 'utf8');
  const meta = /<meta\s+name="viewport"\s+content="([^"]*)"/.exec(html);

  it('exists and is device-width', () => {
    expect(meta, 'no viewport meta tag in index.html').not.toBeNull();
    expect(meta![1]).toContain('width=device-width');
  });

  it('does not disable user scaling', () => {
    expect(meta![1], 'user-scalable=no is a WCAG 1.4.4 failure').not.toContain(
      'user-scalable=no',
    );
  });

  it('does not cap the zoom level', () => {
    // Any maximum-scale below 2 fails SC 1.4.4; the app sets none at all.
    expect(meta![1], 'maximum-scale caps zoom').not.toMatch(/maximum-scale/);
  });

  it('keeps viewport-fit=cover for the safe-area insets', () => {
    // Unrelated to zoom, but the notch padding depends on it — don't lose it
    // while removing the neighbouring attributes.
    expect(meta![1]).toContain('viewport-fit=cover');
  });
});

// ── Half two: why removing it is safe ───────────────────────────────────────

/** Every .tsx under src/, so a new page cannot quietly reintroduce a small input. */
function tsxFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) tsxFiles(full, acc);
    else if (entry.endsWith('.tsx')) acc.push(full);
  }
  return acc;
}

/**
 * Tailwind sizes that are >= 16px, which is the threshold iOS Safari uses to
 * decide whether to zoom a focused field. `text-base` is 16px; everything above
 * it is larger. `sm:text-sm` after one of these is fine — the rule only applies
 * at mobile widths, and `sm:` starts at 640px.
 */
const AT_LEAST_16PX = /\btext-(base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)\b/;

/** Input types with no typeable text, so iOS never zooms them. */
const NOT_TEXT_ENTRY = /type=["'{]?(checkbox|radio|hidden|range|color|file|submit|button)/;

/**
 * The attribute text of every `<input>`, `<textarea>` and `<select>` in a file.
 *
 * Scanned rather than matched with `[^>]*`, because a JSX prop routinely holds a
 * `>` of its own — `onChange={(e) => ...}` is the common one — and a naive
 * character class stops at the arrow, before `className` is ever reached. That
 * mistake makes this whole file silently vacuous: it passes because it is
 * looking at the first two attributes of each element. Track brace depth and
 * quotes, and stop at the `>` that actually closes the tag.
 */
function elementAttributes(source: string): Array<{ tag: string; attrs: string }> {
  const found: Array<{ tag: string; attrs: string }> = [];
  for (const m of source.matchAll(/<(input|textarea|select)\b/g)) {
    const tag = m[1];
    let i = m.index! + m[0].length;
    let depth = 0;
    let quote: string | null = null;
    const start = i;
    for (; i < source.length; i += 1) {
      const c = source[i];
      if (quote) {
        if (c === quote) quote = null;
        continue;
      }
      if (c === '"' || c === "'" || c === '`') quote = c;
      else if (c === '{') depth += 1;
      else if (c === '}') depth -= 1;
      else if (c === '>' && depth === 0) break;
    }
    found.push({ tag, attrs: source.slice(start, i) });
  }
  return found;
}

describe('inputs are at least 16px on mobile', () => {
  const files = tsxFiles(join(ROOT, 'src'));

  it('finds the components to check', () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it.each(files.map((f) => [f.replace(`${ROOT}/`, ''), f]))(
    '%s',
    (_label, file) => {
      const source = readFileSync(file, 'utf8');
      const offenders: string[] = [];

      for (const { tag, attrs } of elementAttributes(source)) {
        if (NOT_TEXT_ENTRY.test(attrs)) continue;
        // No className at all means it inherits, which is the shared Input
        // component's job rather than this element's.
        if (!/className/.test(attrs)) continue;
        // A className that names no text size also inherits.
        if (!/\btext-(xs|sm|base|lg|xl|\[)/.test(attrs)) continue;
        if (!AT_LEAST_16PX.test(attrs)) {
          offenders.push(`<${tag}> ${attrs.replace(/\s+/g, ' ').trim().slice(0, 110)}`);
        }
      }

      expect(
        offenders,
        `these render under 16px on mobile, so iOS Safari will zoom when they take ` +
          `focus — give them "text-base sm:text-sm" as components/ui/input.tsx does`,
      ).toEqual([]);
    },
  );
});
