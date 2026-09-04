'use strict';

// Testheimat fuer scripts/spec-dir.sh (OKFT-g01s). Node built-in runner,
// keine package.json, kein npm -- Konvention D-wqge-04. Jede Fixtur lebt
// ausschliesslich unter einem eigenen mkdtemp-Baum, nie im SPEC-Verzeichnis
// und nie im Vault (CLAUDE.md Regel 1 sinngemaess).

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const SCRIPT = path.resolve(__dirname, 'spec-dir.sh');

function mkdtemp(prefix) {
  return fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), prefix));
}

function run(cwd, envOverrides) {
  return spawnSync(SCRIPT, [], {
    cwd,
    env: { ...process.env, ...envOverrides },
    encoding: 'utf8',
  });
}

function gitInit(dir) {
  const res = spawnSync('git', ['init', '-q', '.'], { cwd: dir, encoding: 'utf8' });
  assert.equal(res.status, 0, `git init failed in ${dir}: ${res.stderr}`);
}

test('path 1: not inside a git checkout -> exit 3, named subsystem', () => {
  const root = mkdtemp('okft-g01s-nogit-');
  const cwd = path.join(root, 'work');
  fs.mkdirSync(cwd);
  const res = run(cwd, { GIT_CEILING_DIRECTORIES: root });
  assert.equal(res.status, 3);
  assert.match(res.stderr, /spec-check: subsystem "spec-dir" unavailable -- not inside a git checkout/);
});

test('path 2: git checkout, no repo/+docs hull found -> exit 3, named subsystem', () => {
  const root = mkdtemp('okft-g01s-nohull-');
  const cwd = path.join(root, 'onlygit');
  fs.mkdirSync(cwd);
  gitInit(cwd);
  const res = run(cwd, { GIT_CEILING_DIRECTORIES: root });
  assert.equal(res.status, 3);
  assert.match(res.stderr, /spec-check: subsystem "spec-dir" unavailable -- no hull \(repo\/\+docs\/\) found walking up from/);
});

test('path 3: hull found, SPEC directory missing -> exit 3, named subsystem', () => {
  const root = mkdtemp('okft-g01s-nospec-');
  const repoDir = path.join(root, 'hull', 'repo');
  fs.mkdirSync(path.join(root, 'hull', 'docs'), { recursive: true });
  fs.mkdirSync(repoDir, { recursive: true });
  gitInit(repoDir);
  const res = run(repoDir, { GIT_CEILING_DIRECTORIES: root });
  assert.equal(res.status, 3);
  assert.match(res.stderr, /spec-check: subsystem "spec-dir" unavailable -- hull found at .*, but SPEC directory missing at/);
});

test('path 4 (AC-01): cd into dirname(git-common-dir) fails -> exit 3, named subsystem, distinguishable message', () => {
  const root = mkdtemp('okft-g01s-cdfail-');
  const binDir = path.join(root, 'bin');
  fs.mkdirSync(binDir);
  // Common dir whose PARENT does not exist -- constructs the precondition
  // deterministically (no race, no sudo): dirname($gcd) is unreadable/absent
  // the moment the script tries to cd into it.
  const vanishedParent = path.join(root, 'vanished-parent');
  const fakeCommonDir = path.join(vanishedParent, '.git');
  const fakeGit = [
    '#!/usr/bin/env bash',
    'if [ "$1" = "rev-parse" ] && [ "$2" = "--git-common-dir" ]; then',
    `  printf '%s\\n' '${fakeCommonDir}'`,
    '  exit 0',
    'fi',
    'echo "fake-git: unsupported invocation: $*" >&2',
    'exit 1',
    '',
  ].join('\n');
  fs.writeFileSync(path.join(binDir, 'git'), fakeGit, { mode: 0o755 });
  assert.equal(fs.existsSync(vanishedParent), false);

  const cwd = mkdtemp('okft-g01s-cdfail-cwd-');
  const res = run(cwd, { PATH: `${binDir}:${process.env.PATH}` });

  assert.equal(res.status, 3);
  const expectedCore = `spec-check: subsystem "spec-dir" unavailable -- could not enter ${vanishedParent}, derived from git common dir ${fakeCommonDir}`;
  assert.equal(res.stderr.trim(), expectedCore);
  // Distinguishable from the three existing messages (AC-02):
  assert.doesNotMatch(res.stderr, /not inside a git checkout/);
  assert.doesNotMatch(res.stderr, /no hull \(repo\/\+docs\/\) found/);
  assert.doesNotMatch(res.stderr, /but SPEC directory missing at/);
});

test('success path: prints absolute SPEC dir, exit 0, worktree-agnostic (root and nested subdir)', () => {
  const root = mkdtemp('okft-g01s-ok-');
  const repoDir = path.join(root, 'hull', 'repo');
  const specDir = path.join(root, 'hull', 'docs', 'topics', 'okf-cli-rust-rewrite', 'spec');
  fs.mkdirSync(specDir, { recursive: true });
  fs.mkdirSync(repoDir, { recursive: true });
  gitInit(repoDir);

  const fromRoot = run(repoDir, { GIT_CEILING_DIRECTORIES: root });
  assert.equal(fromRoot.status, 0);
  assert.equal(fromRoot.stdout.trim(), specDir);

  const nested = path.join(repoDir, 'nested', 'sub');
  fs.mkdirSync(nested, { recursive: true });
  const fromNested = run(nested, { GIT_CEILING_DIRECTORIES: root });
  assert.equal(fromNested.status, 0);
  assert.equal(fromNested.stdout.trim(), specDir);
});

test('success path (AC-06): identical SPEC dir from a real linked git worktree', () => {
  // The motivating case for D-siyu-07: `git rev-parse --git-common-dir` from a
  // linked worktree returns an ABSOLUTE path into the main checkout's `.git`,
  // not a relative one -- a fixed dirname-step-count would silently break
  // here even though the relative (root/nested) cases above stay green.
  const root = mkdtemp('okft-g01s-wt-');
  const repoDir = path.join(root, 'hull', 'repo');
  const specDir = path.join(root, 'hull', 'docs', 'topics', 'okf-cli-rust-rewrite', 'spec');
  fs.mkdirSync(specDir, { recursive: true });
  fs.mkdirSync(repoDir, { recursive: true });
  gitInit(repoDir);
  const commit = spawnSync(
    'git',
    ['-c', 'user.email=t@example.invalid', '-c', 'user.name=t', 'commit', '--allow-empty', '-q', '-m', 'init'],
    { cwd: repoDir, encoding: 'utf8' },
  );
  assert.equal(commit.status, 0, `git commit failed: ${commit.stderr}`);

  const linkedWorktree = path.join(root, 'linked-wt');
  const wtAdd = spawnSync('git', ['worktree', 'add', '-q', linkedWorktree, '-b', 'okft-g01s-wt-branch'], {
    cwd: repoDir,
    encoding: 'utf8',
  });
  assert.equal(wtAdd.status, 0, `git worktree add failed: ${wtAdd.stderr}`);

  try {
    const fromWorktree = run(linkedWorktree, { GIT_CEILING_DIRECTORIES: root });
    assert.equal(fromWorktree.status, 0, `stderr: ${fromWorktree.stderr}`);
    assert.equal(fromWorktree.stdout.trim(), specDir);
  } finally {
    spawnSync('git', ['worktree', 'remove', '--force', linkedWorktree], { cwd: repoDir, encoding: 'utf8' });
  }
});
