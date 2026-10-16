// Package tagwrite is the tag curation and frontmatter write commands: `tags` (listing, fuzzy
// search, --validate and --register), merge-tags, remove-tags, normalize-tags, `registry convert`,
// migrate, sync-insert and sync-update (Python okf.tags, okf.registry, okf.migrate and the write
// half of okf.sync), and the registry writer that `tags --register` and `registry convert` share
// (Python catalogue.register_tags, _insert_tag and render_registry_entry).
//
// Every previewing command computes all new texts first; --apply writes exactly the previewed
// texts and a dry run writes nothing. A frontmatter changes only through package yamlpatch, and a
// file the writer rejects ends the whole run before the first write (R-04).
package tagwrite

import (
	"bufio"
	"errors"
	"io"
	"os"
	"path/filepath"

	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// Register attaches the eight commands and the completers of their values.
func Register(app *cli.App) {
	registerTags(app)
	registerTagVerbs(app)
	registerRegistry(app)
	registerSync(app)
}

// newOut is the buffered text output of a handler; flush it before returning.
func newOut() *bufio.Writer { return bufio.NewWriter(os.Stdout) }

// relPath is os.path.relpath(ap, root).replace(os.sep, "/"): the catalogue-relative path of an
// absolute file.
func relPath(root, ap string) string {
	rel, err := filepath.Rel(root, ap)
	if err != nil {
		rel = ap
	}
	return filepath.ToSlash(rel)
}

// planEntry is one (path, stored text, new text) entry of a write plan.
func planEntry(path, old, new string) diffs.PlanEntry {
	return diffs.PlanEntry{Path: path, Old: &old, New: &new}
}

// diffData is the `files` value of a --json result: [{path, old_path, diff}].
func diffData(files []diffs.FileDiff) []envelope.Obj {
	out := make([]envelope.Obj, len(files))
	for i, f := range files {
		var oldPath any
		if f.OldPath != nil {
			oldPath = *f.OldPath
		}
		out[i] = envelope.O("path", f.Path, "old_path", oldPath, "diff", f.Diff)
	}
	return out
}

// printDiffs prints the unified diffs as Python prints them: each text as it is, no added newline.
func printDiffs(w io.Writer, files []diffs.FileDiff) {
	for _, f := range files {
		io.WriteString(w, f.Diff)
	}
}

// patchError names the file of an edit that the frontmatter writer refused. The run ends with it
// before any file is written (R-04). An error of another kind passes through.
func patchError(rel string, err error) error {
	var rejection *yamlpatch.Rejection
	var unread *yamlpatch.ParseError
	switch {
	case errors.As(err, &rejection):
		return okferr.Newf(okferr.InvalidInput, "%s: %s", rel, rejection.Reason)
	case errors.As(err, &unread):
		return okferr.Newf(okferr.InvalidInput, "%s: frontmatter does not parse: %s", rel, unread.Reason)
	}
	return err
}
