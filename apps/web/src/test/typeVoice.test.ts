import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

/**
 * Batch 242 (owner, 25 Nov 2026; review findings X1 and X5): one label voice, colours
 * that exist, and the two layout glitches the review found on the game screens.
 *
 * These read the source because the faults were invisible to every rendered test: a
 * class name Tailwind never generates renders nothing and throws nothing, and jsdom
 * computes no layout, so a label that only fits in another font passes everywhere.
 */

const SRC = resolve(process.cwd(), 'src');

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      return name === 'test' || name === '__tests__' ? [] : sources(path);
    }
    return path.endsWith('.tsx') ? [path] : [];
  });
}

const files = sources(SRC).map((path) => ({
  path: relative(SRC, path),
  text: readFileSync(path, 'utf8'),
}));

/** Every quoted class string in a file, with the file it came from. */
function classStrings(): Array<{ path: string; value: string }> {
  return files.flatMap(({ path, text }) =>
    Array.from(text.matchAll(/"([^"\n]*)"|'([^'\n]*)'/g), (match) => ({
      path,
      value: match[1] ?? match[2] ?? '',
    })),
  );
}

describe('the type voice and colour names (Batch 242)', () => {
  it('uses no ink colour name, which the theme never generates', () => {
    // `text-*` resolves the brand and semantic names to their `-ink` tokens through
    // tailwind.config.ts, so `text-success` is the ink colour and `text-success-ink` is
    // nothing at all: won and lost labels rendered in the plain text colour for weeks.
    const dead = files.flatMap(({ path, text }) =>
      Array.from(
        text.matchAll(
          /\b(?:text|bg|border|fill|stroke)-(?:success|error|warning|primary|accent|live|gold|bronze)-ink\b/g,
        ),
        (match) => `${path}: ${match[0]}`,
      ),
    );
    expect(dead).toEqual([]);
  });

  it('never sets words in spaced-out monospace capitals outside the wordmark', () => {
    const wide = /^tracking-\[0\.(1[5-9]|[23]\d*)em\]$/;
    const offenders = classStrings()
      .filter(({ path }) => path !== join('components', 'Brand.tsx'))
      .filter(({ value }) => {
        const tokens = value.split(/\s+/);
        return (
          tokens.includes('font-mono') &&
          tokens.includes('uppercase') &&
          tokens.some((token) => wide.test(token))
        );
      })
      .map(({ path, value }) => `${path}: ${value}`);
    expect(offenders).toEqual([]);
  });

  it('defines the one label style in the app font', () => {
    const css = readFileSync(join(SRC, 'index.css'), 'utf8');
    const rule = /@utility eyebrow \{([^}]*)\}/.exec(css);
    expect(rule, 'index.css has no @utility eyebrow').not.toBeNull();
    expect(rule![1]).toMatch(/font-family:\s*'Outfit'/);
    expect(rule![1]).toMatch(/text-transform:\s*uppercase/);
    expect(rule![1]).toMatch(/letter-spacing:\s*0\.06em/);
    expect(rule![1]).not.toMatch(/mono/i);
  });

  it("wraps a price tile's points line instead of cutting it off", () => {
    // "YOUR PICK · 15 P…" on a phone: monospace capitals in a two-column tile.
    for (const path of [
      join('components', 'FantasyFixtureCard.tsx'),
      join('components', 'GroupFixtureCard.tsx'),
      join('components', 'PickCard.tsx'),
    ]) {
      const text = files.find((file) => file.path === path)!.text;
      expect(text, path).not.toContain('w-full truncate text-caption font-mono uppercase');
      expect(text, path).toContain('w-full break-words text-caption font-sans');
    }
  });

  it('never fades a price tile, so its points line cannot lag a theme switch', () => {
    // The two-game stories caught it (25 Nov): tiles faded their colours while the points
    // line, which sets its own, switched at once and sat on the old background mid-fade.
    for (const path of [
      join('components', 'FantasyFixtureCard.tsx'),
      join('components', 'GroupFixtureCard.tsx'),
      join('components', 'PickCard.tsx'),
    ]) {
      const text = files.find((file) => file.path === path)!.text;
      // Batch 245 (owner-approved, 25 Nov 2026): the compact rows' tiles are 44px tall.
      const start = text.search(/flex min-h-(?:\[56px\]|11) flex-col/);
      expect(start, `${path} has no price tile`).toBeGreaterThan(-1);
      // The tile's class list runs from its base string to the first transition it names.
      const transition = /transition-[a-z]+/.exec(text.slice(start, start + 800));
      expect(transition?.[0], path).toBe('transition-none');
    }
  });

  it('keeps the sticky picks bar under the top bar and over the tab bar', () => {
    const slip = files.find((file) => file.path === join('components', 'FantasySlip.tsx'))!.text;
    const bar = /<div className="(sticky bottom-[^"]*)">/.exec(slip);
    expect(bar, 'no sticky slip bar').not.toBeNull();
    const tokens = bar![1].split(/\s+/);
    // The scale in tailwind.config.ts: tab bar 40, top bar 50, banner 55.
    expect(tokens).toContain('z-[45]');
    expect(tokens).not.toContain('z-banner');
  });
});
