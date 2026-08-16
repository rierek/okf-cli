---
# okf-cli-03o1
title: okf CLI rewrite in Rust
status: in-progress
type: milestone
priority: high
created_at: 2026-08-09T20:44:20Z
updated_at: 2026-08-11T19:20:49Z
---

Port the okf CLI from Python to Rust. Motive is distribution: a Python CLI ships only with a Python runtime.

Scope is capability equality, not a line-by-line port (PO ruling): where a better solution exists in Rust, it is used. The MCP server ships with the binary as `okf mcp serve`, because agents are the primary consumer.

Two extensions over OKF v0.1 are explicit: the optional semantic arm, and the knowledge-catalogue store model on top of the standalone bundle. Both are switchable in `.okf.toml` (D05, D06).

## State

Spec phase complete. `docs/okf-cli-rust-rewrite/` carries AUDIT, DECISIONS and 26 EARS spec files, 348 requirements, gate `just spec-check` green.

Branch `docs/rust-rewrite-spec`, worktree `/Users/erik/dev/okf-tools-spec`, base `main @ a73a60e`.
Branch `fix/b01-b02-bundle-validation` @ `b5a9f1d` carries the Python-side B01/B02 fix, suite 559 green.

Neither branch is merged. Both wait on the peer session that realises milestone `okf-cli-wuiv` on `main`.

## Finding

The semantic arm needs no Python. Both embedding paths are HTTP clients (Voyage over HTTPS, bge-m3 over Ollama on localhost:11434), vectors are LE-float32 blobs in SQLite, cosine is three lines. The CLI imports standard library only.

## PO decisions 2026-08-11
D08-D14 confirmed: `index <bundle> --summary` is compact while the default is full; profiles are `okf` and `catalogue` with individual overrides; bundle paths are root-relative; `check --profile okf` is an isolated hard gate; semantic retrieval defaults on only in `catalogue`; precedence is CLI/MCP argument > config override > profile > built-in default.
