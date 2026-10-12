# okf-cli 0.2.0

Release 0.2.0 makes okf-cli predictable and cheap for agents and CI, and moves the CLI and the Knowledge Catalogue to OKF v0.2. It contains breaking changes: read the sections *What every caller must run* and *Breaking changes* before upgrading.

## What every caller must run

okf-cli declares its dependencies as PEP 723 metadata in `cli/okf-cli.py` (`ruamel.yaml`, `argcomplete`, Python 3.11 or newer). The CLI is started through `uv run --script`; a plain `python3` start installs nothing and works only where `ruamel.yaml` happens to be importable. The three starters change:

| starter | before | now |
|---|---|---|
| wrapper `~/.local/bin/okf-cli` | `exec python3 …/cli/okf-cli.py "$@"` | `exec uv run --script …/cli/okf-cli.py "$@"` |
| MCP subprocess in `mcp/okf_mcp.py` | `subprocess.run(["python3", OKF_CLI] + argv)` | `subprocess.run(["uv", "run", "--script", OKF_CLI] + argv)` |
| catalogue hook (`.githooks/pre-commit` of the Knowledge Catalogue) | calls `okf-cli … ctx list --for …` through `PATH` | calls `uv run --script "$OKF_CLI" … ctx list --for …`, skipped when `uv` is missing |

The MCP server registration itself (`uv run --with "mcp<2" …/mcp/okf_mcp.py`) is unchanged; `uv` must be on `PATH`.

### Deploy steps after PO approval

Until approval the live callers keep running `main` (0.1). Deploy means these steps, in this order:

1. Merge `milestone/0.2` into `main` and tag `rel-0-2-0` on the merge commit (see the hand-off list in the gate report).
2. Merge the `okf-0.2` branch of `~/dotfiles` into its main line, and the `okf-0.2` branch of `~/.claude` into its main line. Both carry the caller edits for the `--where`, `--json` and exit-code changes.
3. Switch the wrapper `~/.local/bin/okf-cli` (not in git) to `uv run --script`.
4. Apply the recorded `~/.omp` edits. `~/.omp` is not a git repository, so there is no branch; the consumer leaves record each hit with its new wording.
5. Apply the recorded Knowledge Catalogue deploy-time edits: the `justfile` normalize-tags recipe, the header of `TAGS.md`, and the `uv run --script` form of `.githooks/pre-commit`.
6. Push the Knowledge Catalogue `main` with its migration commits.

## Breaking changes

One hard cut, no shims. Each line names the owning container.

- **`--where` is the only filter** (One filter path: --where). The flags `--type`, `--tag`, `--scope` and `--include-archive` are gone from every command. Use `--where 'type = X'`, `--where 'tag = X'`, `--where 'path ~ <bundle>/'`; archived concepts are hidden unless the expression names `archived`, so `--where 'archived = true or archived = false'` covers both.
- **One `--json` envelope and exit classes** (Uniform --json envelope for every command; Exit-code classes and error class). Every command prints `{command, ok, data, warnings, error}` with `--json`; the per-command shapes are gone. Exit 1 no longer means everything: `1` internal, `2` invalid input, `3` not found, `4` non-conformant, `5` drift. The MCP server has no exit-code special list any more: it forwards `data`, `warnings` and `error`.
- **`check` rule IDs** (check: rule IDs, severity, suppression). Findings carry IDs with the prefixes `okf/` (format) and `kc/` (catalogue conventions) and a severity; `--strict` counts warnings toward the exit code but keeps each severity. `--ignore` and the `ignore_rules` list in `.okf.toml` suppress rules; a suppressed finding neither prints nor counts. Flat v0.1 rule names are gone.
- **Frontmatter `generated` replaces `timestamp`; `status` is a closed set** (OKF v0.2 checks, trust tier, staleness and verify; Migrate the catalogue to OKF v0.2). `status` is `draft`, `stable` or `deprecated`: `obsolete`, `deleted`, `archived` map to `deprecated`; `accepted`, `active`, `passive`, `stable` to `stable`; `todo`, `planned`, `in-bearbeitung`, `experimental` to `draft`. A citations heading becomes `sources`.
- **Package layout** (Split okf-cli.py into package cli/okf/). `cli/okf-cli.py` is the entry point only; the logic lives in modules under `cli/okf/`. The path of the entry script is unchanged.

## New features

Names are those of `okf-cli --help`.

- **`read --section`** prints one section of a concept (`read <concept> --section 'A > B'`); `--frontmatter-only` and `--body-only` split a page at the frontmatter.
- **`read --follow N`** prints a concept together with the pages it links to, up to `N` hops, as one block; `--inbound` adds pages that link to it, `--max-tokens K` bounds the block. The MCP tool `okf_read` takes the same options.
- **`verify <concept> --by <actor>`** records that a concept was checked against its sources.
- **Trust tier and staleness.** `tier` (`unverified`, `machine-confirmed`, `human-reviewed`) and `stale` are `--where` fields and part of the `--json` output of the concept listings; `check` reports `okf/trust/*` and `okf/lifecycle/*` findings in bundles that declare `okf_version: "0.2"`.
- **`migrate`** brings a catalogue to OKF v0.2. It previews as a unified diff by default; `--apply` writes exactly that diff.
- **Unified-diff previews.** `rename`, `archive`, `migrate`, `merge-tags`, `remove-tags`, `normalize-tags`, `sync-insert` and `sync-update` preview by default and write with `--apply`; `fix-crosslinks`, `fix-xml-tags`, `rewrite-path` and `reindex` write unless called with `--check`. Every preview shows one unified diff per affected file; with `--json` the diffs are `data.files`.
- **README** describes the 0.2 surface, command by command.
- Not part of 0.2: SARIF output for `check` and a `schema` command.
