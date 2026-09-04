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
//              violation, or files were read but carried zero requirement
//              rows (a silently-empty gate is itself a finding).
//   2  COM-23  the invocation itself is malformed: no file argument, or a
//              caller-named path does not exist.
//   3  COM-24  a failure outside the invocation and outside the checked
//              input's content -- the house validator dependency is
//              missing, or a caller-named path exists but cannot be read.
//              The message names the failing subsystem.

const fs = require('fs');
const path = require('path');

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

// A requirement row: | <ID> | <EARS statement> |
// The ID is <SCOPE>-<n>; the scope may itself contain hyphens (FIX-CROSSLINKS-1),
// so the number is the digits after the LAST hyphen.
const ROW_RE = /^\|\s*([A-Z][A-Z0-9-]*-\d+)\s*\|\s*(.+?)\s*\|\s*$/;

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

  const lines = raw.split('\n');
  const issues = [];
  const ids = new Map();
  let count = 0;

  lines.forEach((line, i) => {
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

  return { file, count, issues };
}

const files = process.argv.slice(2);
if (files.length === 0) {
  console.error('usage: node scripts/ears-table-check.js <file.md> [<file.md> ...]');
  process.exit(2);
}

let total = 0, failed = 0;
for (const file of files) {
  const { count, issues } = checkFile(file);
  total += count;
  const rel = path.relative(process.cwd(), file);
  if (issues.length === 0) {
    console.log(`${count === 0 ? 'EMPTY  ' : 'OK     '}  ${rel}  (${count} requirement(s))`);
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
  : `\n${failed} VIOLATION(S) across ${files.length} file(s)`);
process.exit(failed === 0 ? 0 : 1);
