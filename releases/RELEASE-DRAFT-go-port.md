# okf-cli <version> — the Go binary (DRAFT)

Draft of the release note for the release that ships the Go port of `okf`. The version number is the product owner's decision. Rename this file to `releases/RELEASE-<version>.md` when it is known: `.github/workflows/release.yml` reads `releases/RELEASE-$VERSION.md`. Nothing here is tagged or published.

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
- Docs: [docs/install.md](../docs/install.md) (per platform, troubleshooting), [command reference](https://rierek.github.io/okf-cli/reference/commands/) (one page per command and verb), README sections Install and Differences from the Python CLI.

The Python CLI is still published (wheel, sdist, `uv run --script cli/okf-cli.py`).

## Known deviations from the Python CLI

As of this release; the product owner has not yet decided them. Evidence: `docs/topics/okf-go-port/ACCEPTANCE-REPORT.md`.

- A YAML parse error is worded and located by the Go parser: `did not find expected ',' or ']' (line 3, column 9)` where Python said `expected ',' or ']', but got ':' (line 4, column 12)`. Same file, same rule, same exit code.
- A frontmatter shape the line patcher cannot patch is refused, not rewritten: exit 2 with `<path>: <reason>`, file untouched. Shapes: a lone CR as line ending, a flow-mapping or `null` root, an anchor, alias or explicit tag on the edited value, a comment inside a multi-line flow list, a few list layouts. One refused file ends the whole run of `merge-tags`, `remove-tags`, `normalize-tags` and `migrate`, a dry run too.
- Rare YAML and TOML edge cases are validated differently (D-26 to D-30 of the report), and `recent` prints UTC where `TZ` is a POSIX rule string (D-52).

## Upgrade steps

1. Install the new binary: `brew upgrade okf-cli`, or download `okf-<os>-<arch>` from the release (see [docs/install.md](../docs/install.md)).
2. Make sure the new binary is the first `okf` on `PATH`: `type -a okf` and `file "$(command -v okf)"`. Remove an old Python launcher (a Homebrew 0.2.x keg, a pipx or `uv tool` install, a wrapper `~/.local/bin/okf` that runs `uv run --script …`).
3. Run `okf install --apply` again, so skills, the MCP entry and the completion scripts point at the new version. A release binary on its own installs completion only; use Homebrew or a clone for the skill and the MCP server.
4. Restart your agent sessions.
5. Existing indexes (`.fts/fts.sqlite`, `.tagvec/tag_vectors.sqlite`) built by the Python CLI keep working; no rebuild is needed.

## Deploy steps after PO approval

1. In `repo/` on `main`: merge the integration line `--no-ff`, check the diff against the line, run `just test` and `just golden-go`, then `git push origin main`.
2. Tag the merge commit `rel-<x-y-z>` and push the tag. The release workflow builds the four binaries, the wheel and the sdist and attaches the provenance; verify the provenance with `slsa-verifier`.
3. In `packaging/homebrew/okf-cli.rb` add `url`, `version` and `sha256` of that tag, then copy the formula to the tap (`xRiErOS/homebrew-tap`, `Formula/okf-cli.rb`). Check it first with `just brew-local-check`.
