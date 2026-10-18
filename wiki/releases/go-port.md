---
title: "okf as a single Go binary"
description: "The okf CLI is one static Go binary: no Python, no uv, same commands."
date: 2026-10-18
teaser: "One static executable replaces the Python CLI. Same commands, `--json` envelope and exit codes; `okf --help` starts about 35 times faster."
minRead: 3
---

## Why

`okf` started in Python and needed `uv` and a Python interpreter at every start: about 47 ms for `okf --help` and 146 ms for `okf find` (median, Linux amd64). This release replaces the CLI with one Go binary. The commands, options, output formats, `--json` envelope and exit codes stay.

## Highlights

- **The `okf` binary.** One static executable, pure Go, no Python and no `uv`. Release assets: `okf-darwin-arm64`, `okf-darwin-amd64`, `okf-linux-amd64`, `okf-linux-arm64`, next to the wheel, the sdist and the provenance file. Homebrew builds it from source.
- **Faster.** Median of 30 runs on Linux amd64: `okf --help` 1.3 ms against 47 ms (about 35 times), `okf find git` 17 ms against 146 ms (about 9 times). Peak memory of `find`: 55 MiB against 212 MiB.
- **Same commands.** All 33 commands, the 14 `ctx` verbs and `--json` behave as before. The golden suite of 314 cases matches the Python CLI byte for byte in 293 cases; the other 21 differ only in the wording of a YAML parse error.
- **Shell completion** for zsh, bash and fish is answered by the binary. `okf install` writes the scripts embedded in it.
- **MCP server** (still run through `uv`) now calls the binary: `$OKF_BIN`, else `bin/okf` or `go/bin/okf` next to `mcp/`, else `okf` on `PATH`.
- **Frontmatter edits keep your formatting.** The Python CLI re-serialised the frontmatter; the binary patches only the edited lines.

The Python CLI is still published (wheel, sdist, `uv run --script cli/okf-cli.py`).

## What is in this release

{/* generated:start */}

Port the okf CLI to a single Go binary without Python runtime; the golden suite is the acceptance basis, frontmatter writes patch lines minimally, Homebrew, install and completion keep working. MCP server follows later.

## Changes

- [OKFT-qg0o] The repo formula installs the binary without Python resources, the release workflow builds it, CI runs the golden suite against it, the MCP server calls it, and zsh completion works end to end; the Python CLI stays deliverable, no tap publication.
- [OKFT-agws] The Go binary runs check (rule IDs, severity, suppression, spec checks) and verify with the same findings as the Python CLI and passes their golden cases.
- [OKFT-daut] A Go module builds an okf binary with the shared core (root and config, sorted walk, frontmatter read, --where filters, spec, git history, link scan, SQLite and index paths, JSON envelope, exit classes, parser with usage errors) and answers info and --help.
- [OKFT-82n3] The Go binary supports every ctx verb on _ctx/<slug>.md bundles, including per-membership attributes, and passes the ctx golden cases.
- [OKFT-5lq2] Frontmatter writes in Go patch only the intended lines on yaml.v3 node positions (set, append list item, new key), keep comments, quotes and styles byte-equal, reject unpatchable frontmatter, and provide dry-run diffs and the ctx file model to all writers.
- [OKFT-cm5o] The Go binary moves and archives concepts, rewrites paths and cross-links, fixes XML-like tags and regenerates index blocks with minimal diffs, passing the golden cases of these commands.
- [OKFT-jsa8] okf install in Go previews and, with --apply, wires agents and shells exactly like the Python installer, verified in a throwaway HOME.
- [OKFT-se5f] The Go binary serves index, prime, read, toc, list, recent, visualize and refs and passes their golden cases.
- [OKFT-y1zl] The Go binary ranks find via FTS5 and the voyage arm, owns the tagvec write half with both embed backends and the tag-vector producer command, builds all indexes, degrades like Python, passes its golden cases and starts find no slower than Python.
- [OKFT-50ly] The Go binary emits zsh, bash and fish completion scripts and provides the completion protocol plus the generic completers (scopes, concepts, concept files, bundles, dirs, files, tags, ctx slugs) that every command package wires to its arguments, respecting --root.
- [OKFT-dkdu] The Go binary registers, merges, normalizes and removes tags, edits the registry, migrates catalogues and materialises sync blocks, passing the golden cases of these commands.
- [OKFT-ca1y] The Go binary resolves wikilinks and parses sync blocks and the canon index, serves wikilinks, sync-export and sync-status, and passes their golden cases; check, rename and sync writes reuse this model.
- [OKFT-ks1t] The golden harness blocks network access including localhost for any implementation, and no expected output carries Python-specific error text, so the Go binary can be judged by the same suite.
- [OKFT-8dnw] The full golden run, the documented deviation list, the minimal-diff corpus run, the three production catalogues and the startup measurement prove the port ready for PO acceptance.

{/* generated:end */}

## Known limitations

Deviations from the Python CLI and other open findings are listed on the [Known limitations](/okf-cli/known-limitations/) page, for example `[cwyx]` (frontmatter shapes the writer refuses) and `[n760]` (one refused file ends a whole run).

## Upgrade notes

1. Install the new binary: `brew upgrade okf-cli`, or download `okf-<os>-<arch>` from the release.
2. Make sure the new binary is the first `okf` on `PATH`: `type -a okf` and `file "$(command -v okf)"`. Remove an old Python launcher (a Homebrew 0.2.x keg, a pipx or `uv tool` install, a wrapper that runs `uv run --script …`).
3. Run `okf install --apply` again, so skills, the MCP entry and the completion scripts point at the new version. A release binary on its own installs completion only; use Homebrew or a clone for the skill and the MCP server.
4. Restart your agent sessions.
5. Existing indexes (`.fts/fts.sqlite`, `.tagvec/tag_vectors.sqlite`) built by the Python CLI keep working; no rebuild is needed.
