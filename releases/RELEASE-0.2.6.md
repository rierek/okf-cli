# okf-cli 0.2.6 — okf tui

Release 0.2.6 ships `okf tui`. Release page: <https://rierek.github.io/okf-cli/releases/v0-2-6/>.

## Why

`okf` serves agents well and people less so. A person must know the `--where` syntax, every search is a new call, and collecting the hits that matter for an agent is copy work. `okf tui` is a terminal UI for that research flow, entirely on the keyboard.

## Highlights

- **Search.** Type a query and the ranked hits appear next to a detail pane with metadata and the table of contents.
- **Filters.** A filter bar narrows by root, bundle, type, tag, status and tier through multi-select menus. Press `/` to search inside a menu. The TUI builds the `--where` expression for you.
- **Editor.** Open a hit in your editor and return to the same search.
- **Session buffer with notes.** Keep hits in a buffer, add a note to each and see the file preview next to it.
- **Hand-off.** `ctrl+s` sends the buffer as Markdown to a herdr agent, or to the clipboard when no agent is there. `y` copies it.
- **Maintenance tasks.** Press `t` on a hit to record a task in the tracker you configure under `[tui.tracker]`.
- **Index dots and refresh.** Two dots show the state of the lexical and the semantic index. `r` opens a dialog: `l` rebuilds the lexical index, `s` embeds the missing concepts for the semantic index.
- **Command center.** `ctrl+k` lists every action and view with a fuzzy filter, also inside the query field.
- **Themes.** The four Catppuccin themes latte, frappe, macchiato and mocha, with an optional accent colour.

`okf tui --help` documents the settings, the state file and the environment variables. See the feature page [Terminal UI: okf tui](https://rierek.github.io/okf-cli/features/tui/) for recordings of every key and the [`okf tui` reference](https://rierek.github.io/okf-cli/reference/commands/tui/) for the key map and the exact hand-off text.

Versioning: major and minor of okf-cli follow the OKF spec version (spec 0.2, so okf-cli 0.2.x). Only the patch number counts CLI releases.

## What is in this release


Keyboard-first terminal UI `okf tui`, opened as a herdr popup: search the catalogue with interactive filters, inspect hits, collect them with notes in a session buffer, hand them to the agent pane, see and refresh stale indexes, and record maintenance tasks in any configured tracker.

## Changes

- [OKFT-07x9] The buffer export puts each note under a `## Notes` heading instead of a quote line.
- [OKFT-9x7l] Error messages no longer stay on screen until `esc`; they expire like other messages.
- [OKFT-ejgy] Filter menus fit long names, search with `/` (also in tags) and select with space as well as enter.
- [OKFT-t64h] The command center on `ctrl+k` lists every action and view with a fuzzy filter; types and tags have their own views; help stays on `?`.
- [OKFT-mpfi] The documentation site has a page for `okf tui` with recordings that show every pressed key.
- [OKFT-lg82] A filter bar on the search screen: root (path input, remembered roots) plus bundle, type, tag, status and tier as multi-select menus. The TUI builds the `--where` expression; you never type it.
- [OKFT-ms7g] Exports the buffer as Markdown (header, one block per hit: title, @absolute path, type, bundle, tags, description, note). `ctrl+s` sends it without Enter to the agent under the popup, else via a picker of herdr agents, else to the clipboard; `y` copies it.
- [OKFT-qagm] Two dots on the search screen show the state of the lexical (FTS) and the semantic index: green current, yellow stale or partial, red absent, grey unknown/unavailable. A key or palette action rebuilds the stale index in the background.
- [OKFT-wjns] The query field has a rounded border, each pane shows its title on the border, and the buffer view shows the file preview of the focused entry with its note below.
- [OKFT-6vmf] `t` on a hit opens a prompt; the task (text plus hit reference) goes to the tracker configured in [tui.tracker] of the user config: kind `command` runs a user command with the task in environment variables, kind `file` appends an Obsidian-Tasks line.
- [OKFT-0kg6] `okf tui --help` lists the settings, the state file and the environment variables, and `tui` appears in `okf --help` and in `prime`.
- [OKFT-qhmz] Adds the `okf tui` command: it opens the configured root on an empty search screen and works as a herdr popup.
- [OKFT-u1b5] `e` opens the focused hit's file in the resolved editor (TUI setting, $VISUAL, $EDITOR, vi) with the terminal handed over; afterwards the session is unchanged and the hit's details reload from disk. Provides the editor helper that text inputs use for `ctrl+e`.
- [OKFT-brlv] Searches no longer show the ranking note as a message; any other search warning appears at most once per session.
- [OKFT-12lf] The query field ranks hits like `okf find` and shows them as a list with a detail pane (type, bundle, description, snippet, tags, provenance, tier, stale). Search warnings show as messages.
- [OKFT-krar] `space` adds or removes the focused hit to a session buffer, marked in the list; the buffer view lists entries in order of adding, removes single entries, clears all after confirmation; `n` attaches a free-text note to a buffered hit.

## Fixes

- [OKFT-ledw] Red tones keep their colour on 256-colour terminals, a long root path no longer wraps the header, and the root menu lists a directory once.


## Upgrade notes

1. Trust the tap: `brew trust rierek/tap`.
2. Run `brew reinstall okf-cli`. The formula now builds the Go binary from source and needs no Python.
3. Check that the new binary is the first `okf` on `PATH`: `type -a okf`. Remove an old Python launcher (a Homebrew 0.2.4 keg, a pipx or `uv tool` install).
4. Run `okf install --apply` again, so skills, the MCP entry and the completion scripts point at the new version.
5. Run `okf tui --help`: the settings epilog confirms the new binary.
