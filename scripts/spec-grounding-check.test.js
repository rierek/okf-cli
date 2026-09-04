// Tests for scripts/spec-grounding-check.js (OKFT-g0xq).
//
// CLAUDE.md Regel 7: these tests IMPORT the production sub-steps and drive
// them through their real inputs -- they do not reimplement the anchor
// regex, the symbol resolver, or the fragment comparison by hand. Every
// exported "Teilschritt" (erfassen: collectReferences/classifyReference,
// aufloesen: resolveDefinitionSite, vergleichen: fragmentPresent) is
// exercised through the import, never re-derived.
//
// Fixtures live in this file's own strings / a per-test mkdtemp -- never in
// the SPEC directory (D-wqge-15), never in the vault.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const {
  classifyReference,
  collectReferences,
  resolveDefinitionSite,
  fragmentPresent,
  parseSymbolSpec,
} = require('./spec-grounding-check.js');

const SCRIPT = path.join(__dirname, 'spec-grounding-check.js');

function runCli(args, cwd) {
  try {
    const stdout = execFileSync('node', [SCRIPT, ...args], { cwd, encoding: 'utf-8' });
    return { code: 0, stdout, stderr: '' };
  } catch (err) {
    return { code: err.status, stdout: err.stdout || '', stderr: err.stderr || '' };
  }
}

function mkroot() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'spec-grounding-'));
}

// ---------------------------------------------------------------------
// Teilschritt "altform-erkennen": classifyReference
// ---------------------------------------------------------------------

test('classifyReference: AC-05(a) path-prefixed digit -> legacy-colon', () => {
  const c = classifyReference('`cli/okf-cli.py:2093`');
  assert.equal(c.kind, 'legacy-colon');
  assert.equal(c.file, 'cli/okf-cli.py');
  assert.equal(c.location, '2093');
});

test('classifyReference: AC-05(a) path-prefixed digit range -> legacy-colon', () => {
  const c = classifyReference('`cli/okf-cli.py:2093-2151`');
  assert.equal(c.kind, 'legacy-colon');
  assert.equal(c.location, '2093-2151');
});

test('classifyReference: AC-05(b) bare backtick digit range -> legacy-bare', () => {
  const c = classifyReference('`2093-2151`');
  assert.equal(c.kind, 'legacy-bare');
  assert.equal(c.file, null);
});

test('classifyReference: AC-05(c) bare paren digit range -> legacy-paren', () => {
  const c = classifyReference('(2093-2151)');
  assert.equal(c.kind, 'legacy-paren');
  assert.equal(c.location, '2093-2151');
});

test('classifyReference: compliant function anchor -> anchor', () => {
  const c = classifyReference('`cli/okf-cli.py:cmd_reindex()`');
  assert.equal(c.kind, 'anchor');
  assert.equal(c.file, 'cli/okf-cli.py');
  assert.equal(c.location, 'cmd_reindex()');
});

test('classifyReference: compliant class anchor -> anchor', () => {
  const c = classifyReference('`cli/okf-cli.py:BundleIndex`');
  assert.equal(c.kind, 'anchor');
});

test('classifyReference: compliant method anchor -> anchor', () => {
  const c = classifyReference('`cli/okf-cli.py:BundleIndex.rebuild()`');
  assert.equal(c.kind, 'anchor');
  assert.equal(c.location, 'BundleIndex.rebuild()');
});

test('classifyReference: running-prose number is not a legacy form -> other', () => {
  // "13 Zeilen" style prose number, not backtick- or paren-delimited as a
  // grounding reference -- classifyReference only ever sees delimited
  // tokens from collectReferences, but must also reject them if handed one.
  assert.equal(classifyReference('13').kind, 'other');
  assert.equal(classifyReference('cli/okf-cli.py').kind, 'other');
});

test('classifyReference: Feinanker fragment text -> other, not a legacy/anchor form', () => {
  const c = classifyReference('`if not args.force:`');
  assert.equal(c.kind, 'other');
});

test('classifyReference: unrelated file path with colon -> other', () => {
  const c = classifyReference('`some/other.py:thing()`');
  assert.equal(c.kind, 'other');
});

// ---------------------------------------------------------------------
// Teilschritt "erfassen": collectReferences
// ---------------------------------------------------------------------

