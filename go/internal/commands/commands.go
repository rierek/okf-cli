// Package commands wires every command package into a cli.App. It is shared by the okf binary and
// by the docs generator (cmd/okf-docgen), so both see the same command tree.
package commands

import (
	"nas/volume1/data/git/okf-tools/go/internal/buildtagvec"
	"nas/volume1/data/git/okf-tools/go/internal/check"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/ctx"
	"nas/volume1/data/git/okf-tools/go/internal/find"
	"nas/volume1/data/git/okf-tools/go/internal/fts"
	"nas/volume1/data/git/okf-tools/go/internal/indexwrite"
	"nas/volume1/data/git/okf-tools/go/internal/info"
	"nas/volume1/data/git/okf-tools/go/internal/install"
	"nas/volume1/data/git/okf-tools/go/internal/move"
	"nas/volume1/data/git/okf-tools/go/internal/navigation"
	"nas/volume1/data/git/okf-tools/go/internal/rewrite"
	"nas/volume1/data/git/okf-tools/go/internal/semantic"
	"nas/volume1/data/git/okf-tools/go/internal/tagwrite"
	"nas/volume1/data/git/okf-tools/go/internal/wikisync"
)

// commands lists the command packages, each exporting Register(*cli.App). A directory command whose
// package is not listed answers with a "not yet ported" error. A new command package adds ONE entry
// here, the mirror of Python's COMMAND_MODULES; there is no discovery.
var commands = []func(*cli.App){
	check.Register,
	ctx.Register,
	buildtagvec.Register,
	find.Register,
	fts.Register,
	indexwrite.Register,
	info.Register,
	install.Register,
	move.Register,
	rewrite.Register,
	semantic.Register,
	navigation.Register,
	wikisync.Register,
	tagwrite.Register,
}

// Register attaches every command package to app, in the order of the list above.
func Register(app *cli.App) {
	for _, register := range commands {
		register(app)
	}
}
