import { readFileSync, readdirSync } from 'node:fs';
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

// ── The focus indicator ─────────────────────────────────────────────────────

/**
 * WCAG 2.2 SC 1.4.11 Non-text Contrast, for a focus indicator.
 *
 * Batch 158. `--shadow-glow` was `0 0 0 3px rgba(16,185,129,0.25)` in dark and
 * `rgba(5,150,105,0.20)` in light: a ring at a fifth to a quarter alpha, which
 * composites against whatever it sits on and lands at 1.49-1.53:1 (dark) and
 * 1.27-1.28:1 (light) against the 3:1 required. Every button in the app used
 * it, alongside `focus-visible:outline-none`, so keyboard focus was effectively
 * invisible — and axe has no focus-indicator rule, so 88 clean automated runs
 * never mentioned it.
 *
 * The arithmetic lives here for the same reason the rest of this file does:
 * jsdom cannot resolve a custom property to a colour, so the rendered-component
 * tests cannot measure this. Rendering is asserted separately below — that the
 * ring is *wired to* the controls the review named.
 */
const AA_NON_TEXT = 3;

/** Every `--name: <anything>;` in a block, values left as written. */
function rawTokens(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/--([a-z-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

const DARK_RAW = rawTokens(blockAfter(/:root\s*,\s*html\.dark\s*\{/));
const LIGHT_RAW = rawTokens(blockAfter(/html\.light\s*\{/));

/**
 * The two layers of a focus ring token, as token names.
 *
 * The shape is `0 0 0 2px var(--gap), 0 0 0 5px var(--ring)`: an inner spread
 * that separates the indicator from the control's own fill, then the indicator
 * itself. Parsed rather than hard-coded so changing the shape fails here.
 */
function ringLayers(value: string): { gap: string; ring: string } {
  const layers = value.split(/,(?![^(]*\))/).map((layer) => layer.trim());
  expect(layers, `expected two box-shadow layers, got: ${value}`).toHaveLength(2);
  const names = layers.map((layer) => {
    const m = /var\(--([a-z-]+)\)/.exec(layer);
    expect(m, `layer is not a bare token reference: ${layer}`).not.toBeNull();
    return (m as RegExpExecArray)[1];
  });
  return { gap: names[0], ring: names[1] };
}

const FOCUS_TOKENS = ['shadow-glow', 'shadow-glow-accent', 'shadow-glow-on-brand'] as const;

describe.each([
  ['dark', DARK, DARK_RAW],
  ['light', LIGHT, LIGHT_RAW],
])('%s focus indicator', (name, palette, raw) => {
  it.each(FOCUS_TOKENS)('--%s carries no alpha at all', (token) => {
    // The regression itself. A translucent ring cannot be measured from the
    // token, only from the pixels it happens to composite onto, which is how
    // this shipped: verified against one background and wrong on all of them.
    expect(raw[token], `--${token}`).toBeDefined();
    expect(raw[token], `${name}: --${token} is translucent again`).not.toMatch(/rgba?\(/);
  });

  it.each(['shadow-glow', 'shadow-glow-accent'] as const)(
    '--%s clears 3:1 on every surface tier',
    (token) => {
      const { ring } = ringLayers(raw[token]);
      for (const surface of SURFACES) {
        const ratio = contrast(palette[ring], palette[surface]);
        expect(
          ratio,
          `${name}: --${ring} (${palette[ring]}) on --${surface} (${palette[surface]}) is ${ratio.toFixed(2)}:1, needs ${AA_NON_TEXT}:1`,
        ).toBeGreaterThanOrEqual(AA_NON_TEXT);
      }
    },
  );

  it.each(FOCUS_TOKENS)('--%s separates its ring from its gap', (token) => {
    // Two layers that read as one blob is one layer with extra steps.
    const { gap, ring } = ringLayers(raw[token]);
    const ratio = contrast(palette[ring], palette[gap]);
    expect(
      ratio,
      `${name}: --${ring} on the --${gap} gap is ${ratio.toFixed(2)}:1`,
    ).toBeGreaterThanOrEqual(AA_NON_TEXT);
  });

  it.each(['shadow-glow', 'shadow-glow-accent'] as const)(
    '--%s uses a gap colour that reads as a gap on every tier',
    (token) => {
      // One gap colour has to serve four grounds. It can, because the tiers are
      // within 1.24:1 of each other — but only while that stays true.
      const { gap } = ringLayers(raw[token]);
      for (const surface of SURFACES) {
        const ratio = contrast(palette[gap], palette[surface]);
        expect(
          ratio,
          `${name}: the --${gap} gap reads as an edge on --${surface} at ${ratio.toFixed(2)}:1`,
        ).toBeLessThan(1.5);
      }
    },
  );

  it('gives a control sitting on a brand fill its own ring', () => {
    // --shadow-glow would vanish here: its gap is --surface and its ring is the
    // brand colour, which is the ground. This one inverts both.
    const { gap, ring } = ringLayers(raw['shadow-glow-on-brand']);
    expect(gap).toBe('primary');
    const ratio = contrast(palette[ring], palette['primary']);
    expect(
      ratio,
      `${name}: --${ring} on a --primary fill is ${ratio.toFixed(2)}:1, needs ${AA_NON_TEXT}:1`,
    ).toBeGreaterThanOrEqual(AA_NON_TEXT);
  });

  it('would have failed on the ring that shipped', () => {
    // Guards the guard: the arithmetic above has to reject the real defect.
    const composite = (hex: string, alpha: number, ground: string) => {
      const mix = (a: string, b: string, i: number) =>
        Math.round(parseInt(a.slice(i, i + 2), 16) * alpha + parseInt(b.slice(i, i + 2), 16) * (1 - alpha));
      const [f, g] = [hex.replace('#', ''), ground.replace('#', '')];
      return `#${[0, 2, 4].map((i) => mix(f, g, i).toString(16).padStart(2, '0')).join('')}`;
    };
    const shipped = name === 'dark' ? ['#10B981', 0.25] : ['#059669', 0.2];
    const onSurface = composite(shipped[0] as string, shipped[1] as number, palette['surface']);
    expect(contrast(onSurface, palette['surface'])).toBeLessThan(AA_NON_TEXT);
  });
});

describe('the controls the focus ring has to reach', () => {
  // The review named three: "buttons, selection rows and the bottom-nav items".
  // Measuring the token proves the colour; this proves it is wired to them.
  const read = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

  it.each([
    ['buttons', 'src/components/ui/button.tsx'],
    ['selection rows', 'src/components/PickCard.tsx'],
    ['bottom-nav items', 'src/components/TabBar.tsx'],
  ])('%s use the shared focus ring', (_label, path) => {
    expect(read(path)).toMatch(/focus-visible:shadow-glow\b/);
  });

  it('leaves no control styling focus with a bare ring utility', () => {
    // `ring-*` utilities bypass the tokens measured above, which is how the two
    // hold-outs (UpdateBanner, the settings toggle) kept an unmeasured ring.
    const sources = ['src/components', 'src/pages'];
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(resolve(process.cwd(), dir), { withFileTypes: true })) {
        const next = `${dir}/${entry.name}`;
        if (entry.isDirectory()) walk(next);
        else if (entry.name.endsWith('.tsx') && /focus-visible:ring-/.test(read(next))) {
          offenders.push(next);
        }
      }
    };
    sources.forEach(walk);
    expect(offenders, 'focus styled with an unmeasured ring utility').toEqual([]);
  });
});
