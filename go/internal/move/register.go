// Package move is the move core shared by rename, archive and ctx rename (Python okf.rename:
// perform_rename and plan_rename) and the commands rename and archive.
package move

import "nas/volume1/data/git/okf-tools/go/internal/cli"

// Register attaches rename and archive.
func Register(app *cli.App) {}
