---
title: "Contribute to okf: build from source and run the tests"
description: "Report bugs, build okf from source, run the tests, change the docs site, license and credit."
---

## Contribute to okf: report bugs, build from source, run the tests

Issues and pull requests are welcome.

## Report bugs and requests

1. Read [Known limitations](/okf-cli/known-limitations/). The problem may be listed with a workaround.
2. Open an issue in [`rierek/okf-cli`](https://github.com/rierek/okf-cli/issues). Give the command, the catalogue layout (or a minimal one) and the output.

## Build from source

The Go module is in `go/`. The binary is written to `go/bin/okf`.

```bash title="Build"
just go-build
```

## Test

Run `just test` before a pull request. It must be green. Tests never write into a real catalogue and use their own temporary directory.

| Recipe | What it runs |
|---|---|
| `just test` | builds the binary, then runs the Python unit tests (needs `uv`) |
| `just golden` | compares command output with the golden files, using the Python script |
| `just golden-go` | the same comparison against the Go binary |
| `just go-completion-scripts --check` | checks the generated completion scripts |
| `just completion-check` | checks shell completion against the Go binary |

Commit titles use `<type>(<scope>): <subject>`, at most 72 bytes.

## Docs site

Content is in `wiki/`, the site is in `site/`. The command pages are generated from the binary and are not checked in.

| Recipe | What it does |
|---|---|
| `just docs-gen` | generates the command pages |
| `just docs-build` | builds the site into `site/dist` |
| `just docs-dev` | starts the dev server |

## License and credit

okf is licensed under [Apache-2.0](https://github.com/rierek/okf-cli/blob/main/LICENSE). It is inspired by Cole Medin's single-bundle `okf-cli.py`.
