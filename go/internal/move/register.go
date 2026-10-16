// Package move is the move core shared by rename, archive and ctx rename (Python okf.rename:
// perform_rename and plan_rename) and the commands rename and archive.
//
// PlanRename computes, without touching the disk, every reference a move oldAbs -> newAbs must
// rewrite: the markdown links pointing at the file, its own links when it changes bundle, the
// wikilinks (rewritten, skipped as ambiguous, or turned ambiguous by the move) and the `source=`
// of materialised sync blocks. PerformRename validates, plans the whole write run as text, and
// without apply previews it; with apply it moves the file (git mv, with a retry in a foreign
// repository and a filesystem fallback), writes the texts, refreshes the ctx bundles that list
// the file and the managed index files of the affected bundles, and answers with a Record.
package move

import (
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
)

const (
	applyHelp = "perform the move (default: dry-run preview only)"
	forceHelp = "overwrite an existing destination, and proceed when the new basename is already taken " +
		"and inbound wikilinks would turn ambiguous"
)

// Register attaches rename and archive with their completers.
func Register(app *cli.App) {
	app.Attach("archive", cli.Spec{
		Args: []cli.Arg{
			{Dest: "path", Help: "<bundle>/<concept>[.md]; with --restore: _archive/<bundle>/<concept>[.md]. " +
				"The other end is derived, never typed"},
			{Flags: []string{"--restore"}, Action: cli.StoreTrue,
				Help: "move the path back out of _archive/ instead of into it"},
			{Flags: []string{"--apply"}, Action: cli.StoreTrue, Help: applyHelp},
			{Flags: []string{"--force"}, Action: cli.StoreTrue, Help: forceHelp},
			cli.JSON(),
		},
		Handler: runArchive,
	})
	complete.Attach([]string{"archive"}, "path", complete.Concepts)

	app.Attach("rename", cli.Spec{
		Args: []cli.Arg{
			{Dest: "old", Help: "source concept path (<bundle>/<concept>.md, abs or --root-relative)"},
			{Dest: "new", Help: "destination path (same or different bundle)"},
			{Flags: []string{"--apply"}, Action: cli.StoreTrue, Help: applyHelp},
			{Flags: []string{"--force"}, Action: cli.StoreTrue, Help: forceHelp},
			cli.JSON(),
		},
		Handler: runRename,
	})
	complete.Attach([]string{"rename"}, "old", complete.ConceptFiles)
	complete.Attach([]string{"rename"}, "new", complete.ConceptFiles)
}
