package tui

// tuiEpilog is the text after the options of `okf tui --help`: where the TUI reads its
// settings, state and environment. Raw keeps the line breaks (argparse RawDescriptionHelpFormatter).
// The key list mirrors Settings and loadTracker; the full page is the docs URL at the end.
const tuiEpilog = "settings (~/.config/okf/config.toml):\n" +
	"  [tui]\n" +
	"    editor   editor command; empty: $VISUAL, then $EDITOR, then vi\n" +
	"    theme    latte, frappe, macchiato or mocha (default: mocha)\n" +
	"    accent   #rrggbb; empty: the built-in accent\n" +
	"  [tui.tracker]  where the `t` key sends maintenance tasks\n" +
	"    kind     \"command\" or \"file\"\n" +
	"    command  kind command: shell command line, run as `sh -c`; the task\n" +
	"             arrives in OKF_TASK_TITLE, OKF_TASK_BODY, OKF_TASK_PATH,\n" +
	"             OKF_TASK_REF and OKF_TASK_ROOT (quote them in the command)\n" +
	"    file     kind file: absolute path, ~ allowed; an Obsidian Tasks line\n" +
	"             is appended\n" +
	"\n" +
	"state:\n" +
	"  $XDG_STATE_HOME/okf/tui.json (default ~/.local/state/okf/tui.json)\n" +
	"\n" +
	"environment:\n" +
	"  VOYAGE_API_KEY   marks the semantic index as usable (shown by its dot)\n" +
	"  HERDR_ACTIVE_PANE_ID, HERDR_PANE_ID\n" +
	"                   pane for the ctrl+s hand-off to an agent (herdr)\n" +
	"\n" +
	"Press ? in the TUI for the key help.\n" +
	"Docs: https://rierek.github.io/okf-cli/features/tui/\n"
