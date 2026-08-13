---
# OKFT-0k55
title: Handle BrokenPipeError in cmd_find
status: todo
type: bug
created_at: 2026-08-13T11:07:31Z
updated_at: 2026-08-13T11:07:31Z
parent: OKFT-wmbu
---

okf-cli find <query> | head aborts with an unhandled BrokenPipeError traceback at okf-cli.py:1652 (print("type: {}".format(h["type"]))). No SIGPIPE handling anywhere in the command.

A stacktrace is not an actionable error message. Observed 2026-08-13 while measuring global vs scoped output. Feeds the CLI-program conformance spec being drafted in lean-stack (docs/aca_capability-mcp/DECISIONS.md D20).
