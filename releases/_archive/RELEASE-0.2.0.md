# okf-cli 0.2.0

Release 0.2.0 makes okf predictable and cheap for agents and CI, and moves the CLI and the Knowledge Catalogue to OKF v0.2. It contains breaking changes: read the sections *What every caller must run* and *Breaking changes* before upgrading.

## What every caller must run

okf declares its dependencies as PEP 723 metadata in `cli/okf-cli.py` (`ruamel.yaml`, `argcomplete`, Python 3.11 or newer). The CLI is started through `uv run --script`; a plain `python3` start installs nothing and works only where `ruamel.yaml` happens to be importable. The three starters change:

| starter | before | now |
|---|---|---|
| wrapper `~/.local/bin/okf` (was `~/.local/bin/okf-cli`) | `exec python3 …/cli/okf-cli.py "$@"` | `exec uv run --script …/cli/okf-cli.py "$@"` |
| MCP subprocess in `mcp/okf_mcp.py` | `subprocess.run(["python3", OKF_CLI] + argv)` | `subprocess.run(["uv", "run", "--script", OKF_CLI] + argv)` |
| catalogue hook (`.githooks/pre-commit` of the Knowledge Catalogue) | calls `okf-cli … ctx list --for …` through `PATH` | calls `uv run --script "$OKF_CLI" …` for the ctx warning and the index gate; skipped with a warning when `uv` or `$OKF_CLI` is missing |

The MCP server registration itself (`uv run --with "mcp<2" …/mcp/okf_mcp.py`) is unchanged; `uv` must be on `PATH`.

### Deploy steps after PO approval

Until approval the live callers keep running `main` (0.1). Deploy means these steps, in this order:

1. In `repo/` on `main`: `git merge --no-ff milestone/0.2`, check `git diff --quiet milestone/0.2 HEAD`, run `just test`, then `git push origin main`.
2. Tag the merge commit: `git tag -a rel-0-2-0 -m "okf-cli 0.2.0" && git push origin rel-0-2-0`, then watch the run: `gh run watch -R xRiErOS/okf-cli $(gh run list -R xRiErOS/okf-cli -w release.yml -L 1 --json databaseId -q '.[0].databaseId')`.
3. `~/dotfiles`: check `git status --short` is empty, merge `main` into `okf-0.2`, re-run `just test-arch test-start test-end test-smoke`, then on `main` run `git merge --no-ff okf-0.2`, `stow -R -d ~/dotfiles -t ~ okf` and `git push origin main`; then `git worktree remove /tmp/okft-cnjd-dotfiles && git branch -d okf-0.2`.
4. `~/.claude`: commit pending edits of `git status --short`, merge `main` into `okf-0.2`, then on `main` run `git merge --no-ff okf-0.2`.
5. Replace the wrapper and the completion link: write `~/.local/bin/okf` with `exec uv run --script "$HOME/dev/cli/OKF_cli/repo/cli/okf-cli.py" "$@"` (mode 755), run `rm ~/.local/bin/okf-cli ~/.zsh/completions/_okf-cli`, `ln -s ~/dev/cli/OKF_cli/repo/cli/_okf ~/.zsh/completions/_okf` and `rm -f ~/.zcompdump*`.
6. In `~/.claude`: `just arch-snapshot && just arch-check && just aca tpic check --render`, commit the snapshot and `TPIC-CHAIN.md`, then `git push origin main && git worktree remove /tmp/okft-cnjd-claude && git branch -d okf-0.2`.
7. Apply the recorded `~/.omp` edits (managed skills, `agents/skill-reviewer.md`, memory notes). `~/.omp` is not a git repository, so there is no branch.
8. Apply the recorded Knowledge Catalogue edits: the `uv run --script` form of `.githooks/pre-commit`, the `justfile` recipes (`okf`, normalize-tags with `--where`), the header of `TAGS.md` and the concept texts.
9. Commit the Knowledge Catalogue and push `main` to `nas` and `github`; this also pushes its migration commits.
10. Edit the project hulls that name `okf-cli` in `CLAUDE.md`, `SSTD.md` or `docs/CLAUDE.md`.

Other hosts: remove `~/.local/bin/okf-cli` and `~/.zsh/completions/_okf-cli`; the Arch bootstrap writes `~/.local/bin/okf`.

## GitHub release workflow

The tag `rel-0-2-0` ran `release.yml` while `xRiErOS/okf-cli` was private. The provenance job stopped at the generator's privacy check, and its upload step still published an empty GitHub release. That release is immutable and stays without files. The wheel, the sdist and the provenance of 0.2.0 exist as artifacts of the run `38218110005`; `slsa-verifier` verified both files against `multiple.intoto.jsonl` (`--source-tag rel-0-2-0`). The first GitHub release with all files is 0.2.1 (`releases/RELEASE-0.2.1.md`).

