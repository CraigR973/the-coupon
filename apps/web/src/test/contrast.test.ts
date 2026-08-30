import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { AVATAR_PALETTE } from '@/components/ui/avatar';

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
 * The brand and semantic names as *text*.
 *
 * Batch 62 split each of these in two, because one value provably cannot do both
 * jobs: in light mode a green clearing 4.5:1 as text on white needs relative
 * luminance <= 0.183, while clearing 4.5:1 as a fill under the near-black
 * `--on-primary` needs >= 0.208. `tailwind.config.ts` points every `text-*`
 * utility at the `-ink` half, so these are what a reader actually sees, and they
 * are held to the same bar as the plain text tokens.
 */
const INK = [
  'primary-ink',
  'success-ink',
  'warning-ink',
  'accent-ink',
  'error-ink',
  'live-ink',
  'gold-ink',
  'bronze-ink',
] as const;

/**
 * The same names as *fills*, which is the job they kept. These are never read as
 * text — `bg-*`, `border-*`, `ring-*`, `fill-*` and `stroke-*` still resolve to
 * them — so measuring them against a surface would be measuring nothing. What
 * matters for a fill is the text that sits on it, asserted separately below.
 */
const FILLS = ['primary', 'accent'] as const;

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

  describe.each(INK)('--%s', (token) => {
    it.each(SURFACES)(`clears AA on --%s`, (surface) => {
      const ratio = contrast(palette[token], palette[surface]);
      expect(
        ratio,
        `${palette[token]} on ${palette[surface]} is ${ratio.toFixed(2)}:1, needs ${AA_NORMAL}:1`,
      ).toBeGreaterThanOrEqual(AA_NORMAL);
    });
  });

  it.each(FILLS)('carries legible text on a --%s fill', (token) => {
    // The other half of the split. A fill is judged by what sits on it, and what
    // sits on these is --on-primary / --on-accent, which index.css records as
    // verified. Asserted here so darkening a fill to "fix" contrast — the exact
    // wrong move, and the one this file exists to prevent — fails loudly.
    const on = token === 'primary' ? palette['on-primary'] : palette['on-accent'];
    const ratio = contrast(on, palette[token]);
    expect(
      ratio,
      `${on} on the --${token} fill is ${ratio.toFixed(2)}:1, needs ${AA_NORMAL}:1`,
    ).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it('leaves no text token failing AA anywhere', () => {
    const failing = Object.keys(palette)
      .filter((token) => token.endsWith('-ink') || (TEXT_ONLY as readonly string[]).includes(token))
      .filter((token) =>
        SURFACES.some((surface) => contrast(palette[token], palette[surface]) < AA_NORMAL),
      );

    expect(failing, `${name}: text tokens below ${AA_NORMAL}:1`).toEqual([]);
  });

  it('gives every ink token a fill counterpart, so none is orphaned', () => {
    for (const ink of INK) {
      const base = ink.replace(/-ink$/, '');
      expect(palette[base], `--${base} backs --${ink}`).toBeDefined();
    }
  });

  it.each(INVERTED_BY_DESIGN)('reads --%s against the ground it is actually on', (token) => {
    // Asserted rather than excluded silently. This token is illegible on the surface
    // tiers on purpose, so the meaningful pairing is the inverted one: `--text-inverse`
    // against `--text-primary` used as a ground, which is what "inverse" means.
    //
    // Note it is *not* the text on a brand fill — that is `--on-primary`, asserted
    // above. Getting those two confused is easy and produces a failing assertion for
    // a pairing the app never renders.
    const ratio = contrast(palette[token], palette['text-primary']);
    expect(
      ratio,
      `${palette[token]} on a --text-primary ground is ${ratio.toFixed(2)}:1`,
    ).toBeGreaterThanOrEqual(AA_NORMAL);
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

describe.each([
  ['dark', DARK],
  ['light', LIGHT],
])('%s avatar palette', (theme, palette) => {
  it.each(AVATAR_PALETTE)(
    'renders $background with AA initials from $foreground',
    ({ background, foreground, className }) => {
      expect(className).toContain(`bg-[var(--${background})]`);
      expect(className).toContain(`text-[var(--${foreground})]`);
      expect(palette[background], `--${background}`).toBeDefined();
      expect(palette[foreground], `--${foreground}`).toBeDefined();
      const ratio = contrast(palette[foreground], palette[background]);
      expect(
        ratio,
        `${theme}: ${palette[foreground]} on ${palette[background]} is ${ratio.toFixed(2)}:1, needs ${AA_NORMAL}:1`,
      ).toBeGreaterThanOrEqual(AA_NORMAL);
    },
  );
});
