// Tests for scripts/ears-table-check.js
//
// Node built-in test runner (`node --test`), no package.json (D-wqge-04).
// Fixtures live in a fresh mkdtemp under the OS tmpdir, never in the SPEC
// directory (the `spec-check` glob would ingest them) and never in the
// Obsidian vault (repo/CLAUDE.md Regel 1).
//
// Run: just test-scripts scripts/ears-table-check.test.js

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const SCRIPT = path.join(__dirname, 'ears-table-check.js');
const { classifySpecFile } = require('./ears-table-check.js');

const REAL_SPEC_DIR = path.join(
  __dirname, '..', '..', '..', 'docs', 'topics', 'okf-cli-rust-rewrite', 'spec');

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ears-table-check-test-'));
}

function writeFixture(name, content) {
  const dir = tmpDir();
  const file = path.join(dir, name);
  fs.writeFileSync(file, content, 'utf-8');
  return file;
}

function run(args, opts = {}) {
  try {
    const stdout = execFileSync('node', [SCRIPT, ...args], { encoding: 'utf-8', ...opts });
    return { status: 0, stdout, stderr: '' };
  } catch (err) {
    return { status: err.status, stdout: err.stdout ?? '', stderr: err.stderr ?? '' };
  }
}

const SPEC_HEADER = '---\ntype: Spec\n---\n\n';
const REAL_ROW = '| REAL-1 | WHEN x occurs THE system SHALL respond. |\n';

// -- classifySpecFile (D-wqge-05 / D-wqge-05b) --------------------------

test('classifySpecFile: type Spec front-matter classifies as spec', () => {
  const result = classifySpecFile('---\ntype: Spec\n---\n\nbody\n');
  assert.deepEqual(result, { kind: 'spec' });
});

test('classifySpecFile: non-Spec type classifies as skip, names the type', () => {
  const result = classifySpecFile('---\ntype: Reference\n---\n\nbody\n');
  assert.equal(result.kind, 'skip');
  assert.match(result.reason, /type: Reference/);
});

test('classifySpecFile: missing front-matter classifies as error', () => {
  const result = classifySpecFile('# just a heading\n\nno front-matter here\n');
  assert.equal(result.kind, 'error');
  assert.match(result.reason, /front-matter/);
});

test('classifySpecFile: front-matter without type field classifies as error', () => {
  const result = classifySpecFile('---\ntitle: something\n---\n\nbody\n');
  assert.equal(result.kind, 'error');
  assert.match(result.reason, /type field/);
});

// -- AC-01: fenced requirement-shaped rows are not counted --------------

test('AC-01: a requirement-shaped row inside a backtick fence is not counted', () => {
  const file = writeFixture('fenced-backtick.md', SPEC_HEADER +
    '````\n' +
    '| EX-1 | WHEN example occurs THE system SHALL do nothing real. |\n' +
    '````\n\n' +
    REAL_ROW);
  const { status, stdout } = run([file]);
  assert.equal(status, 0);
  assert.match(stdout, /OK\s+.*\(1 requirement\(s\)\)/);
});

test('AC-01: a requirement-shaped row inside a tilde fence is not counted', () => {
  const file = writeFixture('fenced-tilde.md', SPEC_HEADER +
    '~~~~\n' +
    '| EX-1 | WHEN example occurs THE system SHALL do nothing real. |\n' +
    '~~~~\n\n' +
    REAL_ROW);
  const { status, stdout } = run([file]);
  assert.equal(status, 0);
  assert.match(stdout, /OK\s+.*\(1 requirement\(s\)\)/);
});

test('AC-01: an unfenced requirement row is still counted', () => {
  const file = writeFixture('unfenced.md', SPEC_HEADER + REAL_ROW +
    '| REAL-2 | WHEN y occurs THE system SHALL respond too. |\n');
  const { status, stdout } = run([file]);
  assert.equal(status, 0);
  assert.match(stdout, /OK\s+.*\(2 requirement\(s\)\)/);
});

// -- AC-02 / AC-04: declared Spec-file criterion -------------------------

test('AC-02: a non-Spec file is skipped -- not counted, not EARS-checked', () => {
  const specFile = writeFixture('real-spec.md', SPEC_HEADER + REAL_ROW);
  const refFile = writeFixture('README.md',
    '---\ntype: Reference\n---\n\n| NOT-1 | this is not a real EARS statement |\n');
  const { status, stdout } = run([specFile, refFile]);
  assert.equal(status, 0);
  assert.match(stdout, /SKIP\s+.*README\.md\s+\(non-Spec file: type: Reference\)/);
  assert.doesNotMatch(stdout, /NOT-1/);
});

