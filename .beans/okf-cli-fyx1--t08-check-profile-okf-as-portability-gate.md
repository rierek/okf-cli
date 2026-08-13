---
# okf-cli-fyx1
title: T08 — check --profile okf as portability gate
status: completed
type: task
priority: normal
created_at: 2026-08-09T20:44:41Z
updated_at: 2026-08-11T19:47:24Z
parent: okf-cli-03o1
---

A bundle that passes under the okf profile holds OKF v0.1 without this catalogue. Falls out of CHECK-9; needs no separate command, only the profile.

## PO decision 2026-08-11
D11 and D14 are confirmed: `check --profile okf` evaluates only OKF v0.1 rules and rejects extension flags or MCP parameters with usage error.

## Completion 2026-08-11
D11 and D14 are encoded by CHECK-9 and CHECK-21, including conflicts from CLI arguments, MCP parameters and `.okf.toml` overrides. `just spec-check` passed with 356 requirements and zero violations.
