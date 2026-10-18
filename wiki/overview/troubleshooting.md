---
title: "okf troubleshooting: command not found, completion, MCP server"
description: "Fix okf command not found, TAB completion not working, MCP server errors and a missing search index."
---

## How to read this page

Each entry has the symptom as heading, then the cause and the fix. Pick the heading that matches what you see. Short IDs such as [fs8c] point to [Known limitations](/okf-cli/known-limitations/).

## `command not found: okf` and the old Python CLI first on PATH

**Cause.** The directory of the binary is not on `PATH`. Or `okf` runs, but an earlier install is first on `PATH`: a Python script from an older Homebrew formula, a `pipx` or `uv tool` install, or a wrapper `~/.local/bin/okf`.

**Fix.** List every `okf` in `PATH` order and check each:

```bash title="Terminal"
type -a okf                 # zsh: whence -a okf
file "$(command -v okf)"    # "Python script text" or a shell script = the old CLI
```

Remove the stale launcher (`brew upgrade okf-cli`, `pipx uninstall okf-cli`, `uv tool uninstall okf-cli`, or delete the wrapper file). Or put the directory of the Go binary first on `PATH`. For `~/.local/bin`, add `export PATH="$HOME/.local/bin:$PATH"` to your rc file and open a new shell. While an `okf` is on `PATH`, `okf install` does not create its own wrapper.

## TAB completion does not work

**Fix.** Go in this order:

1. Run `okf install --only zsh` (or `bash`, `fish`) and read the plan. `create` means the file or the rc block is missing: run `okf install --apply`.
2. Check the file: `ls ~/.zsh/completions/_okf`. Check that `~/.zshrc` holds the block between `# >>> okf-cli >>>` and `# <<< okf-cli <<<`.
3. Open a new shell (`exec zsh`).
4. An alias must start with the word `okf`, resolved through `PATH`. `alias okf='okf --root ~/kc'` works. An alias that starts with an absolute path does not trigger completion.
5. After a binary upgrade, run `okf install --apply`: the completion scripts are copies.

:::note
The installed zsh script has a comment that names argcomplete and `okf-cli.py`. The comment is stale. The Go binary answers completion requests itself, and completion works [jh7t].
:::

## `BLOCKED <agent> source not found` and `uv is not on PATH`

**`source not found: …/skills/okf`.** The binary has no `skills/okf` and `mcp/okf_mcp.py` next to it, as with a lone release binary. Install with Homebrew, or from a clone and run `go/bin/okf install`.

**`uv is not on PATH`.** The MCP server runs through `uv`. Install [`uv`](https://docs.astral.sh/uv/), then run `okf install --apply` again. The CLI itself does not need it.

A blocked plan exits 1 and prints only `install failed with exit code 1` [fs8c]. Read the plan above that line, or run `okf install --json` and look for `steps[].status` = `BLOCKED`.

## The MCP server starts the wrong binary or none

The server picks the binary in this order: `$OKF_BIN`, `<package>/bin/okf`, `<package>/go/bin/okf`, then `okf` on `PATH`. Set `OKF_BIN` to the binary you want, in the environment where the agent starts the server (the MCP entry can carry an `env` block). Or put the binary on the `PATH` of that agent. See [Configuration](/okf-cli/reference/configuration/).

## `find` prints `note: lexical index absent`

```text title="okf --root kc find git (okf 0.2.4, no index built)"
note: lexical index absent — falling back to substring scan; run `okf build-index` for BM25 ranking
note: semantic arm skipped (.tagvec cache/concept embeddings absent) — lexical results only
(no matches for: git)
```

**Fix.** Run `okf build-index` once. Run it again after the catalogue changes. `note: semantic arm skipped` is normal without an embedding setup: the lexical results are complete. See [Search](/okf-cli/features/search/).

## `usage: okf ...` and exit 2 for `okf find git --root ...`

`--root` and `--global` go before the command. This fails with `okf: error: unrecognized arguments: --root x` and exit 2:

```bash title="Terminal"
okf find git --root /path     # wrong
okf --root /path find git     # right
```

## A tag or `migrate` command exits 2 with `<path>: <reason>`

The line patcher of the frontmatter writer refused a file it cannot patch safely. It wrote nothing, also in a dry run. Edit the file by hand or repair its frontmatter, then run the command again. See [Safe edits](/okf-cli/features/safe-edits/) and [Known limitations](/okf-cli/known-limitations/).

## A tag registration warns about `build_tagvec.py`

The warning names a script the Go binary does not ship [erpf]. Ignore it, or run `okf build-tagvec --produce`.
