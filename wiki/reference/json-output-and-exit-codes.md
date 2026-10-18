---
title: "JSON output and exit codes"
description: "The --json envelope and exit-code classes 0 to 5."
---

## Purpose

Specify machine-readable output and the meaning of each exit code.

## Audience

A script, CI or agent author who consumes okf output.

## Required sections

### Envelope

- `{command, ok, data, warnings, error}`; what `data` holds per command family. Source: FACTS §Topic: `--json` envelope.

### Exit-code classes

- Table: code, name, meaning, which commands return it. Source: FACTS §Topic: exit-code classes.
- `tags --validate` and the ctx verbs `show`, `read`, `check`, `edit` exit 4 where the help says 1 [irxe] [vf2r]. Source: FACTS §Defect list a, g.
- A blocked `install` plan exits 1 with a generic message [fs8c]. Source: FACTS §Defect list j.
- Exit codes beyond the observed ones for 17 commands are read from code only. TODO: verify archive, ctx add/create/drop/move/remove/rename, fix-crosslinks, merge-tags, migrate, normalize-tags, registry convert, remove-tags, rename, rewrite-path, sync-insert, sync-update

### Failures

- Error envelope and stderr text. Source: FACTS §Topic: `--json` envelope; FACTS §Topic: exit-code classes.
