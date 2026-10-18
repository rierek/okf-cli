---
title: "Contribute"
description: "Report bugs, build okf from source, run the tests, license and credit."
---

## Purpose

Tell a contributor how to report a problem and how to build and test okf.

## Audience

A user who found a bug; a developer who wants to change okf.

## Required sections

### Report bugs and requests

- Read Known limitations first; then the issue tracker of `github.com/xRiErOS/okf-cli`. Source: CONTRIBUTING.md:1-8.

### Build from source

- Go module in `go/`, `just go-build`, binary at `go/bin/okf`. Source: FACTS §Topic: install; justfile.

### Test

- `just test`, `just golden`, `just golden-go`, `just go-completion-scripts --check`, `just completion-check`. Source: justfile recipes.

### Docs site

- `just docs-gen`, `just docs-build`, `just docs-dev`; content in `wiki/`, site in `site/`. Source: CONCEPT D01.

### License and credit

- Apache-2.0 (`LICENSE`); the CLI is inspired by Cole Medin's single-bundle `okf-cli.py`. Source: README License; FACTS §Defect list i.
