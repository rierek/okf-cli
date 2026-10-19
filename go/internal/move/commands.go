package move

import (
	"strings"
	"syscall"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
)

// runRename is Python cmd_rename: the paths resolved against the root, the guard on a source under
// `_archive/`, then the move core.
func runRename(root string, a *cli.Args) (any, error) {
	oldAbs := pyAbspath(catalogue.Join(root, a.String("old")))
	newAbs := pyAbspath(catalogue.Join(root, a.String("new")))

	// A rename whose source lies under _archive/ reproduces, through this command, the invisible
	// empty-directory residue `archive --restore` closes. Guarded here, not in PerformRename: that
	// function is also `archive --restore`'s own path back OUT of _archive/, so a shared guard
	// would refuse the operation this message points users at. It runs unconditionally, before the
	// apply/dry-run branch, so a preview never promises a move --apply would then decline.
	//
	// "Resolved source" is realpath: an abspath already collapses a `..` argument lexically, but
	// only the realpath also follows a symlink whose target lands inside _archive/ even though
	// neither the argument nor oldAbs ever spells "_archive/".
	archiveRoot := pyRealpath(catalogue.Join(root, "_archive"))
	if under(pyRealpath(oldAbs), archiveRoot) {
		return nil, okferr.New(okferr.InvalidInput,
			"rename: source lies under _archive/ — use archive --restore to bring it back: "+pyRelpath(oldAbs, root))
	}

	result, err := PerformRename(root, oldAbs, newAbs, a.Bool("apply"), a.Bool("force"), "rename", nil, a.JSON)
	if err != nil || !a.JSON {
		return nil, err
	}
	return result, nil
}

// pruneEmptyArchiveDirs removes, after a restore vacated freedDir (the directory that held the
// concept before the move), every directory from there up to and including `_archive/` that the
// move has left empty. It stops at the first directory that still holds something (a sibling
// concept's now-empty subdirectory of its own included) and never touches anything outside
// `_archive/`.
//
// Git does not track empty directories, so a leftover here is invisible to `git status`. That is
// why the walk is a plain listdir/rmdir filesystem operation, not a git one.
func pruneEmptyArchiveDirs(root, freedDir string) {
	archiveRoot := pyRealpath(catalogue.Join(root, "_archive"))
	d := pyRealpath(freedDir)
	for under(d, archiveRoot) {
		if names, err := listdir(d); err != nil || len(names) > 0 {
			break
		}
		if err := syscall.Rmdir(d); err != nil {
			break
		}
		if d == archiveRoot {
			break
		}
		d = pyDirname(d)
	}
}

// runArchive is Python cmd_archive: `archive <bundle>/<concept>[.md]` moves a concept to
// `_archive/<bundle>/<concept>.md`, preserving any subdirectory substructure of the concept id;
// `archive --restore _archive/<bundle>/<concept>[.md]` moves it back. The destination is derived,
// never typed; the three direction guards below are archive's own and run before PerformRename's
// shared guards.
func runArchive(root string, a *cli.Args) (any, error) {
	const verb = "archive"
	die := func(kind okferr.Kind, msg string) error { return okferr.New(kind, verb+": "+msg) }
	restore := a.Bool("restore")

	ref := strings.TrimSuffix(a.String("path"), ".md")
	srcAbs := pyAbspath(catalogue.Join(root, ref+".md"))
	srcRel := pyRelpath(srcAbs, root)
	segs := strings.Split(srcRel, "/")

	var destRel string
	if restore {
		if segs[0] != "_archive" {
			return nil, die(okferr.InvalidInput, "--restore source must lie under _archive/, not: "+srcRel)
		}
		if len(segs) < 3 {
			return nil, die(okferr.InvalidInput, "archive path carries no bundle segment — destination is not "+
				"derivable from: "+srcRel)
		}
		destRel = strings.Join(segs[1:], "/")
	} else {
		if segs[0] == "_archive" {
			return nil, die(okferr.InvalidInput, "source already lies under _archive/ — use --restore to bring "+
				"it back: "+srcRel)
		}
		destRel = strings.Join(append([]string{"_archive"}, segs...), "/")
	}
	destAbs := catalogue.Join(root, destRel)

	// A missing source whose derived counterpart exists is not a bare miss: a reader following a
	// stale reference gets pointed at where the concept actually is, instead of just being told
	// it is gone.
	if !catalogue.RealFS.IsFile(srcAbs) && catalogue.RealFS.IsFile(destAbs) {
		if restore {
			return nil, die(okferr.NotFound, "source not found: "+srcAbs+" — the active copy already exists at "+destRel)
		}
		return nil, die(okferr.NotFound, "source not found: "+srcAbs+" — already archived at "+destRel+
			" (use --restore to bring it back)")
	}

	// The inbound-reference count is a report line, not a guard: it must not gate the move, only
	// disclose what the move leaves behind. A nonexistent source with no archived counterpart is
	// left to PerformRename's own "source not found", so a plan is only built once there is a
	// file to plan a move for.
	var plan *RenamePlan
	var nConcepts any
	if catalogue.RealFS.IsFile(srcAbs) {
		var err error
		if plan, err = PlanRename(root, srcAbs, destAbs); err != nil {
			return nil, err
		}
		sources := map[string]bool{}
		for _, in := range plan.Inbound {
			sources[in.Source] = true
		}
		nConcepts = len(sources)
		if !a.JSON {
			stdio.Printf("%d active concept(s) still link to this concept\n", len(sources))
		}
	}

	result, err := PerformRename(root, srcAbs, destAbs, a.Bool("apply"), a.Bool("force"), verb, plan, a.JSON)
	if err != nil {
		return nil, err
	}
	result.Set("restore", restore)
	result.Set("active_inbound_concepts", nConcepts)

	// Only a restore can empty an _archive/ directory: `archive` in the other direction only ever
	// adds to one. PerformRename already returned on failure, so reaching here means the move
	// happened and the directory the concept just vacated is srcAbs's.
	if restore && a.Bool("apply") {
		pruneEmptyArchiveDirs(root, pyDirname(srcAbs))
	}
	if !a.JSON {
		return nil, nil
	}
	return result, nil
}