test('AC-01/AC-08: collectReferences finds prefixed AND prefix-less (elliptical) refs', () => {
  const text = [
    '## Grounding',
    '',
    'Erfassung `cli/okf-cli.py:cmd_reindex()`, danach `2093-2151` als Altrest.',
  ].join('\n');
  const refs = collectReferences(text);
  assert.equal(refs.length, 2);
  assert.equal(refs[0].kind, 'anchor');
  assert.equal(refs[1].kind, 'legacy-bare');
});

test('collectReferences: fenced code blocks are excluded (anchors live only in prose)', () => {
  const text = [
    '## Grounding',
    '',
    '```',
    '`cli/okf-cli.py:2093` -- this is example text inside a fence, not a reference',
    '```',
    '',
    'Real reference: `cli/okf-cli.py:cmd_reindex()`',
  ].join('\n');
  const refs = collectReferences(text);
  assert.equal(refs.length, 1);
  assert.equal(refs[0].raw, '`cli/okf-cli.py:cmd_reindex()`');
});

test('collectReferences: tilde fence also excluded', () => {
  const text = [
    '~~~',
    '`cli/okf-cli.py:2093`',
    '~~~',
    'real `cli/okf-cli.py:cmd_reindex()`',
  ].join('\n');
  const refs = collectReferences(text);
  assert.equal(refs.length, 1);
});

test('collectReferences: Feinanker fragment attaches to the preceding anchor, not counted twice', () => {
  const text = 'Grounding: `cli/okf-cli.py:cmd_reindex()` (`if not args.force:`).';
  const refs = collectReferences(text);
  assert.equal(refs.length, 1);
  assert.equal(refs[0].kind, 'anchor');
  assert.equal(refs[0].fragment, 'if not args.force:');
});

test('collectReferences: paren-legacy detected outside backticks, with correct line number', () => {
  const text = ['line one', 'anchor at (2093-2151) here'].join('\n');
  const refs = collectReferences(text);
  assert.equal(refs.length, 1);
  assert.equal(refs[0].kind, 'legacy-paren');
  assert.equal(refs[0].line, 2);
});

test('collectReferences: a number embedded in running prose is not collected', () => {
  const text = 'Es gibt 357 requirement(s) in dieser SPEC, Version 13.';
  const refs = collectReferences(text);
  assert.equal(refs.length, 0);
});

// ---------------------------------------------------------------------
// Teilschritt "aufloesen": resolveDefinitionSite (D-wqge-12, definition site only)
// ---------------------------------------------------------------------

const SAMPLE_SOURCE = [
  'RESERVED = {"index.md"}',
  '',
  'def helper_used_elsewhere():',
  '    return cmd_reindex()',   // a CALL site -- must never satisfy resolution (D-wqge-12)
  '',
  'def cmd_reindex(force=False):',
  '    if not args.force:',
  '        pass',
  '    return 0',
  '',
  'class BundleIndex:',
  '    """docstring"""',
  '',
  '    def rebuild(self):',
  '        touch_marker()',
  '        return True',
  '',
  '    def other(self):',
  '        pass',
  '',
  '    def other(self):',
  '        return "bundle-other"',
  '',
  'def after_class():',
  '    pass',
  '',
].join('\n');

const SAMPLE_SOURCE_2 = SAMPLE_SOURCE + [
  'class SecondIndex:',
  '    def other(self):',
  '        return "second-other"',
  '',
  '    def second_only(self):',
  '        return "only-in-second"',
  '',
].join('\n');

test('resolveDefinitionSite: resolves a top-level function at its def line, not a call site', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE, 'cmd_reindex()');
  assert.equal(r.ok, true);
  assert.match(r.body, /^def cmd_reindex\(/);
  assert.doesNotMatch(r.body, /helper_used_elsewhere/);
});

test('D-wqge-12: a call-site-only symbol with no def anywhere does not resolve', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE, 'touch_marker()');
  assert.equal(r.ok, false);
  assert.match(r.reason, /no definition/);
});

test('D-wqge-12: method resolution is scoped to its named class, not the first same-named method anywhere', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE_2, 'SecondIndex.other()');
  assert.equal(r.ok, true);
  assert.match(r.body, /second-other/);
  assert.doesNotMatch(r.body, /bundle-other/);
});

test('D-wqge-12: class boundary blocks a forward leak into a later class with no such method', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE_2, 'BundleIndex.second_only()');
  assert.equal(r.ok, false);
  assert.match(r.reason, /BundleIndex/);
});

test('resolveDefinitionSite: resolves a class', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE, 'BundleIndex');
  assert.equal(r.ok, true);
  assert.match(r.body, /^class BundleIndex:/);
  assert.match(r.body, /def rebuild/);
});

