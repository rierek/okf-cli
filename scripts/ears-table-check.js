#!/usr/bin/env node
// EARS conformance gate for the Rust-rewrite SPEC files.
//
// The house EARS validator (operationalize-beans/scripts/ears-validator.js)
// only parses numbered lists under "#### Acceptance Criteria" and **SC-###**
// checkboxes -- the bean acceptance shape. The persistent-Spec shape used by
// lean-stack-okf/dev-cli-conformance is a markdown table, so it goes
// unvalidated today. This adapter closes that gap: it extracts requirement
// rows from the tables and hands each statement to the house validator's
// exported validateEarsStatement(), so there is exactly one EARS ruleset in
// play, not a second implementation that could drift from it.
//
// Usage:  node scripts/ears-table-check.js <file.md> [<file.md> ...]
//
// Exit codes (I09, project convention _common.md:63-70; D-siyu-06/D-siyu-07):
//   0  COM-21  checked, all statements valid.
//   1  COM-22  adverse finding about the checked input -- an EARS
//              violation, a Spec file (declared via front-matter `type:
//              Spec`) that carries zero requirement rows, a SPEC-directory
//              file with unreadable front-matter or no `type` field, or
//              files were read but carried zero requirement rows in total
//              (a silently-empty gate is itself a finding).
//   2  COM-23  the invocation itself is malformed: no file argument, or a
//              caller-named path does not exist.
//   3  COM-24  a failure outside the invocation and outside the checked
//              input's content -- the house validator dependency is
//              missing, or a caller-named path exists but cannot be read.
//              The message names the failing subsystem.

const fs = require('fs');
const path = require('path');

// A requirement row: | <ID> | <EARS statement> |
// The ID is <SCOPE>-<n>; the scope may itself contain hyphens (FIX-CROSSLINKS-1),
// so the number is the digits after the LAST hyphen.
const ROW_RE = /^\|\s*([A-Z][A-Z0-9-]*-\d+)\s*\|\s*(.+?)\s*\|\s*$/;

// A CommonMark fence marker: up to 3 leading spaces, then >=3 backticks or
// >=3 tildes. Captured group is the marker itself (character + length),
// which is what a closing fence must match: same character, length >= open.
const FENCE_RE = /^ {0,3}(`{3,}|~{3,})/;

// The SPEC-file criterion (D-wqge-05): which files in the SPEC directory
// are Spec files that this gate must check is DECLARED via front-matter,
// never derived from a file's content (a content-derived criterion is
// circular -- a Spec file that loses its table would silently fall out of
// the checked set instead of failing it). A file with unreadable
// front-matter or no `type` field is a named finding (D-wqge-05b), not a
// silent skip.
//
// Exported so a second tool (e.g. a grounding check) can reuse this exact
// criterion instead of re-deriving it from content.
function classifySpecFile(raw) {
  const fm = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!fm) {
    return { kind: 'error', reason: 'no readable front-matter (missing --- delimiters)' };
  }
  const typeMatch = fm[1].match(/^type:\s*(.+?)\s*$/m);
  if (!typeMatch) {
    return { kind: 'error', reason: 'front-matter has no type field' };
  }
  const type = typeMatch[1].trim();
  if (type !== 'Spec') {
    return { kind: 'skip', reason: `type: ${type}` };
  }
  return { kind: 'spec' };
}

module.exports = { classifySpecFile };

if (require.main === module) {
  function findValidator() {
    const candidates = [];
    if (process.env.EARS_VALIDATOR) candidates.push(process.env.EARS_VALIDATOR);
    candidates.push(path.join(
      process.env.HOME, '.claude', 'skills', 'operationalize-beans',
      'scripts', 'ears-validator.js'));

    for (const candidate of candidates) {
      if (fs.existsSync(candidate)) return candidate;
    }

    console.error('ears-table-check: subsystem "ears-validator" unavailable -- no candidate found. Checked:');
    for (const candidate of candidates) {
      console.error('  - ' + candidate);
    }
    console.error('hint: this gate reuses the operationalize-beans validator; ' +
                  'it is not vendored here on purpose, so the ruleset stays single-source. ' +
                  'Set EARS_VALIDATOR to override the search.');
    process.exit(3);
  }
  const VALIDATOR = findValidator();
  const { validateEarsStatement } = require(VALIDATOR);

  function checkFile(file) {
    let raw;
    try {
      raw = fs.readFileSync(file, 'utf-8');
    } catch (err) {
      if (err.code === 'ENOENT') {
        console.error(`ears-table-check: path does not exist: ${file}`);
        process.exit(2);
      }
      console.error(`ears-table-check: subsystem "filesystem" failed reading ${file}: ${err.message}`);
      process.exit(3);
    }

    const classification = classifySpecFile(raw);
    if (classification.kind !== 'spec') {
      return { file, classification, count: 0, issues: [] };
    }

    const lines = raw.split('\n');
    const issues = [];
    const ids = new Map();
    let count = 0;
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

      const m = line.match(ROW_RE);
      if (!m) return;
      const [, id, statement] = m;
      count++;

      if (ids.has(id)) {
        issues.push({ line: i + 1, id,
                      error: `duplicate requirement id (first seen on line ${ids.get(id)})` });
      } else {
        ids.set(id, i + 1);
      }

      const issue = validateEarsStatement(statement, i + 1);
      if (issue) {
        issues.push({ line: i + 1, id, error: issue.error, suggestion: issue.suggestion });
      } else if (!statement.includes('SHALL')) {
        issues.push({ line: i + 1, id, error: 'statement carries no SHALL' });
      }
    });

    return { file, classification, count, issues };
  }

  const files = process.argv.slice(2);
  if (files.length === 0) {
    console.error('usage: node scripts/ears-table-check.js <file.md> [<file.md> ...]');
    process.exit(2);
  }

  let total = 0, failed = 0;
  for (const file of files) {
    const { classification, count, issues } = checkFile(file);
    const rel = path.relative(process.cwd(), file);

    if (classification.kind === 'error') {
      failed++;
      console.log(`FAIL     ${rel}  (${classification.reason})`);
      continue;
    }
    if (classification.kind === 'skip') {
      console.log(`SKIP     ${rel}  (non-Spec file: ${classification.reason})`);
      continue;
    }

    total += count;
    if (count === 0) {
      failed++;
      console.log(`FAIL     ${rel}  (0 requirement(s) -- Spec file carries no requirement rows)`);
      continue;
    }
    if (issues.length === 0) {
      console.log(`OK       ${rel}  (${count} requirement(s))`);
      continue;
    }
    failed += issues.length;
    console.log(`FAIL     ${rel}  (${count} requirement(s), ${issues.length} violation(s))`);
    for (const it of issues) {
      console.log(`  ${rel}:${it.line}  ${it.id}: ${it.error}`);
      if (it.suggestion) {
        console.log(it.suggestion.split('\n').map(l => '      ' + l).join('\n'));
      }
    }
  }

  if (total === 0) {
    console.log(`\n0 requirement(s) found across ${files.length} file(s) -- nothing was checked`);
    process.exit(1);
  }

  console.log(failed === 0
    ? `\nOK — ${total} requirement(s) across ${files.length} file(s), 0 violations`
    : `\n${failed} FINDING(S) across ${files.length} file(s)`);
  process.exit(failed === 0 ? 0 : 1);
}
