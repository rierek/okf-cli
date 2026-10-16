// Package indexwrite is the managed index-block writer (Python okf.catalogue, writer half, and
// okf.index.plan_reindex) and the command reindex.
package indexwrite

import "nas/volume1/data/git/okf-tools/go/internal/cli"

// Register attaches reindex.
func Register(app *cli.App) {}
