---
# okf-cli-5436
title: 'archive: point at --restore when the missing source sits in the archive'
status: todo
type: feature
priority: high
created_at: 2026-08-10T06:45:10Z
updated_at: 2026-08-10T06:45:41Z
parent: okf-cli-0xkj
---

PO side finding, 2026-08-10 review of US-04.


## Origin — PO review 2026-08-10, side finding on US-04

The PO ran `archive agent-memory/mein-konzept --apply` twice in a row. The second run answered:

```
archive: source not found: /Users/erik/Obsidian/Knowledge-Catalogue/agent-memory/mein-konzept.md
```

Formally correct — `cmd_archive` only guards the *direction* (R-03), and `agent-memory/mein-konzept` does not lie under `_archive/`, so the miss falls through to the generic "source not found" of `perform_rename`. The three direction guards themselves were verified working in the same session and are not in question.

### Why the PO wants it anyway (verbatim, German)

> also mir ist es ja passiert - daher wäre das wichtig, dass auch dieser Fehler abgefangen wird. Denn wenn bspw. ein Verweis in einer Unterlage liegt und stale ist, dann ist das der direkte Hinweis, dass ich dann im Archiv schauen kann.

That reframes the finding. This is not cosmetics on an error string: the message is a navigation signal. A reader who follows a stale reference out of some document and lands on a missing concept needs to be told the concept still exists, one directory over. The tool already holds that fact at the moment it errors — it computed `dest_rel` two lines earlier — and withholds it.

### Shape of the fix

In `cmd_archive` (cli/okf-cli.py:4214), on the non-restore path, before delegating to `perform_rename`: if `src_abs` does not exist but `dest_abs` does, fail with a message that names the archived path and the `--restore` verb instead of the bare "source not found". The mirrored case on the `--restore` path is worth considering too — a restore of something that already sits active.

Do not move the check into `perform_rename`. That function is shared with `rename`, which has no archive semantics; archive-specific knowledge belongs in the archive-specific caller, same reasoning as the three existing direction guards (SPEC.md section 2).

Acceptance: a missing source whose derived archive path exists errors with a message naming that path and `--restore`; a missing source with no archived counterpart keeps the current message.