test('resolveDefinitionSite: resolves a method scoped to its class, not a same-named top-level fn', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE, 'BundleIndex.rebuild()');
  assert.equal(r.ok, true);
  assert.match(r.body, /^\s+def rebuild\(self\):/);
  assert.match(r.body, /touch_marker/);
});

test('resolveDefinitionSite: unknown class fails by name, not silently', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE, 'Nope.rebuild()');
  assert.equal(r.ok, false);
  assert.match(r.reason, /class Nope/);
});

test('resolveDefinitionSite: unknown method inside a real class fails, distinct reason', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE, 'BundleIndex.missing()');
  assert.equal(r.ok, false);
  assert.match(r.reason, /BundleIndex/);
});

test('resolveDefinitionSite: malformed symbol syntax (leftover line number) fails explicitly', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE, '2093');
  assert.equal(r.ok, false);
  assert.match(r.reason, /malformed symbol syntax/);
});

test('parseSymbolSpec: distinguishes func/class/method grammar', () => {
  assert.deepEqual(parseSymbolSpec('foo()'), { kind: 'func', name: 'foo' });
  assert.deepEqual(parseSymbolSpec('Foo'), { kind: 'class', name: 'Foo' });
  assert.deepEqual(parseSymbolSpec('Foo.bar()'), { kind: 'method', cls: 'Foo', name: 'bar' });
  assert.equal(parseSymbolSpec('2093'), null);
});

test('parseSymbolSpec: SCREAMING_SNAKE resolves to const, checked before class', () => {
  assert.deepEqual(parseSymbolSpec('MARK_START'), { kind: 'const', name: 'MARK_START' });
  assert.deepEqual(parseSymbolSpec('RESERVED'), { kind: 'const', name: 'RESERVED' });
});

// ---------------------------------------------------------------------
// D-wqge-21/AC-11: module-level constants as a fourth symbol form
// ---------------------------------------------------------------------

const CONST_SOURCE = [
  'import re',
  '',
  'MARK_START = "<!-- start -->"',
  'MARK_END = "<!-- end -->"',
  '',
  'RESERVED = {',
  '    "index.md",',
  '    "README.md",',
  '}',
  '',
  'class Config:',
  '    DEFAULT_TIMEOUT = 30', // indented -- must never satisfy a module-const lookup
  '',
  'class SCREAMING:',
  '    pass',
  '',
].join('\n');

test('AC-11 branch 1: module constant found at column 0', () => {
  const r = resolveDefinitionSite(CONST_SOURCE, 'MARK_START');
  assert.equal(r.ok, true);
  assert.match(r.body, /^MARK_START = /);
});

test('AC-11 branch 2: an indented same-named assignment is rejected, distinct reason', () => {
  const r = resolveDefinitionSite(CONST_SOURCE, 'DEFAULT_TIMEOUT');
  assert.equal(r.ok, false);
  assert.match(r.reason, /not a module constant/);
  assert.match(r.reason, /column 0/);
});

test('AC-11 branch 3: an all-caps class name is resolved as const, not class -- fails by name', () => {
  const r = resolveDefinitionSite(CONST_SOURCE, 'SCREAMING');
  assert.equal(r.ok, false);
  assert.match(r.reason, /no module assignment "SCREAMING" found/);
});

test('AC-11 branch 4: fine-anchor fragment found across a multi-line constant body', () => {
  const r = resolveDefinitionSite(CONST_SOURCE, 'RESERVED');
  assert.equal(r.ok, true);
  assert.equal(fragmentPresent(r.body, '"index.md"'), true);
  assert.equal(fragmentPresent(r.body, '"nonexistent.md"'), false);
});

// ---------------------------------------------------------------------
// Teilschritt "vergleichen": fragmentPresent (AC-09)
// ---------------------------------------------------------------------

test('AC-09: fragmentPresent true when fragment occurs verbatim in body', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE, 'cmd_reindex()');
  assert.equal(fragmentPresent(r.body, 'if not args.force:'), true);
});

test('AC-09: fragmentPresent false when fragment is absent', () => {
  const r = resolveDefinitionSite(SAMPLE_SOURCE, 'cmd_reindex()');
  assert.equal(fragmentPresent(r.body, 'if not args.other:'), false);
});

// ---------------------------------------------------------------------
// CLI integration: exit codes and end-to-end behaviour, own mkdtemp
// ---------------------------------------------------------------------

