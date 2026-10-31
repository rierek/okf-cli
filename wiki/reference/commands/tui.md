---
title: "okf tui: terminal UI"
description: "okf tui opens a keyboard-first terminal UI on the catalogue root: start, keys, the [tui] settings and how to open it as a herdr popup."
---

# `okf tui`

`okf tui` opens a keyboard-first terminal UI on the catalogue. Look and keys follow `lif tui`. The command exists only in the Go binary; the Python CLI has no `tui`. It is hidden from `okf --help`, but `okf tui --help` and the call itself work.

:::note
This page describes the start screen. Search, filters, the session buffer and the hand-off to an agent pane come with later releases of the TUI.
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

## Keys

Inside the query field the letter keys type, so `q` and `?` are text there. Press `esc` to leave the field, then the global keys work.

| Key | Action |
|---|---|
| `?`, `f1` | Help overlay, generated from the key map. `f1` also works inside the query field. |
| `q` | Quit. A dialog asks first: `enter` or `y` quits, `esc` or `n` cancels. |
| `ctrl+c` | Quit at once, without a dialog, from every state. |
| `tab`, `shift+tab` | Move the focus to the next or previous part of the screen. |
| `/` | Focus the query field. |
| `esc` | Leave the query field. Outside it, dismiss a sticky message. Close an overlay. |

One overlay is open at a time and takes every key until it closes. The help overlay scrolls with `↑`/`↓`/`pgup`/`pgdn`, and `/` searches it.

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
