---
# okf-cli-unxt
title: T09 — delete plugin/ and its index-map line
status: completed
type: task
priority: low
created_at: 2026-08-09T20:44:41Z
updated_at: 2026-08-11T19:47:24Z
parent: okf-cli-03o1
---

D05 rules out a plugin system. The plugin/ skeleton is dead; remove it and the entry in docs/okf-tools-okf/index-map.md.

## PO decision 2026-08-11
D05 remains confirmed: remove the rejected plugin skeleton and its stale index-map entry.

## Completion 2026-08-11
`plugin/` is absent and the stale `plugin/` entry was removed from `docs/docs-index-map.md`. `just spec-check` passed with 356 requirements and zero violations.
