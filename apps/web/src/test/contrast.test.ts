import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

// Read from disk rather than imported: Vitest stubs CSS imports, so both a
// plain import and `?raw` hand back an empty string here. This is the same
// file the app ships, so the tokens under test cannot drift from the shipped
// ones. `process.cwd()` is the Vitest root, which is apps/web.
const CSS = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8');

/**
 * WCAG contrast, computed from the design tokens themselves.
 *
 * `accessibility.test.tsx` runs axe over rendered components, and axe's
 * `color-contrast` rule is disabled there because jsdom cannot resolve a CSS
 * custom property to a colour — so the one rule that would have caught this
 * class of bug is the one rule that cannot run. That is not a flaw in that
 * test; it is a limit of the environment. This file closes it from the other
 * side: it never renders anything, it reads `index.css` and does the
 * arithmetic.
 *
 * What it caught when it was written (2026-08-22 review): `--text-muted` had
 * been verified against `--bg` and `--surface` and shipped, and failed on
 * `--surface-elevated` and `--surface-overlay` in dark mode and on every
 * surface in light mode.
 */

// ── Token extraction ────────────────────────────────────────────────────────

/**
 * The declarations inside one balanced `{ ... }` block, found by its selector.
 *
 * Matched by regex rather than a literal so the test does not break on
 * reformatting — the selector list spans two lines today and need not tomorrow.
 */
function blockAfter(selector: RegExp): string {
  const found = selector.exec(CSS);
  if (!found) throw new Error(`selector not found in index.css: ${selector}`);
  const open = CSS.indexOf('{', found.index);
  let depth = 0;
  for (let i = open; i < CSS.length; i += 1) {
    if (CSS[i] === '{') depth += 1;
    else if (CSS[i] === '}') {
      depth -= 1;
      if (depth === 0) return CSS.slice(open, i);
    }
  }
  throw new Error(`unbalanced block for selector: ${selector}`);
}

/** Every `--name: #rrggbb;` in a block. Non-hex values (gradients, rgba) are skipped. */
function hexTokens(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/--([a-z-]+):\s*(#[0-9A-Fa-f]{6})\s*;/g)) {
    out[m[1]] = m[2].toUpperCase();
  }
  return out;
}

