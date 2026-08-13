---
# okf-cli-bu0p
title: T07 — store abstraction per command
status: completed
type: task
priority: normal
created_at: 2026-08-09T20:44:41Z
updated_at: 2026-08-11T19:47:24Z
parent: okf-cli-03o1
---

Per-command decision on how the store model (D06: bundle vs catalogue) reaches the command logic. Follows from COM-1 to COM-8.

## PO decision 2026-08-11
D10 is confirmed: in bundle mode every path and scope is bundle-root-relative without a bundle prefix; in catalogue mode it remains catalogue-root-relative with a bundle segment.

## Completion 2026-08-11
D10 is encoded by COM-46 and COM-47: Bundle operands are store-root-relative without a bundle selector; Catalogue operands are store-root-relative with the first segment as bundle selector. `just spec-check` passed with 356 requirements and zero violations.
