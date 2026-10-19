# okf-cli — CLI and MCP server for Open Knowledge Format (OKF) v0.2 catalogues

Search, navigate, validate and refactor a **catalogue of [Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) bundles** — markdown files with YAML frontmatter, built for humans and AI agents.

**Documentation:** <https://rierek.github.io/okf-cli/> — install, first steps, features, command reference and agent onboarding.

- **Agent-ready.** `read` returns one section, or a page together with the pages it links to, in one call; one command registers an MCP server and an agent skill with Claude Code, Codex, opencode, omp, Kimi Code, OpenClaw and Hermes; `prime` onboards a fresh agent session in one call.
- **Predictable.** Every command answers `--json` with one envelope, and every failure has an exit code that names its class.
- **Hybrid search.** Local SQLite FTS5/BM25 plus optional semantic arm (Voyage embeddings), narrowed by one `--where` filter language.
- **Safe refactoring.** `rename` and `archive` move a concept and rewrite every inbound and outbound link. Every mutating command previews a unified diff before `--apply` writes it.
- **Trust and freshness.** OKF v0.2 provenance (`generated`, `sources`, `verified`, `stale_after`) is checked by `check`, recorded by `verify` and queried by `--where`.
- **Catalogue-aware.** Works across many bundles at once, not only one.

Keywords: Open Knowledge Format, OKF v0.2, knowledge base CLI, markdown frontmatter, MCP server, Claude Code, agent memory, Obsidian, BM25, link checker, wikilinks.

## Install

```bash
brew install okf-cli
```

