package fts

import (
	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/sqlstore"
)

// Facade of the lexical index for the TUI: the same staleness check as `find` and the same build
// as `build-index`, called in process. Errors come back as values; nothing is noted on the
// envelope or printed.

// State is the condition of the lexical index of a root.
type State int

const (
	Absent  State = iota // no index file
	Stale                // the corpus changed since the build, or the file is unusable
	Current              // the index matches the corpus
)

// Status is the staleness check of `find` and `build-index --if-stale`, against the corpus the
// index was built for. An unusable index file counts as stale, since a rebuild replaces it.
func Status(root string) (State, error) {
	dbPath := sqlstore.FTSPath(root)
	if !catalogue.RealFS.IsFile(dbPath) {
		return Absent, nil
	}
	topics, _ := IncludesTopics(root)
	stale, err := staleAt(root, dbPath, topics)
	switch {
	case err != nil && sqlstore.IsDatabaseError(err):
		return Stale, nil
	case err != nil:
		return Stale, err
	case stale:
		return Stale, nil
	}
	return Current, nil
}

// Refresh rebuilds the index and returns the number of indexed concepts. It keeps the corpus the
// current index was built for (with or without topics); a new index is built without topics.
func Refresh(root string) (int, error) {
	topics, _ := IncludesTopics(root)
	n, _, err := Build(root, topics)
	return n, err
}