test('AC-04: a SPEC-directory file with no front-matter fails the run, names the file', () => {
  const specFile = writeFixture('real-spec.md', SPEC_HEADER + REAL_ROW);
  const badFile = writeFixture('no-frontmatter.md', '# heading only\n\nno front-matter\n');
  const { status, stdout } = run([specFile, badFile]);
  assert.equal(status, 1);
  assert.match(stdout, /FAIL\s+.*no-frontmatter\.md\s+\(no readable front-matter/);
});

test('AC-04: a SPEC-directory file with front-matter but no type field fails the run', () => {
  const specFile = writeFixture('real-spec.md', SPEC_HEADER + REAL_ROW);
  const badFile = writeFixture('no-type.md', '---\ntitle: x\n---\n\nbody\n');
  const { status, stdout } = run([specFile, badFile]);
  assert.equal(status, 1);
  assert.match(stdout, /FAIL\s+.*no-type\.md\s+\(front-matter has no type field\)/);
});

// -- AC-03: per-file zero-requirement-rows Spec file ---------------------

test('AC-03: a Spec file with zero requirement rows fails the run, names the file', () => {
  const specFile = writeFixture('real-spec.md', SPEC_HEADER + REAL_ROW);
  const emptyFile = writeFixture('empty-spec.md', SPEC_HEADER + 'just prose, no table\n');
  const { status, stdout } = run([specFile, emptyFile]);
  assert.equal(status, 1);
  assert.match(stdout, /FAIL\s+.*empty-spec\.md\s+\(0 requirement\(s\)/);
  assert.match(stdout, /OK\s+.*real-spec\.md\s+\(1 requirement\(s\)\)/);
});

// existing aggregate zero-case (:the whole invocation carries zero rows) stays intact
test('aggregate zero-case: total zero requirement rows across all files still exits 1', () => {
  const emptyFile = writeFixture('only-empty.md', SPEC_HEADER + 'just prose\n');
  const { status, stdout } = run([emptyFile]);
  assert.equal(status, 1);
  assert.match(stdout, /0 requirement\(s\) found across 1 file\(s\) -- nothing was checked/);
});

// -- AC-08: a real command Spec losing its table form --------------------

test('AC-08: a copy of a real Spec file with its table stripped fails, names the file', () => {
  const realFiles = fs.readdirSync(REAL_SPEC_DIR)
    .filter((f) => f.endsWith('.md') && f !== 'README.md' && f !== '_common.md');
  assert.ok(realFiles.length > 0, 'expected at least one real command spec file');
  const realPath = path.join(REAL_SPEC_DIR, realFiles[0]);
  const raw = fs.readFileSync(realPath, 'utf-8');
  const stripped = raw.replace(/^\|.*\|\s*$/gm, '');
  const copy = writeFixture(realFiles[0], stripped);
  const { status, stdout } = run([copy]);
  assert.equal(status, 1);
  assert.match(stdout, new RegExp(`FAIL\\s+.*${realFiles[0].replace('.', '\\.')}\\s+\\(0 requirement\\(s\\)`));
});

// -- AC-09: existing exit-code meanings are preserved ---------------------

test('AC-09: no file argument -> exit 2', () => {
  const { status, stderr } = run([]);
  assert.equal(status, 2);
  assert.match(stderr, /usage:/);
});

test('AC-09: a caller-named path that does not exist -> exit 2', () => {
  const dir = tmpDir();
  const missing = path.join(dir, 'does-not-exist.md');
  const { status, stderr } = run([missing]);
  assert.equal(status, 2);
  assert.match(stderr, /path does not exist/);
});

test('AC-09: a caller-named path that cannot be read -> exit 3', () => {
  // A directory exists but is not readable as a file (EISDIR), exercising
  // the filesystem-subsystem-failure branch distinct from ENOENT.
  const dir = tmpDir();
  const { status, stderr } = run([dir]);
  assert.equal(status, 3);
  assert.match(stderr, /subsystem "filesystem"/);
});

test('AC-09: missing validator dependency -> exit 3', () => {
  const specFile = writeFixture('real-spec.md', SPEC_HEADER + REAL_ROW);
  const fakeHome = tmpDir();
  const { status, stderr } = run([specFile], {
    env: { ...process.env, HOME: fakeHome, EARS_VALIDATOR: '' },
  });
  assert.equal(status, 3);
  assert.match(stderr, /subsystem "ears-validator" unavailable/);
});

test('AC-09: an EARS violation -> exit 1', () => {
  const file = writeFixture('violation.md', SPEC_HEADER +
    '| BAD-1 | THE system should respond eventually. |\n');
  const { status, stdout } = run([file]);
  assert.equal(status, 1);
  assert.match(stdout, /BAD-1/);
});

// -- success path ---------------------------------------------------------

test('a clean Spec file with valid rows exits 0 and reports the count', () => {
  const file = writeFixture('clean.md', SPEC_HEADER + REAL_ROW +
    '| REAL-2 | WHEN y occurs THE system SHALL respond too. |\n');
  const { status, stdout } = run([file]);
  assert.equal(status, 0);
  assert.match(stdout, /OK — 2 requirement\(s\) across 1 file\(s\), 0 violations/);
});