## Breaking changes

One hard cut, no shims. Each line names the owning container.

- **Command `okf` replaces `okf-cli`** (Command okf replaces okf-cli; skills use-okf). The console script, the wrapper `~/.local/bin/okf`, `--help` (`usage: okf`), the zsh completion `_okf` (`compdef _okf okf`) and the bash and fish completion files `okf` and `okf.fish` carry the new name; `okf-cli` is gone. The distribution and the repository keep the name `okf-cli`; the entry script stays `cli/okf-cli.py`. An install made by `okf-cli install` before 0.2: run `okf-cli install --uninstall --apply` with the old version, upgrade, then run `okf install --apply`. The agent skills `use-okf-cli` and `use-okf-cli-in-projects` are now `use-okf` and `use-okf-in-projects`.
- **`--where` is the only filter** (One filter path: --where). The flags `--type`, `--tag`, `--scope` and `--include-archive` are gone from every command. Use `--where 'type = X'`, `--where 'tag = X'`, `--where 'path ~ <bundle>/'` (`~` is a substring match: choose a value that occurs in no other path); archived concepts are hidden unless the expression names `archived`, so `--where 'archived = true or archived = false'` covers both.
- **One `--json` envelope and exit classes** (Uniform --json envelope for every command; Exit-code classes and error class). Every command prints `{command, ok, data, warnings, error}` with `--json`; the per-command shapes are gone. Exit 1 no longer means everything: `1` internal, `2` invalid input, `3` not found, `4` non-conformant, `5` drift. The MCP server has no exit-code special list any more: it forwards `data`, `warnings` and `error`.
- **`check` rule IDs** (check: rule IDs, severity, suppression). Findings carry IDs with the prefixes `okf/` (format) and `kc/` (catalogue conventions) and a severity; `--strict` counts warnings toward the exit code but keeps each severity. `--ignore` and the `ignore_rules` list in `.okf.toml` suppress rules; a suppressed finding neither prints nor counts. Flat v0.1 rule names are gone.
- **Frontmatter `generated` replaces `timestamp`; `status` is a closed set** (OKF v0.2 checks, trust tier, staleness and verify; Migrate the catalogue to OKF v0.2). `status` is `draft`, `stable` or `deprecated`: `obsolete`, `deleted`, `archived` map to `deprecated`; `accepted`, `active`, `passive`, `stable` to `stable`; `todo`, `planned`, `in-bearbeitung`, `experimental` to `draft`. A citations heading becomes `sources`.
- **Package layout** (Split okf-cli.py into package cli/okf/). `cli/okf-cli.py` is the entry point only; the logic lives in modules under `cli/okf/`. The path of the entry script is unchanged.

## New features

Names are those of `okf --help`.

- **Global catalogue root** (Global catalogue root from user config). Without `--root`, `okf` takes the nearest catalogue above the current directory (`.okf.toml`, or `SPEC.md` plus `TYPES.md`, also in a `docs/` child), else `root` from `$XDG_CONFIG_HOME/okf/config.toml` (default `~/.config/okf/config.toml`), e.g. `root = "~/Obsidian/Knowledge-Catalogue"`.
- **`read --section`** prints one section of a concept (`read <concept> --section 'A > B'`); `--frontmatter-only` and `--body-only` split a page at the frontmatter.
- **`read --follow N`** prints a concept together with the pages it links to, up to `N` hops, as one block; `--inbound` adds pages that link to it, `--max-tokens K` bounds the block. The MCP tool `okf_read` takes the same options.
- **`verify <concept> --by <actor>`** records that a concept was checked against its sources.
- **Trust tier and staleness.** `tier` (`unverified`, `machine-confirmed`, `human-reviewed`) and `stale` are `--where` fields and part of the `--json` output of the concept listings; `check` reports `okf/trust/*` and `okf/lifecycle/*` findings in bundles that declare `okf_version: "0.2"`.
- **`migrate`** brings a catalogue to OKF v0.2. It previews as a unified diff by default; `--apply` writes exactly that diff.
- **Unified-diff previews.** `rename`, `archive`, `migrate`, `merge-tags`, `remove-tags`, `normalize-tags`, `sync-insert` and `sync-update` preview by default and write with `--apply`; `fix-crosslinks`, `fix-xml-tags`, `rewrite-path` and `reindex` write unless called with `--check`. Every preview shows one unified diff per affected file; with `--json` the diffs are `data.files`.
- **README** describes the 0.2 surface, command by command.
- Not part of 0.2: SARIF output for `check` and a `schema` command.
