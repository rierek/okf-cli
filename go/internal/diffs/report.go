package diffs

import (
	"io"

	"nas/volume1/data/git/okf-tools/go/internal/envelope"
)

// JSONFiles is the `files` value of a --json result: one {path, old_path, diff} object per entry
// of files, old_path null unless the file moved.
func JSONFiles(files []FileDiff) []envelope.Obj {
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

// PrintFiles writes every diff text as Python prints it: print(entry["diff"], end=""), so no
// newline is added.
func PrintFiles(w io.Writer, files []FileDiff) {
	for _, f := range files {
		io.WriteString(w, f.Diff)
	}
}