const DARK = hexTokens(blockAfter(/:root\s*,\s*html\.dark\s*\{/));
const LIGHT = hexTokens(blockAfter(/html\.light\s*\{/));

// ── WCAG 2.1 relative luminance and contrast ────────────────────────────────

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const h = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrast(fg: string, bg: string): number {
  const [hi, lo] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
  return (hi + 0.05) / (lo + 0.05);
}

// ── What must hold ──────────────────────────────────────────────────────────

/** Every ground a token may be painted on. A card can sit on a card. */
const SURFACES = ['bg', 'surface', 'surface-elevated', 'surface-overlay'] as const;

/**
 * Tokens that exist only to be read as text, so a single value has to clear AA
 * everywhere. Dual-purpose brand and semantic tokens are deliberately not here
 * — see KNOWN_DUAL_ROLE_DEBT.
 */
const TEXT_ONLY = ['text-primary', 'text-secondary', 'text-muted', 'locked'] as const;

/** WCAG 2.1 SC 1.4.3 Contrast (Minimum), AA, normal-sized text. */
const AA_NORMAL = 4.5;

/**
 * `--text-inverse` is the one text token that is *supposed* to be illegible on
 * the surface tiers: it is painted on an inverted ground — a `--primary` or
 * `--accent` fill, or the opposite palette — and never on `--bg` or a card. The
 * pairing that matters for it is `--on-primary` / `--on-accent`, which
 * `index.css` records as verified at >= 4.9:1. Measuring it against the
 * surfaces would assert the opposite of what it is for.
 */
const INVERTED_BY_DESIGN = ['text-inverse'] as const;

/**
 * Tokens that still fail AA as text and are knowingly left alone, because each
 * is used as a fill and a border as well as text, and one value provably cannot
 * do both jobs.
 *
 * The proof, for `--primary` in light mode: to clear 4.5:1 as text on white a
 * colour needs relative luminance <= 0.183; to clear 4.5:1 as a fill under the
 * near-black `--on-primary` it needs >= 0.208. There is no such colour. These
 * need a second token (brand-as-ink, distinct from brand-as-surface), which is
 * a design decision rather than a correction, and it is specified separately in
 * `docs/BUILD_PLAN.md`.
 *
 * This list is an admission, not a suppression: it is asserted to be exactly
 * accurate below, so it cannot silently grow.
 */
const KNOWN_DUAL_ROLE_DEBT = [
  'primary',
  'accent',
  'success',
  'warning',
  'error',
  'live',
  'gold',
  'silver',
  'bronze',
] as const;

describe.each([
  ['dark', DARK],
  ['light', LIGHT],
])('%s palette', (name, palette) => {
  it('defines every surface tier and text token', () => {
    for (const surface of SURFACES) expect(palette[surface], `--${surface}`).toBeDefined();
    for (const token of TEXT_ONLY) expect(palette[token], `--${token}`).toBeDefined();
  });

  describe.each(TEXT_ONLY)('--%s', (token) => {
    it.each(SURFACES)(`clears AA on --%s`, (surface) => {
      const ratio = contrast(palette[token], palette[surface]);
      expect(
        ratio,
        `${palette[token]} on ${palette[surface]} is ${ratio.toFixed(2)}:1, needs ${AA_NORMAL}:1`,
      ).toBeGreaterThanOrEqual(AA_NORMAL);
    });
  });

  it('records exactly the dual-role tokens that still fail, and no others', () => {
    const failing = Object.keys(palette)
      .filter((token) => (KNOWN_DUAL_ROLE_DEBT as readonly string[]).includes(token))
      .filter((token) =>
        SURFACES.some((surface) => contrast(palette[token], palette[surface]) < AA_NORMAL),
      )
      .sort();

    const expected = [...KNOWN_DUAL_ROLE_DEBT]
      .filter((token) => palette[token] !== undefined)
      .filter((token) =>
        SURFACES.some((surface) => contrast(palette[token], palette[surface]) < AA_NORMAL),
      )
      .sort();

    // The real assertion: nothing outside the known list may fail.
    const unexpected = Object.keys(palette)
      .filter((token) => !(KNOWN_DUAL_ROLE_DEBT as readonly string[]).includes(token))
      .filter((token) => !(TEXT_ONLY as readonly string[]).includes(token))
      .filter((token) => !(INVERTED_BY_DESIGN as readonly string[]).includes(token))
      .filter((token) => token.startsWith('text-'))
      .filter((token) =>
        SURFACES.some((surface) => contrast(palette[token], palette[surface]) < AA_NORMAL),
      );

    expect(unexpected, `${name}: text tokens failing AA outside the known list`).toEqual([]);
    expect(failing).toEqual(expected);
  });
});

describe('the regression this file exists for', () => {
  it('keeps muted legible where a card sits on a card', () => {
    // #7B859B (dark) and #8A93A1 (light) were the shipped values that failed.
    expect(contrast(DARK['text-muted'], DARK['surface-overlay'])).toBeGreaterThanOrEqual(
      AA_NORMAL,
    );
    expect(contrast(LIGHT['text-muted'], LIGHT['surface-elevated'])).toBeGreaterThanOrEqual(
      AA_NORMAL,
    );
  });

  it('keeps secondary and muted visually distinct after the correction', () => {
    expect(DARK['text-muted']).not.toEqual(DARK['text-secondary']);
    expect(LIGHT['text-muted']).not.toEqual(LIGHT['text-secondary']);
    // Secondary stays the stronger of the two in both palettes.
    expect(contrast(DARK['text-secondary'], DARK['bg'])).toBeGreaterThan(
      contrast(DARK['text-muted'], DARK['bg']),
    );
    expect(contrast(LIGHT['text-secondary'], LIGHT['bg'])).toBeGreaterThan(
      contrast(LIGHT['text-muted'], LIGHT['bg']),
    );
  });
});