Release binaries and a source build: [Installation](https://rierek.github.io/okf-cli/overview/installation/). First steps, command reference and agent onboarding are on the same site.

The Python CLI of the earlier releases is still published as wheel and sdist (`pipx install git+https://github.com/rierek/okf-cli`, or `uv run --script cli/okf-cli.py` from a clone; Python 3.11 or newer). It offers the same commands; what differs is listed under [Differences from the Python CLI](#differences-from-the-python-cli).

## Demo

Ranked search over a catalogue:

![okf find: ranked results with title, type, path and snippet](assets/find.png)

Link-safe rename (dry-run) shows one unified diff per rewritten file, then the plan:

```
$ okf rename notes/ref.md notes/reference.md
--- a/_ctx/demo.md
+++ b/_ctx/demo.md
@@ -10,4 +10,4 @@
 | 1 | pflicht | [notes (draft)](/b/notes (draft).md) |  |
 | 2 | pflicht | [intro](/intro.md) |  |
 | 3 | pflicht | [design](/notes/design.md) |  |
-| - | nachschlag | [ref](/notes/ref.md) | nur bei Bedarf |
+| - | nachschlag | [reference](/notes/reference.md) | nur bei Bedarf |
rename from notes/ref.md
rename to notes/reference.md
would move   notes/ref.md  ->  notes/reference.md
  inbound    _ctx/demo.md   /notes/ref.md  ->  /notes/reference.md
  ctx        demo (reference)
  reindex    notes
rename (dry-run): 1 inbound, 0 outbound link(s), 0 wikilink(s) (0 skipped-ambiguous), 1 bundle(s), 0 sync source(s). Re-run with --apply.
```

## How it differs

| | okf | single-bundle tools |
|---|---|---|
| scope | catalogue of many bundles | one bundle |
| dependencies | declared inline (PEP 723), installed by `uv run --script` | varies |
| link-safe move/rename | yes | rarely |
| search | BM25 + semantic, local index | varies |

Catalogue-aware fork inspired by Cole Medin's single-bundle `okf-cli.py`. Related OKF projects: [open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format) (spec), [openknowledge-sh/openknowledge](https://github.com/openknowledge-sh/openknowledge), [okf-enforcer](https://github.com/MartinForReal/okf-enforcer) (Obsidian).

## Differences from the Python CLI

As of this release. The behaviour decisions below are still open for the product owner; the evidence is in [Known limitations](https://rierek.github.io/okf-cli/known-limitations/).

**Same:** the 33 commands, the 14 `ctx` verbs, their options, the `--json` envelope, the exit codes, the `--where` grammar, the output formats and the dry-run defaults. The golden suite of 314 cases runs both CLIs: the Go binary matches the Python CLI byte for byte in 293 cases; the 21 others differ only in the wording of one YAML parse error (see below). `--root` and `--global` go before the command in both CLIs (`okf --root /path find git`).

**Different:**

- **No Python.** The binary needs no Python and no `uv`; `okf find` runs with an empty `PATH`. Only the MCP server (`mcp/okf_mcp.py`) still runs through `uv`; it now calls the Go binary (`$OKF_BIN`, else the binary next to `mcp/`, else `okf` on `PATH`).
- **Speed.** Median over 30 runs, Linux amd64, Knowledge-Catalogue with a 26 MB tag-vector file: `okf --help` 1.3 ms (Python: 47 ms), `okf find git` 17 ms (Python: 146 ms); peak memory of `find` 55 MiB (Python: 212 MiB).
- **YAML parse errors read differently.** `check`, the tag verbs and `verify` name the same file under the same rule and exit with the same code, but the parser's own sentence and position differ: Python `expected ',' or ']', but got ':' (line 4, column 12)`, Go `did not find expected ',' or ']' (line 3, column 9)`.
- **Frontmatter writes keep your formatting.** The Python CLI re-serialised the frontmatter it edited; the Go binary patches only the edited lines, so comments, quoting and indentation stay and the diff is minimal.
- **Some frontmatter is refused instead of rewritten.** When the line patcher cannot patch a shape safely, the command exits 2 with `<path>: <reason>` and leaves the file untouched; the Python CLI writes such files. The shapes: a lone CR as line ending inside an LF frontmatter, a flow mapping or `null` as the frontmatter root, an anchor, alias or explicit tag on the edited value, a comment inside a multi-line flow list, and a few list layouts (null or folded item, value after the dash, complex key). One refused file ends the whole run of `merge-tags`, `remove-tags`, `normalize-tags` and `migrate` (a dry run too), and also a `ctx` edit of such a file. `verify` and `normalize-tags` stop on a frontmatter key that is not a scalar.
- **Rare YAML and TOML edge cases are validated differently.** The Python parser reads some frontmatter that Go refuses (a `\/` escape, odd anchor names, empty keys) and the other way round (impossible dates in a custom key). The report lists them as D-26 to D-30; they are open for the product owner.
- **Shell completion** is answered by the binary itself, without Python or `argcomplete`.

The same report has the full list of 77 entries, each with a reproduction line.

## Learn more

- [Google Cloud blog: How the Open Knowledge Format can improve data sharing](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) — the original announcement
- [OKF v0.2 specification](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) and [reference repository](https://github.com/GoogleCloudPlatform/open-knowledge-format)
- [okf.md](https://okf.md/) — community guide: [spec walkthrough](https://okf.md/spec/), [FAQ](https://okf.md/faq/), [tools](https://okf.md/tools/), [ecosystem map](https://okf.md/ecosystem-map/)
- [Karpathy's LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — the idea that inspired much of the ecosystem

## Development

```bash
just test     # builds the Go binary (`just go-build`, needed by the MCP boundary tests), then unittest discovery over tests/test_*.py
just golden   # golden-output comparison; --update rewrites the goldens, --cmd <binary> checks another implementation
just golden-go          # builds go/bin/okf and runs the golden suite against it (CI runs this on Linux and macOS)
just go-find-smoke      # `okf find` with a PATH that holds no python3 and no uv
just completion-check   # zsh TAB completion end to end in a PTY: Go binary against the Python CLI, throwaway HOME
just brew-local-check   # builds packaging/homebrew/okf-cli.rb from source in a throwaway local tap and runs `brew test`
just install-parity     # `okf install` of the Python CLI and the Go binary side by side in throwaway HOMEs
just build    # wheel and sdist into dist/ (uv build)
just check    # conformance scan against a real catalogue
just prime
just setup    # the okf install plan; add --apply to perform it
```

`just test` must be green before anything in `cli/`, `tests/` or `mcp/` is committed. Tests never write into a real catalogue. `just check` and `just prime` take a catalogue root as argument; their default is a personal catalogue path set at the top of the `justfile`.

The golden suite (`tests/okf_golden.py`, driven by `tests/test_golden.py` inside `just test`) runs every line of `tests/golden/cases.txt` against a fresh git copy of the fixture catalogue `tests/golden/catalogue/` and compares stdout, stderr, exit code and the changed files with `tests/golden/expected/<case>.out`. It treats the CLI as a black box, so a port of the CLI passes when `just golden --cmd <binary>` is green. Two parts are masked: an instant of the current day becomes `<NOW>`, and a usage error (stderr starting with `usage: okf`) pins only as `<usage error>` plus exit code 2, because argparse's wording changes between Python releases; a port must start such stderr with `usage: okf`. After an intended output change, run `just golden --update` and review the diff of `tests/golden/expected/`.

The Go module is `go/` (own `go.mod`, pure Go, no cgo; dependencies in `go/go.mod`). `go/cmd/okf/main.go` is the entry point and the one place that wires the commands together. The shared core lives in `go/internal/` (`okferr` exit codes, `envelope` the `--json` envelope, `catalogue`, `frontmatter`, `where` the `--where` grammar, `spec`, `linkscan`, `history`, `sqlstore`, `tagvec`, `stdio`, `complete` shell completion, `cli` the command table). Each command area owns one package there with one `Register` function, for example `find`, `check`, `ctx`, `move` (rename, archive), `indexwrite` (reindex), `tagwrite`, `wikisync`, `install` and `buildtagvec`. `yamlpatch` is the one writer of frontmatter: it patches the lines of the edited value and keeps everything else byte for byte. Run the Go unit tests with `go test ./...` in `go/`; the black-box proof is `just golden-go`. `okf install` writes the completion scripts embedded in the binary (`go/internal/complete/okf.{zsh,bash,fish}`); `just go-completion-scripts` regenerates them from the Python completion glue.

The Python CLI is still in the repository, and the golden suite runs it as the reference. `cli/okf-cli.py` is only its entry point: it carries the PEP 723 header, builds the parser, resolves the catalogue root and dispatches. The commands live in the `cli/okf/` package; tests live in `tests/`, and `tests/test_okf_cli.py` covers the entry itself. The `cli/_okf` file is the zsh completion glue of the Python CLI; it stays beside the entry payload because packaging and installer tests verify that path.

- Shared foundation: `catalogue` (root, bundles, concepts, tags, configuration), `linkscan` (link and reference scan), `parser_support` (command registration helpers), `errors` (the exit-code classes), `output` (the `--json` envelope), `diffs` (unified-diff previews), `history` (git lookups for `recent`, `migrate` and the drift rule), `spec` (trust tier and staleness).
- Commands, each module defining its `COMMANDS`: `navigation` (list, read, info, toc, visualize, refs), `prime`, `index` (index, reindex), `ctx`, `recent`, `find` (with `find_filters`, the `--where` grammar), `fts` (build-index), `semantic` (build-semantic-index), `tags`, `check` (check, fix-crosslinks, fix-xml-tags; the v0.2 rules are in `spec_check`), `verify`, `migrate`, `wikilinks`, `sync`, `rename` (rename, archive, rewrite-path) and `install`.
- `parser` merges the `COMMANDS` of every command module into the argparse parser; `entry_support` holds the BrokenPipe helper of the entry.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Spec changes go upstream to [open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format).

## License

[Apache-2.0](LICENSE)
