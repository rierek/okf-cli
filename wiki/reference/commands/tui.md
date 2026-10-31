---
title: "okf tui: terminal UI"
description: "okf tui opens a keyboard-first terminal UI on the catalogue root: search with result list and detail pane, keys, the [tui] settings and how to open it as a herdr popup."
---

# `okf tui`

`okf tui` opens a keyboard-first terminal UI on the catalogue. Look and keys follow `lif tui`. The command exists only in the Go binary; the Python CLI has no `tui`. It is hidden from `okf --help`, but `okf tui --help` and the call itself work.

:::note
This page describes the search screen, the filters, the editor, the index dots and the session buffer. The hand-off to an agent pane comes with a later release of the TUI.
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

## Filters

Below the query field a bar of six boxes narrows the search: **Root**, **Bundle**, **Type**, **Tag**, **Status** and **Tier**. You never write `--where` syntax. An empty box shows `(any)`. A box with values shows them (`<first> +N` when several), so the active filters are always on screen.

Press `f` to focus the bar, or step into it with `tab`. `tab` and `shift+tab` walk through the fields and leave the bar behind the last or before the first field; `←`/`→` do the same without leaving it. `enter` opens the menu of the focused field. `esc` leaves the bar.

### Value menus

The menus of Bundle, Type, Tag, Status and Tier are multi-select. `↑`/`↓` move the cursor, `space` or `x` select or deselect a value, `X` clears all filters, and `esc` closes the menu. A search that already ran starts again on `esc` when the choice changed, so the list always shows the chosen filters. Before the first search the choice waits and applies to it.

The menus list only values that exist in the active root:

- Bundle: the bundles `okf find` searches (the one named by `bundle` in `.okf.toml`, if set).
- Type: the types registered in the root's `TYPES.md`.
- Tag: the tags the root's concepts use.
- Status: `draft`, `stable`, `deprecated`. Tier: `unverified`, `machine-confirmed`, `human-reviewed`. These values are the same in every root.

### How the choice becomes a filter

The TUI builds a `--where` expression and compiles it with the compiler of [`--where`](/okf-cli/reference/where-filter/):

- A bundle `B` is `path ~ B/`.
- Values of one field are joined with `or`; different fields are joined with `and`.

Bundle `handbook` and type `Runbook` give the hits of `okf find <query> --where "path ~ handbook/ and type = Runbook"`. The types `Recipe` and `Runbook` give `(type = Recipe or type = Runbook)`.

`X` outside the query field clears all values of all fields at once and keeps the root.

### Root

The header and the Root box show the active root. `enter` on the Root box opens the root menu. It lists the active root, the root of `~/.config/okf/config.toml` and every root you used in earlier sessions, most recent first. Choose one with `↑`/`↓` and `enter`, or move below the list and type a path (`~` and relative paths work as for `--root`).

- The TUI runs the current query again on the new root and resets the index dots. The list of the old root is dropped.
- Filter values the new root does not hold are dropped. A message names them.
- A path that is not a directory, or holds no catalogue (`.okf.toml`, or `SPEC.md` and `TYPES.md`), is refused. The root stays, the menu stays open and a red message shows the reason.

The TUI remembers a root when it starts on it or switches to it. The list is in `tui.json` in `$XDG_STATE_HOME/okf/` (`~/.local/state/okf/` when the variable is unset), at most 20 roots. It is a state file of the TUI, outside every catalogue and outside the user config, which the TUI never writes.

## Open a hit in the editor

`e` on a focused hit opens its file in the editor and suspends the TUI. When the editor exits, the TUI comes back with the same root, query, hit list, order and focus, and reads that one hit again from disk: the detail pane shows the changed type, description, tags, snippet and headings. If the editor exits with an error, the TUI shows a red message and keeps the session. If the file is gone afterwards, the row stays and a red message says so.

The editor is the first of these that is set:

1. the `editor` key of `[tui]` in the user config;
2. `$VISUAL`;
3. `$EDITOR`;
4. `vi`.

A value may carry arguments, for example `code --wait`. The file name is appended as the last argument.

## Session buffer

The session buffer collects hits across searches and roots, so that you can carry a curated selection through the session. It lives only as long as the TUI runs.

- `space` on the focused hit adds it to the buffer; a second `space` removes it. A buffered hit carries a `◆` in the result list. The header shows the number of entries as `buffer N`.
- A file is one entry. The identity is the absolute path with symlinks resolved, so the same file found by a later search, or under another spelling of the root (a symlink, a trailing slash), shows as buffered and is never added twice.
- The buffer keeps its entries across new searches, and across a change of the root. Every entry keeps a snapshot of title, absolute path, type, bundle, tags and description, so it survives a root change. Editing a buffered hit with `e` refreshes its snapshot.
- `n` opens a text area for the note of the focused hit. A hit that is not buffered yet joins the buffer when you save a note that is not empty. `ctrl+s` saves, `esc` cancels, `ctrl+e` opens the text in the editor and puts the edited text back into the text area when the editor exits. Enter starts a new line. Saving an empty note removes the note and keeps the entry.
- `b` opens the buffer view. It lists the entries in the order they were added, each with title, type, bundle and a `✎` marker when the entry has a note. Below the list, the pane shows path, tags and note of the entry under the cursor.
- In the buffer view: `j`/`k` move, `x` removes the entry under the cursor, `n` writes its note, `c` clears the whole buffer after a red confirm dialog (`enter` or `y` clears, `esc` or `n` keeps the buffer), and `b` or `esc` goes back to the search.

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
| `e` | In the result list: open the focused hit in the editor. |
| `space` | In the result list: add the focused hit to the buffer, or remove it. |
| `n` | In the result list and in the buffer view: write the note of the focused hit or entry. |
| `b` | In the result list: open the buffer view. In the buffer view: back to the search. |
| `x`, `c` | In the buffer view: remove the entry, or clear the buffer after a confirm dialog. |
| `ctrl+s`, `ctrl+e` | In the note text area: save, or edit the text in the editor. `esc` cancels. |
| `v`, `V` | Next or previous layout: list and detail, list, detail. |
| `ctrl+d`, `ctrl+u` | Scroll the detail pane down or up. |
| `/` | Focus the query field. |
| `f` | Focus the filter bar, on its root field. Outside the query field only. |
| `←`/`h`, `→`/`l` | In the filter bar: previous or next field. |
| `enter` | In the filter bar: open the menu of the focused field. |
| `space`, `x` | In a value menu: select or deselect the value under the cursor. |
| `X` | Clear every filter but the root. Outside the query field only. |
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
