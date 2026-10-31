package tui

import (
	"nas/volume1/data/git/okf-tools/go/internal/cli"
)

// Register attaches the `tui` command. The root arrives resolved by the same dispatch as every
// other command (--root, --global, walk-up, user config), so a missing root ends with the same
// message and exit code as `okf find` before the TUI starts.
func Register(app *cli.App) {
	app.Attach("tui", cli.Spec{Handler: run})
}

func run(root string, _ *cli.Args) (any, error) {
	return nil, Run(root)
}
