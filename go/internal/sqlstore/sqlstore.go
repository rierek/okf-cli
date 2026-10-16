// Package sqlstore opens the two SQLite files a catalogue keeps next to its concepts: the FTS5
// lexical index `<root>/.fts/fts.sqlite` and the tag-vector store
// `<root>/.tagvec/tag_vectors.sqlite` (Python okf.fts._fts_db_path, okf.semantic._tagvec_db_path
// and every sqlite3.connect call on them). It is the only package that imports the SQLite driver
// (modernc.org/sqlite, pure Go, FTS5 and bm25() built in). A binary that links this package
// starts the driver's package initialisation (a few allocations and the registration of the name
// "sqlite", about 0.1 ms); no database file is touched before Open.
package sqlstore

import (
	"context"
	"database/sql"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"modernc.org/sqlite"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// ftsTokenizer is the FTS5 tokenizer of the lexical index: unicode61 folds diacritics (a German
// catalogue needs ä/ö/ü to match a/o/u), porter stems English morphology.
const ftsTokenizer = "porter unicode61 remove_diacritics 2"

// FTSSchema creates the FTS5 table `docs` (Python FTS_SCHEMA); path and ctype are stored, not
// indexed.
const FTSSchema = "CREATE VIRTUAL TABLE docs USING fts5(" +
	"path UNINDEXED, ctype UNINDEXED, title, tags, body, tokenize='" + ftsTokenizer + "')"

// FTSMetaSchema creates the `fts_meta` table that records what the index was built from (Python
// FTS_META_SCHEMA).
const FTSMetaSchema = "CREATE TABLE IF NOT EXISTS fts_meta(k TEXT PRIMARY KEY, v TEXT)"

// FTSBM25Weights is the argument list of bm25(docs, ...): one weight per column of `docs` in
// declaration order (path, ctype, title, tags, body).
const FTSBM25Weights = "0.0, 0.0, 3.0, 2.0, 1.0"

// FTSPath is Python _fts_db_path: `<root>/.fts/fts.sqlite`.
func FTSPath(root string) string {
	return catalogue.Join(catalogue.Join(root, ".fts"), "fts.sqlite")
}

// TagvecPath is Python _tagvec_db_path: `<root>/.tagvec/tag_vectors.sqlite`.
func TagvecPath(root string) string {
	return catalogue.Join(catalogue.Join(root, ".tagvec"), "tag_vectors.sqlite")
}

// Mode says how Open opens a store.
type Mode int

const (
	// Read opens an existing store for reading only. It never creates a file or a directory: a
	// path that is not a regular file is reported as an error that matches fs.ErrNotExist.
	Read Mode = iota
	// Write opens a store for reading and writing and creates its directory (os.makedirs) and the
	// file, as sqlite3.connect does, when they are absent. A handle autocommits every statement;
	// a bulk write belongs in db.Begin.
	Write
)

// busyTimeoutMS is the time a statement waits for a lock before it fails, Python sqlite3.connect's
// default `timeout` of 5 seconds.
const busyTimeoutMS = "5000"

// uriPath escapes the three characters that SQLite's URI parser reads in a path.
var uriPath = strings.NewReplacer("%", "%25", "?", "%3f", "#", "%23")

// Open opens the SQLite file at path and fails where sqlite3.connect fails: when the file cannot
// be opened at all (a directory, no permission). It does not read the file, so bytes that are not
// a database surface at the first statement as an error that IsDatabaseError accepts, as in
// Python. The caller closes the handle.
func Open(path string, mode Mode) (*sql.DB, error) {
	dsn := "file:" + uriPath.Replace(path) + "?_busy_timeout=" + busyTimeoutMS
	if mode == Read {
		if !catalogue.RealFS.IsFile(path) {
			return nil, &fs.PathError{Op: "open", Path: path, Err: fs.ErrNotExist}
		}
		dsn += "&mode=ro"
	} else {
		abs, err := catalogue.Abspath(path)
		if err != nil {
			return nil, err
		}
		if err := os.MkdirAll(filepath.Dir(abs), 0o777); err != nil {
			return nil, err
		}
	}
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	// database/sql connects on first use; connect now so that the file is opened (and created, in
	// Write mode) here, and hand the connection back to the pool.
	conn, err := db.Conn(context.Background())
	if err != nil {
		db.Close()
		return nil, err
	}
	conn.Close()
	return db, nil
}

// IsDatabaseError reports whether err comes from SQLite itself: Python's sqlite3.Error, which
// every caller that degrades on a bad store catches. Errors of the file system and of the
// catalogue are not.
func IsDatabaseError(err error) bool {
	var e *sqlite.Error
	return errors.As(err, &e)
}
