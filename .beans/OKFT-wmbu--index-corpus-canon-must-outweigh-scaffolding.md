---
# OKFT-wmbu
title: 'Index corpus: canon must outweigh scaffolding'
status: todo
type: epic
priority: high
created_at: 2026-08-13T11:07:04Z
updated_at: 2026-08-13T11:07:04Z
---

Root cause behind OKFT-xori and OKFT-oe8t: the catalogue has no notion of a topic folder. is_bundle_dir (okf-cli.py:68-69) is a two-clause name filter - anything without a leading dot or underscore is a bundle - and it never opens the directory. Correct at the catalogue root, where every top-level directory really is a bundle; wrong for every directory but one in a repo docs root.

Measured 2026-08-13 against lean-stack/docs: the FTS corpus holds 197 documents, of which 41 are bundle concepts (21%) and 156 are TPIC scaffolding (79%). Over ten real agent queries, 64 of 87 global hits (74%) were scaffolding, and scaffolding held rank 1 in six of ten. Six dispatched agents issued ten find calls, none of them scoped.

The missing distinction is already declared: .okf.toml carries bundle = "<name>" in every repo docs root. okf-cli parses that file through load_okf_config and consumes types_source and wikilink_checked_bundles from it, but never reads the bundle key.

Requirement: honour the declaration for the index and search corpus only. Full rationale in lean-stack docs/aca_capability-mcp/DECISIONS.md D16/D17 and REFERENCES.md R33-R42.
