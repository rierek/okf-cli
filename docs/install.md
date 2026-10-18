# Installing okf

`okf` is one binary written in Go. It needs no Python, no `uv` and no other runtime, and it runs on macOS and Linux (`amd64` and `arm64`). Only the MCP server of `okf install` needs `uv`. Every command and option: [command reference](https://xrieros.github.io/okf-cli/reference/commands/). Overview: [README](../README.md).

## Choose a method

| method | gives you | needs |
|---|---|---|
| [Homebrew](#homebrew-macos-and-linuxbrew) | binary, agent skill and MCP server sources in one keg | Homebrew (it installs `go`, `just` for the build and `uv`) |
| [Release binary](#release-binary) | the binary alone: commands and shell completion | `curl` |
| [From source](#from-source) | binary, skill and MCP server in the clone | Go 1.26 or newer, `just` |

The agent skill and the MCP server live in `skills/okf` and `mcp/okf_mcp.py`. `okf install` finds them next to the binary (a Homebrew keg, a clone). A release binary alone has none, so its skill and MCP steps stay BLOCKED; use Homebrew or a clone when you want them.

## Homebrew (macOS and Linuxbrew)

```bash
brew tap xRiErOS/tap
brew trust xRiErOS/tap      # Homebrew 7 refuses formulae from untrusted taps
brew install okf-cli
```

The formula builds `okf` from source with `just go-build` (`go` and `just` are build dependencies) and keeps `skills/okf` and `mcp/okf_mcp.py` in the keg. `uv` is a runtime dependency for the MCP server only. The formula in the repository is `packaging/homebrew/okf-cli.rb`; the tap copy is replaced at release time, so check the tap for the version it installs.

Upgrade with `brew upgrade okf-cli`, then run `okf install --apply` again (see [Wire okf into agents and shells](#wire-okf-into-agents-and-shells)).

## Release binary

A release carries one binary per platform: `okf-darwin-arm64`, `okf-darwin-amd64`, `okf-linux-amd64` and `okf-linux-arm64`, next to the wheel, the sdist and the provenance file `multiple.intoto.jsonl`. Replace `<tag>` with the release tag and pick your platform:

```bash
mkdir -p ~/.local/bin
curl -fsSL -o ~/.local/bin/okf https://github.com/xRiErOS/okf-cli/releases/download/<tag>/okf-darwin-arm64
chmod +x ~/.local/bin/okf
```

`~/.local/bin` must be on your `PATH`. If it is not, add `export PATH="$HOME/.local/bin:$PATH"` to your rc file.

## From source

You need Go 1.26 or newer (`go/go.mod`) and [`just`](https://github.com/casey/just). The build is pure Go, no cgo, no C compiler.

```bash
git clone https://github.com/xRiErOS/okf-cli
cd okf-cli
just go-build               # writes go/bin/okf
# the same without just:
CGO_ENABLED=0 go build -C go -trimpath -buildvcs=false -o bin/okf ./cmd/okf
```

Run it in place (`go/bin/okf`) or let `okf install` put a wrapper `~/.local/bin/okf` that runs it (see below). `git pull` and `just go-build` update it.

## Verify

`okf --version` does not exist. Use these:

```bash
command -v okf              # the path you expect?
file "$(command -v okf)"    # a compiled executable (Mach-O on macOS, ELF on Linux), not a script
okf --help                  # starts with `usage: okf [-h] [--root ROOT] [--global]`
okf install --only zsh      # prints a plan, changes nothing
```

Then point it at a catalogue and run a command that reads it:

```bash
okf --root /path/to/catalogue info      # prints TYPES.md and PROPERTIES.md
okf --root /path/to/catalogue check     # conformance scan
```

`--root` goes **before** the command. Without `--root`, `okf` takes the nearest catalogue above the current directory (a directory with `.okf.toml`, or `SPEC.md` plus `TYPES.md`), else `root` from `~/.config/okf/config.toml` (`$XDG_CONFIG_HOME/okf/config.toml`):

```toml
root = "~/path/to/catalogue"
```

Without a catalogue, `okf` exits 3. The message is `ERROR: root not found: <path> (pass --root <path>)` after a bad `--root`; `--global` without a configured root prints ``ERROR: --global needs a `root` in <config file>``.

## Wire okf into agents and shells

```bash
okf install                 # prints the plan, changes nothing
okf install --apply         # performs it
okf install --only claude,zsh --apply     # a subset: claude omp codex opencode kimi openclaw hermes zsh bash fish
okf install --uninstall --apply            # removes what install created
```

`install` needs no catalogue. It registers, for every agent and shell it finds on this machine:

- **Skill.** `skills/okf` for Claude Code, Codex, opencode, omp, Kimi Code, OpenClaw and Hermes.
- **MCP server.** `uv run --with "mcp<2" <install dir>/mcp/okf_mcp.py` in each agent's config. `uv` must be on `PATH`; otherwise this step is BLOCKED and the plan says how to fix it. The server calls the binary with `--json`. It takes the binary from `$OKF_BIN`, else `bin/okf` or `go/bin/okf` beside `mcp/`, else `okf` on `PATH`.
- **Shell completion and PATH.** The completion scripts are embedded in the binary; the binary answers the TAB requests itself.

| shell | completion file | rc change |
|---|---|---|
| zsh | `~/.zsh/completions/_okf` | block in `${ZDOTDIR:-~}/.zshrc`: `fpath` and `compinit`, only where missing |
| bash | `~/.local/share/bash-completion/completions/okf` | block in `~/.bashrc`; on macOS the first of `~/.bash_profile`, `~/.bash_login`, `~/.profile` that exists, else `~/.bash_profile` |
| fish | `~/.config/fish/completions/okf.fish` | `~/.config/fish/conf.d/okf.fish` |

In a clone, `install` also creates `~/.local/bin/okf`, a wrapper that runs `go/bin/okf`, and puts `~/.local/bin` on `PATH` in the rc block. It skips this when an `okf` is already on `PATH`. Open a new shell and restart your agents afterwards. More about what `install` edits, backups (`<file>.okf-cli.bak`) and the supported agents: [README, agents and shells](../README.md#use-with-ai-agents-and-shells).

A binary that lives alone (release binary) can install completion only: `okf install --only zsh --apply`. A real plan, run with such a binary in `/usr/local/bin`:

```text
okf install - PLAN only, nothing is changed (add --apply to perform it)
source: /usr/local/bin (installed package, skills are copied)

skills
  BLOCKED   claude          source not found: /usr/local/bin/skills/okf

mcp
  BLOCKED   claude          uv is not on PATH; install it (https://docs.astral.sh/uv/), then re-run

shell
  skip      PATH            okf is already on PATH: /usr/local/bin/okf
  create    zsh completion  ~/.zsh/completions/_okf
  create    zsh rc          ~/.zshrc (managed block)
```

The exit code is 1 while a step is BLOCKED.

## Update and uninstall

- **Update.** Homebrew: `brew upgrade okf-cli`. Release binary: download the new asset over the old file. Clone: `git pull && just go-build`. Afterwards run `okf install --apply` again: copied skills and the embedded completion scripts are refreshed only then.
- **Uninstall.** `okf install --uninstall --apply` first (it removes what `install` created and keeps the `<file>.okf-cli.bak` backups), then remove the binary: `brew uninstall okf-cli`, or delete the file.

## Troubleshooting

**`command not found: okf`.** The directory of the binary is not on `PATH`. For `~/.local/bin`: `export PATH="$HOME/.local/bin:$PATH"` in your rc file, then open a new shell.

**`okf` runs, but it is the old Python CLI.** An earlier install is first on `PATH`: the Homebrew formula of release 0.2.4 (a Python script), a pipx or `uv tool` install, or a wrapper `~/.local/bin/okf` that runs `uv run --script …/cli/okf-cli.py`. List all of them in `PATH` order and check each:

```bash
type -a okf                      # zsh: `whence -a okf`
file "$(command -v okf)"         # "Python script text" or a shell script = the old CLI
```

Remove the stale one (`brew upgrade okf-cli`, `pipx uninstall okf-cli`, `uv tool uninstall okf-cli`, or delete the wrapper file), or put the directory of the Go binary first on `PATH`. While an `okf` is on `PATH`, `okf install` does not create its own wrapper `~/.local/bin/okf`. The Python CLI also starts slower: about 47 ms for `okf --help` against 1.3 ms (median, Linux amd64).

**TAB completion does not work.**

1. Run `okf install --only zsh` (or `bash`, `fish`) and read the plan: `unchanged` means the file and the rc block are in place, `create` means they are missing (run `okf install --apply`).
2. Check that the file exists: `ls ~/.zsh/completions/_okf`, and that `~/.zshrc` holds the block between `# >>> okf-cli >>>` and `# <<< okf-cli <<<`. The block adds `~/.zsh/completions` to `fpath` and calls `compinit`.
3. Open a new shell (`exec zsh`). To test without a new shell, run `autoload -Uz compinit && compinit` once.
4. An alias must begin with the word `okf`, resolved through `PATH`: `alias okf='okf --root ~/kc'` works; an alias that starts with an absolute path does not trigger the completion.
5. After a binary upgrade, run `okf install --apply`: the completion scripts are copies.

**`BLOCKED  <agent>  source not found: …/skills/okf`.** The binary has no `skills/okf` and `mcp/okf_mcp.py` next to it, as with a lone release binary. Install with Homebrew, or from a clone and run `go/bin/okf install`.

**`BLOCKED  <agent>  uv is not on PATH`.** Install [`uv`](https://docs.astral.sh/uv/) and run `okf install --apply` again. The CLI itself does not need it.

**The MCP server starts the wrong binary or none.** Set `OKF_BIN` to the binary in the environment the agent starts the server in (the MCP entry can carry an `env` block), or put the binary on the `PATH` of that agent.

**`find` prints `note: lexical index absent — falling back to substring scan`.** Run `okf build-index` once; run it again after the catalogue changes (`okf build-index --if-stale` skips the work when nothing changed). `note: semantic arm skipped …` is normal without `VOYAGE_API_KEY`: the lexical results are complete.

**`usage: okf …` and exit 2 for `okf find git --root …`.** `--root` and `--global` go before the command: `okf --root /path find git`.

**A tag or `migrate` command exits 2 with `<path>: <reason>`.** The line patcher of the frontmatter writer refused a file it could not patch safely, and wrote nothing. Edit that file by hand or repair its frontmatter, then run the command again. Which shapes it refuses: [README, Differences](../README.md#differences-from-the-python-cli).
