import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

/**
 * Batch 141. The web app shipped `Cache-Control`, `Permissions-Policy`,
 * `Referrer-Policy` and `X-Content-Type-Options` and nothing else — no CSP, no
 * `frame-ancestors`, no `X-Frame-Options`. The API's own headers were exemplary by
 * contrast, and the gap matters here because the client holds a thirty-day refresh
 * token in `localStorage`: with no CSP there is no second line of defence if script
 * ever runs on this origin, and with no frame-ancestors the app can be framed.
 *
 * This file holds the parts of the policy that can be checked from the source. The
 * part that can only be checked by running it — that the real bundle loads clean under
 * the real policy — is `e2e/prod-bundle-csp.spec.ts`.
 */

const WEB = process.cwd();
interface HostCondition {
  type: string;
  value: string;
}
interface HeaderRule {
  source: string;
  has?: HostCondition[];
  missing?: HostCondition[];
  headers: { key: string; value: string }[];
}
const VERCEL = JSON.parse(readFileSync(resolve(WEB, 'vercel.json'), 'utf8')) as {
  headers: HeaderRule[];
};
const INDEX_HTML = readFileSync(resolve(WEB, 'index.html'), 'utf8');

const rootHeaders =
  VERCEL.headers.find((entry) => entry.source === '/(.*)')?.headers ?? [];
const header = (key: string) =>
  rootHeaders.find((entry) => entry.key.toLowerCase() === key.toLowerCase())?.value;

/** `directive-name` → its value, from a policy string. */
function directives(policy: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of policy.split(';')) {
    const [name, ...rest] = part.trim().split(/\s+/);
    if (name) out[name] = rest.join(' ');
  }
  return out;
}

describe('the shipped Content-Security-Policy', () => {
  const policy = header('Content-Security-Policy');

  it('is served on every route', () => {
    expect(policy, 'no Content-Security-Policy in vercel.json').toBeDefined();
  });

  it('cannot be framed, twice over', () => {
    expect(directives(policy!)['frame-ancestors']).toBe("'none'");
    // Superseded by frame-ancestors where CSP is understood, kept for where it is not.
    expect(header('X-Frame-Options')).toBe('DENY');
  });

  it.each([
    ['default-src', "'self'"],
    ['base-uri', "'self'"],
    ['object-src', "'none'"],
    ['form-action', "'self'"],
    ['font-src', "'self'"],
    ['worker-src', "'self'"],
    ['manifest-src', "'self'"],
  ])('locks %s to %s', (name, value) => {
    expect(directives(policy!)[name]).toBe(value);
  });

  it('names the API origin explicitly rather than allowing any https', () => {
    const connect = directives(policy!)['connect-src'];
    expect(connect).toContain('https://api-production-109b1.up.railway.app');
    // Batch 182: one static file still serves the production and staging Vercel projects,
    // but each now gets its own policy, so production no longer reaches the staging API.
    expect(connect).not.toContain('https://api-production-0641.up.railway.app');
    expect(connect).not.toMatch(/https:\/\/\*|\bhttps:(\s|$)/);
  });

  it('allows no inline or remote script beyond the one hash', () => {
    const script = directives(policy!)['script-src'];
    expect(script).not.toContain("'unsafe-inline'");
    expect(script).not.toContain("'unsafe-eval'");
    expect(script.replace(/'sha256-[^']+'/g, '').trim()).toBe("'self'");
  });
});

/**
 * Batch 182. One `vercel.json` serves both Vercel projects, so production's policy used to
 * allow the staging API and any Supabase project's images. Each environment now gets its own
 * policy by host: staging's is chosen only on the staging project's host, and production's
 * everywhere else — so an unexpected host fails closed to production's narrower list rather
 * than open to staging's.
 */
describe('the policy is chosen per environment', () => {
  const STAGING_HOST = 'the-coupon-staging.vercel.app';
  const rootRules = VERCEL.headers.filter((entry) => entry.source === '/(.*)');
  const production = rootRules[0];
  const staging = rootRules.find((rule) => rule.has !== undefined);
  const csp = (rule: HeaderRule | undefined) =>
    directives(rule!.headers.find((entry) => entry.key === 'Content-Security-Policy')!.value);

  it('is two rules split on the staging host, so exactly one applies to any request', () => {
    expect(rootRules).toHaveLength(2);
    expect(production.has).toBeUndefined();
    expect(production.missing).toEqual([{ type: 'host', value: STAGING_HOST }]);
    expect(staging?.has).toEqual([{ type: 'host', value: STAGING_HOST }]);
    expect(staging?.missing).toBeUndefined();
  });

  it("gives staging its own API and storage host, and production none of staging's", () => {
    expect(csp(staging)['connect-src']).toBe(
      "'self' https://api-production-0641.up.railway.app",
    );
    expect(csp(staging)['img-src']).toBe(
      "'self' data: blob: https://gegcnhoeudpkcoxqcebe.supabase.co",
    );
    expect(csp(production)['connect-src']).toBe(
      "'self' https://api-production-109b1.up.railway.app",
    );
  });

  it("allows images only from this project's storage, not any Supabase project", () => {
    expect(csp(production)['img-src']).toBe(
      "'self' data: blob: https://pugujiiojitstkilphrz.supabase.co",
    );
    expect(csp(production)['img-src']).not.toContain('*');
  });

  it('differs between the two only in the hosts it names', () => {
    const rest = (rule: HeaderRule | undefined) => {
      const { 'connect-src': _connect, 'img-src': _img, ...others } = csp(rule);
      return others;
    };
    expect(rest(staging)).toEqual(rest(production));
    const others = (rule: HeaderRule | undefined) =>
      rule!.headers.filter((entry) => entry.key !== 'Content-Security-Policy');
    expect(others(staging)).toEqual(others(production));
  });
});

describe("the hash of index.html's inline script", () => {
  /**
   * The one inline script is the pre-mount theme apply, which has to run before React
   * or the first paint is the wrong palette. Vite copies it into `dist/index.html`
   * verbatim — it does not minify inline HTML scripts — so the hash computed here is
   * the hash of what ships.
   *
   * This test is the reason the hash is safe to hard-code: editing that script without
   * updating the policy fails the gate rather than blanking the theme in production.
   */
  const inline = [...INDEX_HTML.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)];

  it('is the only inline script in the document', () => {
    expect(inline).toHaveLength(1);
  });

  it('matches the hash the policy allows', () => {
    const digest = createHash('sha256').update(inline[0][1]).digest('base64');
    expect(directives(header('Content-Security-Policy')!)['script-src']).toContain(
      `'sha256-${digest}'`,
    );
  });
});
