---
title: "Installation"
description: "Install the okf binary with Homebrew, a release asset or a source build."
---

## Purpose

Get a working `okf` on PATH on macOS or Linux and check that it runs.

## Audience

A new user on macOS or Linux (amd64 or arm64) with a shell; no catalogue needed yet.

## Required sections

### Result sentence

- Bold sentence: after this page `okf --help` runs on your machine. Source: FACTS §Topic: install.

### Install command

- One command line directly under the result sentence (the primary path). TODO: verify which path is primary while the formula is head-only; see [71rn]
- Homebrew: `brew install okf-cli` per README, but the repo formula declares only `head` and builds from source with `just` and `go` [71rn]. Source: FACTS §Topic: Homebrew formula; FACTS §Defect list c.

### Release binary

- Assets `okf-darwin-arm64`, `okf-darwin-amd64`, `okf-linux-amd64`, `okf-linux-arm64`; download, make executable, put on PATH. Source: FACTS §Topic: release assets.
- No statement whether the macOS binaries are signed or notarised [c0mc]. Source: FACTS §Topic: release assets; FACTS §Defect list f.

### Build from source

- Clone, `just go-build`, binary at `go/bin/okf`. Source: FACTS §Topic: install; justfile recipe go-build.
- Clone URL and release URLs: the repo is `rierek/okf-cli`; older docs name `xRiErOS`. [zs6t]. Source: FACTS §Topic: install.

### Verify the install

- `okf --help` is the check: there is no `--version` [i2ws]. Source: FACTS §Topic: install; FACTS §Defect list d.

### Register okf with agents and shells (optional)

- `okf install` previews, `okf install --apply` writes, `--uninstall` undoes; completion for zsh, bash and fish. Source: FACTS §Topic: install; FACTS §Topic: shell completion.

### Update and uninstall

- Homebrew upgrade, new release asset over the old file, `git pull && just go-build`; then `okf install --apply` again. Source: FACTS §Topic: install.

### Reference

- Links to the `okf install` command page and Troubleshooting. Source: FACTS §okf install.
