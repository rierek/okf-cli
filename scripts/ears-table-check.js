#!/usr/bin/env node
// EARS conformance gate for the Rust-rewrite SPEC files.
//
// The house EARS validator (ce-beans-operationalize/scripts/ears-validator.js)
// only parses numbered lists under "#### Acceptance Criteria" and **SC-###**
// checkboxes -- the bean acceptance shape. The persistent-Spec shape used by
// lean-stack-okf/dev-cli-conformance is a markdown table, so it goes
// unvalidated today. This adapter closes that gap: it extracts requirement
// rows from the tables and hands each statement to the house validator's
// exported validateEarsStatement(), so there is exactly one EARS ruleset in
// play, not a second implementation that could drift from it.
//
// Usage:  node scripts/ears-table-check.js <file.md> [<file.md> ...]
// Exit:   0 all statements valid | 1 violations found | 2 usage/setup error

const fs = require('fs');
const path = require('path');

const VALIDATOR = path.join(
  process.env.HOME, '.claude', 'skills', 'ce-beans-operationalize',
  'scripts', 'ears-validator.js');

if (!fs.existsSync(VALIDATOR)) {
  console.error('ears-table-check: house validator not found at ' + VALIDATOR);
  console.error('hint: this gate reuses the ce-beans-operationalize validator; ' +
                'it is not vendored here on purpose, so the ruleset stays single-source.');
  process.exit(2);
}
const { validateEarsStatement } = require(VALIDATOR);

// A requirement row: | <ID> | <EARS statement> |
// The ID is <SCOPE>-<n>; the scope may itself contain hyphens (FIX-CROSSLINKS-1),
// so the number is the digits after the LAST hyphen.
const ROW_RE = /^\|\s*([A-Z][A-Z0-9-]*-\d+)\s*\|\s*(.+?)\s*\|\s*$/;

function checkFile(file) {
  const lines = fs.readFileSync(file, 'utf-8').split('\n');
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

console.log(failed === 0
  ? `\nOK — ${total} requirement(s) across ${files.length} file(s), 0 violations`
  : `\n${failed} VIOLATION(S) across ${files.length} file(s)`);
process.exit(failed === 0 ? 0 : 1);
