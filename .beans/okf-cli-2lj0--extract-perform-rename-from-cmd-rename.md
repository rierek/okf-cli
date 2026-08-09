---
# okf-cli-2lj0
title: extract perform_rename from cmd_rename
status: todo
type: task
created_at: 2026-08-09T19:14:20Z
updated_at: 2026-08-09T19:14:20Z
parent: okf-cli-ubxk
---

`cmd_rename` (cli/okf-cli.py:3846) is validation, planning and application in one handler that reads its parameters off an argparse namespace (`args.old`, `args.new`, `args.apply`, `args.force`). A wrapper that assembles such a namespace would be coupled to every later flag change without a test showing it. Lift the body into a function both commands call.

### Requirement 1: Shared rename core

**Objective:** As a CLI maintainer, I want the rename body callable as a plain function, so that `archive` reuses the move machinery instead of forging an argparse namespace.

#### Acceptance Criteria

1. THE okf-cli SHALL provide `perform_rename(root, old_abs, new_abs, apply, force, verb)` holding the validation, planning and application logic currently inside `cmd_rename`.
2. THE okf-cli SHALL implement `cmd_rename` as a call into `perform_rename` with its two paths resolved.
3. WHERE `verb` is supplied THE okf-cli SHALL use it as the prefix of the command's error messages.
4. THE okf-cli SHALL leave the observable behaviour of `rename` unchanged, including its dry-run output, its ambiguity guards and its exit codes.

#### Success Criteria

- SC-01: The existing `rename` test set passes unmodified against the refactored code.

_Requirements: R-04_

## Recommended Skills

- `superpowers:test-driven-development`
