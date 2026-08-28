import { describe, it, expect } from 'vitest';
import { resolveNextDestination } from '@/lib/redirect';

const ORIGIN = 'https://the-coupon.example';

function next(value: string): string {
  return resolveNextDestination(`?next=${encodeURIComponent(value)}`, ORIGIN);
}

describe('resolveNextDestination — destinations that must be refused', () => {
  // OPS-08 / GHSA-wrjc-x8rr-h8h6. Each of these starts with a single `/` and so passed
  // the `startsWith('/') && !startsWith('//')` guard this replaced. Browsers resolve `\`
  // as `/` inside a special scheme, so every one of them left the app's origin.
  it.each([
    ['backslash authority', '/\\evil.com'],
    ['backslash then slash', '/\\/evil.com'],
    ['slash then backslash', '/\\\\evil.com'],
    ['backslash with a path', '/\\evil.com/steal'],
    ['backslash with credentials', '/\\user:pw@evil.com'],
  ])('refuses %s (%s)', (_label, payload) => {
    expect(next(payload)).toBe('/');
  });

  // The forms the original guard did stop. Kept so the rewrite cannot regress them
  // while closing the backslash gap.
  it.each([
    ['protocol-relative', '//evil.com'],
    ['protocol-relative with path', '//evil.com/steal'],
    ['absolute https', 'https://evil.com'],
    ['absolute http', 'http://evil.com'],
    ['scheme-less host', 'evil.com'],
    ['javascript scheme', 'javascript:alert(1)'],
    ['data scheme', 'data:text/html,<script>alert(1)</script>'],
    ['relative path', 'join/ABC123'],
    ['empty', ''],
  ])('refuses %s (%s)', (_label, payload) => {
    expect(next(payload)).toBe('/');
  });

  it('falls back when there is no ?next at all', () => {
    expect(resolveNextDestination('', ORIGIN)).toBe('/');
    expect(resolveNextDestination('?name=Alice', ORIGIN)).toBe('/');
  });

  it('refuses a same-origin-looking host that only shares a prefix', () => {
    // `the-coupon.example.evil.com` starts with the real host as a string but is a
    // different origin — the reason this compares parsed origins rather than prefixes.
    expect(next('/\\the-coupon.example.evil.com')).toBe('/');
  });
});

describe('resolveNextDestination — destinations that must survive', () => {
  it('keeps the invite path that gives ?next its reason to exist', () => {
    expect(next('/join/ABC123')).toBe('/join/ABC123');
  });

  it('keeps a deep league path with query and hash', () => {
    expect(next('/leagues/the-coupon/predictions/coupon?gw=abc#top')).toBe(
      '/leagues/the-coupon/predictions/coupon?gw=abc#top',
    );
  });

  it('keeps the root', () => {
    expect(next('/')).toBe('/');
  });

  it('returns the parsed path, not the caller string', () => {
    // Normalising is the point: what gets handed to react-router is what was actually
    // validated, so the two cannot diverge on a form the parser reads differently.
    expect(next('/join/../join/ABC123')).toBe('/join/ABC123');
  });
});
