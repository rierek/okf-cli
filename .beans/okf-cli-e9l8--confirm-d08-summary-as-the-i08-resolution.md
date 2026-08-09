---
# okf-cli-e9l8
title: 'Confirm D08: --summary as the I08 resolution'
status: todo
type: task
created_at: 2026-08-09T20:44:56Z
updated_at: 2026-08-09T20:44:56Z
parent: okf-cli-03o1
---

`--summary` is the only invented identifier across all 26 spec files. It resolves the `--full` duality of `index` that I08 demands.

I08 requires the split but names no flag, and an unnamed flag makes INDEX-7 unauditable as an audit cell — so the name stands in the spec rather than being left blank. It is recorded as D08 with status yellow in `docs/okf-cli-rust-rewrite/DECISIONS.md`, explicitly marked as not PO-confirmed.

Needs a yes or a different name. Not an agent decision.
