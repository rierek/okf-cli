# okf-cli 0.2.5 — the Go binary

Release 0.2.5 ships the Go port of `okf`. The documentation site is at <https://rierek.github.io/okf-cli/>.

## Why

`okf` started in Python and needed `uv` and a Python interpreter at every start: about 47 ms for `okf --help` and 146 ms for `okf find` (median, Linux amd64). This release replaces the CLI with one Go binary. The commands, options, output formats, `--json` envelope and exit codes stay.

## What changed

- **New: the `okf` binary.** One static executable, pure Go, no Python and no `uv`. Release assets: `okf-darwin-arm64`, `okf-darwin-amd64`, `okf-linux-amd64`, `okf-linux-arm64`, next to the wheel, the sdist and the provenance file. Homebrew builds it from source.
- **Faster.** Median of 30 runs on Linux amd64, Knowledge-Catalogue with a 26 MB tag-vector file, lexical index built: `okf --help` 1.3 ms against 47 ms (about 35 times), `okf find git` 17 ms against 146 ms (about 9 times). Peak memory of `find`: 55 MiB against 212 MiB. `okf find` also runs with a `PATH` that holds no `python` and no `uv`.
- **Same commands.** All 33 commands, the 14 `ctx` verbs and `--json` behave as before. The golden suite of 314 cases matches the Python CLI byte for byte in 293 cases; the other 21 differ only in the wording of a YAML parse error.
- **Shell completion** for zsh, bash and fish is answered by the binary. `okf install` writes the scripts embedded in it.
- **MCP server** (`mcp/okf_mcp.py`, still run through `uv`) now calls the binary: `$OKF_BIN`, else `bin/okf` or `go/bin/okf` next to `mcp/`, else `okf` on `PATH`.
- **New hidden command `okf build-tagvec`.** The tag-vector producer, formerly a Python script, is a command now (dry run unless `--produce`).
- **Frontmatter edits keep your formatting.** The Python CLI re-serialised the frontmatter; the binary patches only the edited lines.
- Docs: [Installation](https://rierek.github.io/okf-cli/overview/installation/) (per platform, troubleshooting), [command reference](https://rierek.github.io/okf-cli/reference/commands/) (one page per command and verb), README sections Install and Differences from the Python CLI.

The Python CLI is still published (wheel, sdist, `uv run --script cli/okf-cli.py`).

## Known limitations

Deviations from the Python CLI and other open findings are listed with a short ID on the [Known limitations](https://rierek.github.io/okf-cli/known-limitations/) page, for example `[cwyx]` (frontmatter shapes the writer refuses) and `[n760]` (one refused file ends a whole run).

## Upgrade steps

1. Install the new binary: `brew upgrade okf-cli`, or download `okf-<os>-<arch>` from the release (see [Installation](https://rierek.github.io/okf-cli/overview/installation/)).
2. Make sure the new binary is the first `okf` on `PATH`: `type -a okf` and `file "$(command -v okf)"`. Remove an old Python launcher (a Homebrew 0.2.x keg, a pipx or `uv tool` install, a wrapper `~/.local/bin/okf` that runs `uv run --script …`).
3. Run `okf install --apply` again, so skills, the MCP entry and the completion scripts point at the new version. A release binary on its own installs completion only; use Homebrew or a clone for the skill and the MCP server.
4. Restart your agent sessions.
5. Existing indexes (`.fts/fts.sqlite`, `.tagvec/tag_vectors.sqlite`) built by the Python CLI keep working; no rebuild is needed.
