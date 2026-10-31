---
title: "okf tui: terminal UI"
description: "okf tui opens a keyboard-first terminal UI on the catalogue root: search with result list and detail pane, keys, the [tui] settings and how to open it as a herdr popup."
---

# `okf tui`

`okf tui` opens a keyboard-first terminal UI on the catalogue. Look and keys follow `lif tui`. The command exists only in the Go binary; the Python CLI has no `tui`. It is hidden from `okf --help`, but `okf tui --help` and the call itself work.

:::note
This page describes the search screen. Filters, the session buffer and the hand-off to an agent pane come with later releases of the TUI.
:::

## Start

```text
okf [--root ROOT | --global] tui
```

`okf tui` takes the catalogue root exactly as `okf find` does, see [Configuration](/okf-cli/reference/configuration/): `--root`, then `--global`, then the nearest catalogue above the current directory, then `root` of `~/.config/okf/config.toml`.

- `okf tui` without `--root` opens the root `okf find` would use from the same directory.
- `okf --root <dir> tui` opens `<dir>`.
- With no root at all, `okf tui` prints the message of `okf find` and exits with code 3. The TUI does not start.

The TUI starts on the search screen. The header shows the active root. The query field has the focus.

## Search

Type a query and press `enter`. The search runs only on `enter`, never while you type. It is `okf find <query> --limit 50` on the active root, run in the same process: the list shows the same hits in the same order, at most 50, and scrolls. The semantic arm and its embedding call run as for `okf find`.

- The search runs in the background. The TUI keeps reacting to keys and shows a spinner and `searching` at the right end of the query row until the answer arrives.
- After `enter` the focus moves to the result list. Press `/` to edit the query again and `enter` to search again. A new search replaces the list. The answer of an older search never replaces a newer one.
- The warnings `okf find` prints as `note:` lines on stderr (an absent or stale index, a skipped semantic arm) show as a toast.
- A search without a hit says `No hits for "<query>".` in the list area.

The result list shows title, type and bundle of every hit. The detail pane at the right shows the focused hit:

- type, bundle, tags (from the frontmatter), provenance (`lexical` or `semantic`), trust tier and stale flag;
- the absolute path `<root>/<path>.md`, which identifies the hit;
- description and snippet;
- the table of contents: the H2 and H3 headings in document order, the headings of `okf toc <path> --level 0` at levels 2 and 3.

`v` cycles the body between list and detail side by side, the list alone and the detail alone; `V` cycles back. `ctrl+d` and `ctrl+u` scroll a detail pane that is taller than the screen.

## Keys

Inside the query field the letter keys type, so `q` and `?` are text there; the header names `f1` for the help. Press `esc` to leave the field, then the global keys work.

| Key | Action |
|---|---|
| `?`, `f1` | Help overlay, generated from the key map. `f1` also works inside the query field. |
| `q` | Quit. A dialog asks first: `enter` or `y` quits, `esc` or `n` cancels. |
| `ctrl+c` | Quit at once, without a dialog, from every state. |
| `tab`, `shift+tab` | Move the focus to the next or previous part of the screen. |
| `enter` | In the query field: search. |
| `j`, `k`, `↓`, `↑` | In the result list: focus the next or previous hit. |
| `g`, `G` | In the result list: first or last hit. |
| `v`, `V` | Next or previous layout: list and detail, list, detail. |
| `ctrl+d`, `ctrl+u` | Scroll the detail pane down or up. |
| `/` | Focus the query field. |
| `r` | Refresh an index: a dialog offers the lexical or the semantic index. Outside the query field only. |
| `esc` | Leave the query field. Outside it, dismiss a sticky message. Close an overlay. |

One overlay is open at a time and takes every key until it closes. The help overlay scrolls with `↑`/`↓`/`pgup`/`pgdn`, and `/` searches it.

## Index dots and refresh

The right part of the header shows two labelled dots, one for the lexical (FTS) index and one for the semantic index. The TUI checks both in the background when it starts and when the root changes; the dots appear within moments and never block input.

| Dot | Lexical index | Semantic index |
|---|---|---|
| green | current | every concept embedded |
| yellow | stale: the catalogue changed since the build | partial: some concepts have no current embedding |
| red | absent | absent |
| grey | not checked yet | unavailable: `VOYAGE_API_KEY` is not set |

A half-filled dot (`◐`) means a check or a refresh of that index is running; it keeps its colour until the result is in. The dots are half filled from the start until the first check returns. Choosing a refresh while the check or another refresh of the same index is running starts nothing and shows a message; press `r` again when the dot is full.

Press `r` outside the query field and choose:

- `l` rebuilds the lexical index at once, as `okf build-index` does. A new index keeps the choice of the current one (with or without topics).
- `s` embeds the concepts without a current embedding, as `okf build-semantic-index` does. A dialog names the number of concepts first and sends nothing to Voyage AI until you confirm with `enter` or `y`. Without `VOYAGE_API_KEY` the choice shows a message that names the key and nothing runs.

Both refreshes run in the background. A message reports the end and the dot is checked again, so it turns green on success. If a refresh fails, the dot keeps its colour and a red message shows the error; `esc` outside the query field dismisses it.

## Settings: `[tui]`

The TUI reads the `[tui]` table of `~/.config/okf/config.toml`, the same file as `root`:

```toml title="~/.config/okf/config.toml"
[tui]
editor = "nvim"     # editor command; empty: $VISUAL, then $EDITOR, then vi
theme  = "mocha"    # latte, frappe, macchiato or mocha (default mocha)
accent = "#cba6f7"  # #rrggbb for cursor and header; empty: the theme's accent
```

An invalid section does not stop the TUI. The TUI starts with the default settings and shows a red message that names the config file and the reason, for example an unknown theme, an accent that is not `#rrggbb`, or a value of the wrong type. Press `esc` outside the query field to dismiss it. A popup closes when the program exits, so an error on stderr would vanish before you read it; this is why the message is part of the screen.

## herdr popup

herdr runs a command in a popup over the focused pane. Add an entry to `~/.config/herdr/config.toml`:

```toml title="~/.config/herdr/config.toml"
# okf tui for the catalogue above the focused pane's cwd
[[keys.command]]
key = "prefix+shift+o"
type = "popup"
description = "okf tui"
width = "100%"
height = "100%"
command = """
cd "${HERDR_ACTIVE_PANE_CWD:-$HOME}" || exit
okf tui || { echo "okf tui exited with $?"; read -r _; }
"""
```

The popup starts in the directory of the focused pane, so `okf tui` finds the catalogue above it, or the `root` of the user config. Pick any free key. Without a root `okf tui` prints its message and exits with code 3; the last line of the command keeps the popup open until you press enter, so you can read the message.
