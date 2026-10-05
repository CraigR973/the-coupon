import { spawnSync } from 'node:child_process';
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';

const SOURCE_GUARD = resolve(process.cwd(), '../../scripts/check-closeout-safety.sh');

type Sandbox = {
  root: string;
  guard: string;
  stampedTree: string;
};

function git(root: string, ...args: string[]): string {
  const result = spawnSync('git', args, { cwd: root, encoding: 'utf8' });
  if (result.status !== 0) {
    throw new Error(`git ${args.join(' ')} failed: ${result.stderr}`);
  }
  return result.stdout.trim();
}

function write(root: string, path: string, contents: string): void {
  const target = join(root, path);
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, contents);
}

function makeSandbox(): Sandbox {
  const root = mkdtempSync(join(tmpdir(), 'coupon-closeout-'));
  git(root, 'init', '--quiet');
  git(root, 'checkout', '--quiet', '-b', 'main');
  git(root, 'config', 'user.name', 'Close-out test');
  git(root, 'config', 'user.email', 'closeout-test@example.invalid');

  const guard = join(root, 'scripts/check-closeout-safety.sh');
  mkdirSync(dirname(guard), { recursive: true });
  copyFileSync(SOURCE_GUARD, guard);
  write(root, 'docs/BUILD_PLAN.md', 'open\n');
  write(root, 'session-log.md', 'before\n');
  write(root, 'STATUS.md', 'before\n');
  git(root, 'add', '-A');
  git(root, 'commit', '--quiet', '-m', 'test baseline');

  return { root, guard, stampedTree: git(root, 'rev-parse', 'HEAD^{tree}') };
}

function stamp(sandbox: Sandbox, contents?: string): void {
  writeFileSync(
    join(sandbox.root, '.git/coupon-ci-local.pass'),
    contents ?? `version=1\nprofile=full\ntree=${sandbox.stampedTree}\n`,
  );
}

function verify(sandbox: Sandbox) {
  return spawnSync('bash', [sandbox.guard, '204', '--verify-gate-stamp'], {
    cwd: sandbox.root,
    encoding: 'utf8',
  });
}

describe('close-out gate stamp reuse', () => {
  const sandboxes: Sandbox[] = [];

  afterEach(() => {
    for (const sandbox of sandboxes.splice(0)) {
      rmSync(sandbox.root, { recursive: true, force: true });
    }
  });

  function sandbox(): Sandbox {
    const created = makeSandbox();
    sandboxes.push(created);
    return created;
  }

  it('accepts an identical real Git tree', () => {
    const repo = sandbox();
    stamp(repo);

    const result = verify(repo);

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('verified ci-local PASS stamp for identical tree');
  });

  it('accepts and names all three close-out document differences', () => {
    const repo = sandbox();
    stamp(repo);
    write(repo.root, 'docs/BUILD_PLAN.md', 'closed\n');
    write(repo.root, 'session-log.md', 'after\n');
    write(repo.root, 'STATUS.md', 'after\n');

    const result = verify(repo);

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('differs only in close-out documents');
    expect(result.stdout).toContain('docs/BUILD_PLAN.md');
    expect(result.stdout).toContain('session-log.md');
    expect(result.stdout).toContain('STATUS.md');
  });

  it.each([
    'docs/agent-commands/probe.md',
    'apps/probe.txt',
    'scripts/probe.txt',
  ])('refuses a difference in %s', (path) => {
    const repo = sandbox();
    stamp(repo);
    write(repo.root, path, 'changed\n');

    const result = verify(repo);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('differs from the ci-local PASS stamp outside');
    expect(result.stderr).toContain(path);
  });

  it('refuses a missing stamp', () => {
    const repo = sandbox();

    const result = verify(repo);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('no matching ci-local PASS stamp');
  });

  it('refuses a truncated stamp', () => {
    const repo = sandbox();
    stamp(repo, 'version=1\nprofile=full\n');

    const result = verify(repo);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('no matching ci-local PASS stamp');
  });

  it('refuses a skipped-browser stamp', () => {
    const repo = sandbox();
    stamp(repo, `version=1\nprofile=partial\ntree=${repo.stampedTree}\n`);

    const result = verify(repo);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('no matching ci-local PASS stamp');
  });

  it('refuses a malformed tree id', () => {
    const repo = sandbox();
    stamp(repo, 'version=1\nprofile=full\ntree=not-a-tree\n');

    const result = verify(repo);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('no matching ci-local PASS stamp');
  });

  it('refuses a stamp whose tree object is absent', () => {
    const repo = sandbox();
    stamp(repo, `version=1\nprofile=full\ntree=${'f'.repeat(40)}\n`);

    const result = verify(repo);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('stamped tree object is missing or invalid');
  });
});
