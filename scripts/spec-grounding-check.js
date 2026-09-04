#!/usr/bin/env node
// Grounding-truth gate for the Rust-rewrite SPEC files (OKFT-g0xq).
//
// `scripts/ears-table-check.js` gates the EARS form of the requirement
// tables; grounding truth -- whether a cited symbol actually stands where a
// SPEC file says it does -- is a different subject and lives here as its
// own tool (D-wqge-09), reusing the Spec-file criterion from that module
// instead of rebuilding it (D-wqge-10).
//
// Anchor form (D-wqge-06, decided): `<zieldatei>:<symbol>()` /
// `<zieldatei>:<Klasse>` / `<zieldatei>:<Klasse.methode>()`, in backticks,
// in Grounding prose, `<zieldatei>` one of the three target files. No line
// number, ever -- neither alone, nor as a range, nor next to a symbol. An
// optional fine anchor follows immediately: `` (`<literal fragment>`) ``.
//
// The legacy form this gate must recognise and reject is pinned
// syntactically (AC-05, precise as of bean commit 4944408) -- exactly
// three shapes, no intent-guessing:
//   (a) `<zieldatei>:<digit…>`            -- path prefix, numeric location
//   (b) `<digit…>` (bare, in backticks)   -- the 49 context-inheriting refs
//   (c) `(<digit…>-<digit…>)`             -- bare range in parens
// Anything else (running prose numbers, Feinanker code fragments, unrelated
// backtick text) is not a grounding reference and is not counted.
//
// Symbols are resolved at their DEFINITION SITE (D-wqge-12): `def <name>(`
// / `class <name>`, never a substring match anywhere in the file. The
// three target files are read from the tree that carries the state
// (D-wqge-13) -- the current working directory, i.e. the worktree `just
// spec-grounding` is invoked from, never a hardcoded path.
//
// Exit codes (same convention as ears-table-check.js):
//   0  clean -- every reference resolved, no legacy form found.
//   1  a finding about the checked SPEC content: an unresolved anchor, a
//      fine-anchor fragment absent from the symbol body, or a reference
//      still in legacy form.
//   2  the invocation itself is malformed: no file argument, or a
//      caller-named path does not exist.
//   3  a failure outside the invocation and outside the checked input's
//      content: a target source file cannot be read, or classifySpecFile's
//      dependency is missing.
//
// Usage: node scripts/spec-grounding-check.js <file.md> [<file.md> ...]

const fs = require('fs');
const path = require('path');
const { classifySpecFile } = require('./ears-table-check.js');