function writeSpecFile(dir, name, body) {
  const full = [
    '---',
    'type: Spec',
    `title: "${name} — EARS-Requirements"`,
    'description: "fixture"',
    'tags: [okf-cli]',
    '---',
    '',
    body,
  ].join('\n');
  fs.writeFileSync(path.join(dir, name), full);
}

test('CLI: no file argument -> exit 2', () => {
  const root = mkroot();
  const r = runCli([], root);
  assert.equal(r.code, 2);
  assert.match(r.stderr, /usage/);
});

test('CLI: a caller-named path that does not exist -> exit 2', () => {
  const root = mkroot();
  const r = runCli(['nope.md'], root);
  assert.equal(r.code, 2);
});

test('CLI: a Spec file whose anchor resolves cleanly against a real target file -> exit 0', () => {
  const root = mkroot();
  fs.mkdirSync(path.join(root, 'cli'));
  fs.writeFileSync(path.join(root, 'cli', 'okf-cli.py'), SAMPLE_SOURCE);
  writeSpecFile(root, 'x.md', [
    '## Grounding',
    '',
    'Der Kern: `cli/okf-cli.py:cmd_reindex()` (`if not args.force:`).',
  ].join('\n'));
  const r = runCli(['x.md'], root);
  assert.equal(r.code, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /OK — 1 grounding reference\(s\)/);
});

test('AC-02: an anchor whose symbol is not defined anywhere -> exit 1, names file/reference/reason', () => {
  const root = mkroot();
  fs.mkdirSync(path.join(root, 'cli'));
  fs.writeFileSync(path.join(root, 'cli', 'okf-cli.py'), SAMPLE_SOURCE);
  writeSpecFile(root, 'x.md', [
    '## Grounding',
    '',
    'Ghost: `cli/okf-cli.py:does_not_exist()`.',
  ].join('\n'));
  const r = runCli(['x.md'], root);
  assert.equal(r.code, 1);
  assert.match(r.stdout, /x\.md:10/);
  assert.match(r.stdout, /does_not_exist/);
});

test('AC-05/AC-06: any remaining legacy-form reference -> exit 1, names the form', () => {
  const root = mkroot();
  fs.mkdirSync(path.join(root, 'cli'));
  fs.writeFileSync(path.join(root, 'cli', 'okf-cli.py'), SAMPLE_SOURCE);
  writeSpecFile(root, 'x.md', [
    '## Grounding',
    '',
    'Alt: `cli/okf-cli.py:2093-2151`.',
  ].join('\n'));
  const r = runCli(['x.md'], root);
  assert.equal(r.code, 1);
  assert.match(r.stdout, /legacy form/);
});

test('a non-Spec file is skipped -- not counted, not checked', () => {
  const root = mkroot();
  fs.writeFileSync(path.join(root, 'y.md'), '---\ntype: Reference\ntitle: "y"\n---\n\nno grounding here');
  const r = runCli(['y.md'], root);
  assert.equal(r.code, 1); // total===0 across all checked files -> nothing-was-checked finding
  assert.match(r.stdout, /SKIP/);
});

test('AC-01/AC-08: the printed total matches the independently counted population', () => {
  const root = mkroot();
  fs.mkdirSync(path.join(root, 'cli'));
  fs.writeFileSync(path.join(root, 'cli', 'okf-cli.py'), SAMPLE_SOURCE);
  writeSpecFile(root, 'x.md', [
    '## Grounding',
    '',
    'Anker: `cli/okf-cli.py:cmd_reindex()`. Altform prefixed: `cli/okf-cli.py:2093`.',
    'Altform bare: `2093-2151`. Altform paren: liegt bei (2093-2151) im Code.',
  ].join('\n'));
  const r = runCli(['x.md'], root);
  assert.equal(r.code, 1);
  assert.match(r.stdout, /4 reference\(s\) checked/);
});

test('subsystem failure: target source file missing -> exit 3, names the target file', () => {
  const root = mkroot();
  // cli/okf-cli.py deliberately absent.
  writeSpecFile(root, 'x.md', [
    '## Grounding',
    '',
    'Ref: `cli/okf-cli.py:cmd_reindex()`.',
  ].join('\n'));
  const r = runCli(['x.md'], root);
  assert.equal(r.code, 3);
  assert.match(r.stderr, /target-file/);
  assert.match(r.stderr, /cli\/okf-cli\.py/);
});