// The three target files an Option-C anchor may name (D-wqge-06).
const TARGET_FILES = ['cli/okf-cli.py', 'mcp/okf_mcp.py', 'cli/test_okf_cli.py'];
const TARGET_FILE_ALT = TARGET_FILES.map(f => f.replace(/\//g, '\\/').replace(/\./g, '\\.')).join('|');

// A CommonMark fence marker -- identical convention to ears-table-check.js,
// duplicated here (not imported) because it is a generic markdown-parsing
// utility, not the identity-bearing mechanism D-wqge-10 guards.
const FENCE_RE = /^ {0,3}(`{3,}|~{3,})/;

// One backtick-delimited span, single line (anchors never span lines).
const BACKTICK_SPAN_RE = /`([^`\n]+)`/g;

// A bare digit range in parens, not inside backticks (legacy form c).
const PAREN_LEGACY_RE = /\(([0-9]{3,4}-[0-9]{3,4})\)/g;

// A path-prefixed reference: `<target-file>:<rest>`.
const FILE_PREFIX_RE = new RegExp(`^(${TARGET_FILE_ALT}):(.+)$`);

// Symbol-anchor grammar (D-wqge-06).
const FUNC_RE = /^([A-Za-z_][A-Za-z0-9_]*)\(\)$/;
const CLASS_RE = /^([A-Za-z_][A-Za-z0-9_]*)$/;
const METHOD_RE = /^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\(\)$/;
// Module-level constant (D-wqge-21, extended D-wqge-25): SCREAMING_SNAKE,
// optional leading underscores (private module attribute), no parens.
// Checked BEFORE class -- a bare all-caps identifier is deterministically
// a constant, never a class, even if a same-named class happens to exist.
const CONST_RE = /^(_*[A-Z][A-Z0-9_]*)$/;

// -- Teilschritt "altform-erkennen": classify one raw token (delimiters
// included) into an anchor or one of the three pinned legacy forms, or
// 'other' if it is not a grounding reference at all. Single source of
// truth for "which forms are legacy" -- collectReferences never re-derives
// this, it only calls it.
function classifyReference(raw) {
  if (raw.startsWith('(') && raw.endsWith(')')) {
    const inner = raw.slice(1, -1);
    if (/^[0-9]{3,4}-[0-9]{3,4}$/.test(inner)) {
      return { kind: 'legacy-paren', file: null, location: inner };
    }
    return { kind: 'other' };
  }
  if (!(raw.startsWith('`') && raw.endsWith('`'))) {
    return { kind: 'other' };
  }
  const inner = raw.slice(1, -1);
  const fileMatch = inner.match(FILE_PREFIX_RE);
  if (fileMatch) {
    const [, file, loc] = fileMatch;
    if (/^[0-9]/.test(loc)) {
      return { kind: 'legacy-colon', file, location: loc };
    }
    return { kind: 'anchor', file, location: loc };
  }
  if (/^[0-9]{2,4}(-[0-9]{2,4})?$/.test(inner)) {
    return { kind: 'legacy-bare', file: null, location: inner };
  }
  return { kind: 'other' };
}

// -- Teilschritt "erfassen": walk the (fence-stripped) SPEC text and
// collect every grounding reference -- compliant anchors AND all three
// legacy forms (D-wqge-11: the input set is never built from the path
// prefix alone, so the 49 prefix-less legacy refs are not skipped).
function collectReferences(text) {
  const lines = text.split('\n');
  const refs = [];
  let fenceChar = null;
  let fenceLen = 0;

  lines.forEach((line, i) => {
    const fenceMatch = line.match(FENCE_RE);
    if (fenceMatch) {
      const marker = fenceMatch[1];
      const char = marker[0];
      const len = marker.length;
      if (fenceChar === null) {
        fenceChar = char;
        fenceLen = len;
      } else if (char === fenceChar && len >= fenceLen) {
        fenceChar = null;
        fenceLen = 0;
      }
      return;
    }
    if (fenceChar !== null) return;

    // Backtick-delimited references, plus optional trailing Feinanker.
    let m;
    BACKTICK_SPAN_RE.lastIndex = 0;
    while ((m = BACKTICK_SPAN_RE.exec(line)) !== null) {
      const raw = m[0];
      const classified = classifyReference(raw);
      if (classified.kind === 'other') continue;

      let fragment = null;
      if (classified.kind === 'anchor') {
        const rest = line.slice(m.index + raw.length);
        const fineMatch = rest.match(/^\s*\(`([^`]+)`\)/);
        if (fineMatch) fragment = fineMatch[1];
      }

      refs.push({
        raw,
        line: i + 1,
        kind: classified.kind,
        file: classified.file,
        location: classified.location,
        fragment,
      });
    }

    // Bare-paren legacy references, only outside backtick spans.
    const masked = line.replace(BACKTICK_SPAN_RE, s => ' '.repeat(s.length));
    PAREN_LEGACY_RE.lastIndex = 0;
    while ((m = PAREN_LEGACY_RE.exec(masked)) !== null) {
      const raw = m[0];
      const classified = classifyReference(raw);
      if (classified.kind === 'other') continue;
      refs.push({
        raw,
        line: i + 1,
        kind: classified.kind,
        file: classified.file,
        location: classified.location,
        fragment: null,
      });
    }
  });

  return refs;
}

function indentOf(line) {
  const m = line.match(/^[ \t]*/);
  return m ? m[0].length : 0;
}

// From startIdx (inclusive) to the next non-blank line whose indentation is
// <= the start line's indentation, bounded by boundaryIdx (exclusive).
function extractBlock(lines, startIdx, boundaryIdx) {
  const startIndent = indentOf(lines[startIdx]);
  let end = boundaryIdx;
  for (let i = startIdx + 1; i < boundaryIdx; i++) {
    const line = lines[i];
    if (line.trim() === '') continue;
    if (indentOf(line) <= startIndent) {
      end = i;
      break;
    }
  }
  return { body: lines.slice(startIdx, end).join('\n'), end };
}

function parseSymbolSpec(location) {
  let m = location.match(METHOD_RE);
  if (m) return { kind: 'method', cls: m[1], name: m[2] };
  m = location.match(FUNC_RE);
  if (m) return { kind: 'func', name: m[1] };
  m = location.match(CONST_RE);
  if (m) return { kind: 'const', name: m[1] };
  m = location.match(CLASS_RE);
  if (m) return { kind: 'class', name: m[1] };
  return null;
}

// -- Teilschritt "aufloesen": find the symbol's DEFINITION SITE (D-wqge-12)
// in sourceText and return its body, or a named failure reason. Never a
// substring match -- a function is `^def <name>\(`, a class `^class
// <name>\b`, a method the first `def <name>\(` inside the named class's
// (indentation-bounded) body.
function resolveDefinitionSite(sourceText, location) {
  const spec = parseSymbolSpec(location);
  if (!spec) {
    return { ok: false, body: null, reason: `malformed symbol syntax: "${location}"` };
  }
  const lines = sourceText.split('\n');

  if (spec.kind === 'func') {
    const re = new RegExp(`^def ${spec.name}\\(`);
    const idx = lines.findIndex(l => re.test(l));
    if (idx === -1) {
      return { ok: false, body: null, reason: `no definition "def ${spec.name}(" found` };
    }
    return { ok: true, body: extractBlock(lines, idx, lines.length).body, reason: null };
  }

  if (spec.kind === 'const') {
    const colZeroRe = new RegExp(`^${spec.name}\\s*(:[^=]*)?=`);
    const idx = lines.findIndex(l => colZeroRe.test(l));
    if (idx !== -1) {
      return { ok: true, body: extractBlock(lines, idx, lines.length).body, reason: null };
    }
    const indentedRe = new RegExp(`^\\s+${spec.name}\\s*(:[^=]*)?=`);
    if (lines.some(l => indentedRe.test(l))) {
      return {
        ok: false, body: null,
        reason: `indented assignment "${spec.name}" is not a module constant (not at column 0)`,
      };
    }
    return { ok: false, body: null, reason: `no module assignment "${spec.name}" found` };
  }

  if (spec.kind === 'class') {
    const re = new RegExp(`^class ${spec.name}\\b`);
    const idx = lines.findIndex(l => re.test(l));
    if (idx === -1) {
      return { ok: false, body: null, reason: `no definition "class ${spec.name}" found` };
    }
    return { ok: true, body: extractBlock(lines, idx, lines.length).body, reason: null };
  }

  // method
  const classRe = new RegExp(`^class ${spec.cls}\\b`);
  const classIdx = lines.findIndex(l => classRe.test(l));
  if (classIdx === -1) {
    return { ok: false, body: null, reason: `no definition "class ${spec.cls}" found` };
  }
  const classEnd = extractBlock(lines, classIdx, lines.length).end;
  const methodRe = new RegExp(`^\\s+def ${spec.name}\\(`);
  let methodIdx = -1;
  for (let i = classIdx + 1; i < classEnd; i++) {
    if (methodRe.test(lines[i])) {
      methodIdx = i;
      break;
    }
  }
  if (methodIdx === -1) {
    return {
      ok: false, body: null,
      reason: `no definition "def ${spec.name}(" found inside class ${spec.cls}`,
    };
  }
  return { ok: true, body: extractBlock(lines, methodIdx, classEnd).body, reason: null };
}

// -- Teilschritt "vergleichen": does the fine-anchor fragment occur, VERBATIM,
// in the resolved symbol's body (AC-09)?
function fragmentPresent(body, fragment) {
  return body.includes(fragment);
}

function describeLegacy(ref) {
  if (ref.kind === 'legacy-colon') return `legacy form: "${ref.raw}" (path-prefixed line reference)`;
  if (ref.kind === 'legacy-bare') return `legacy form: "${ref.raw}" (bare, context-inheriting line reference)`;
  return `legacy form: "${ref.raw}" (bare range in parens)`;
}

module.exports = {
  classifyReference,
  collectReferences,
  resolveDefinitionSite,
  fragmentPresent,
  parseSymbolSpec,
  TARGET_FILES,
};

if (require.main === module) {
  const files = process.argv.slice(2);
  if (files.length === 0) {
    console.error('usage: node scripts/spec-grounding-check.js <file.md> [<file.md> ...]');
    process.exit(2);
  }

  const sourceCache = new Map();
  function readTarget(rel) {
    if (sourceCache.has(rel)) return sourceCache.get(rel);
    const abs = path.join(process.cwd(), rel);
    let text = null;
    let error = null;
    try {
      text = fs.readFileSync(abs, 'utf-8');
    } catch (err) {
      error = err;
    }
    const entry = { text, error };
    sourceCache.set(rel, entry);
    return entry;
  }

  let total = 0;
  let failed = 0;
  let subsystemFailure = null;

  for (const file of files) {
    let raw;
    try {
      raw = fs.readFileSync(file, 'utf-8');
    } catch (err) {
      if (err.code === 'ENOENT') {
        console.error(`spec-grounding-check: path does not exist: ${file}`);
        process.exit(2);
      }
      console.error(`spec-grounding-check: subsystem "filesystem" failed reading ${file}: ${err.message}`);
      process.exit(3);
    }

    const rel = path.relative(process.cwd(), file);
    const classification = classifySpecFile(raw);
    if (classification.kind === 'error') {
      failed++;
      console.log(`FAIL     ${rel}  (${classification.reason})`);
      continue;
    }
    if (classification.kind === 'skip') {
      console.log(`SKIP     ${rel}  (non-Spec file: ${classification.reason})`);
      continue;
    }

    const refs = collectReferences(raw);
    total += refs.length;
    const issues = [];

    for (const ref of refs) {
      if (ref.kind !== 'anchor') {
        issues.push({ line: ref.line, error: describeLegacy(ref) });
        continue;
      }
      const source = readTarget(ref.file);
      if (source.error) {
        subsystemFailure =
          `spec-grounding-check: subsystem "target-file" unavailable -- could not read ${ref.file}` +
          ` (referenced ${rel}:${ref.line}): ${source.error.message}`;
        break;
      }
      const resolution = resolveDefinitionSite(source.text, ref.location);
      if (!resolution.ok) {
        issues.push({ line: ref.line, error: `"${ref.raw}" -- ${resolution.reason}` });
        continue;
      }
      if (ref.fragment !== null && !fragmentPresent(resolution.body, ref.fragment)) {
        issues.push({
          line: ref.line,
          error: `"${ref.raw}" (\`${ref.fragment}\`) -- fragment not found in body of "${ref.location}"`,
        });
      }
    }
    if (subsystemFailure) break;

    if (issues.length === 0) {
      console.log(`OK       ${rel}  (${refs.length} reference(s))`);
    } else {
      failed += issues.length;
      console.log(`FAIL     ${rel}  (${refs.length} reference(s), ${issues.length} violation(s))`);
      for (const it of issues) {
        console.log(`  ${rel}:${it.line}  ${it.error}`);
      }
    }
  }

  if (subsystemFailure) {
    console.error(subsystemFailure);
    process.exit(3);
  }

  if (total === 0) {
    console.log(`\n0 grounding reference(s) found across ${files.length} file(s) -- nothing was checked`);
    process.exit(1);
  }

  console.log(failed === 0
    ? `\nOK — ${total} grounding reference(s) across ${files.length} file(s), 0 violations`
    : `\n${failed} FINDING(S) across ${files.length} file(s) (${total} reference(s) checked)`);
  process.exit(failed === 0 ? 0 : 1);
}
