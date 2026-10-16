// Package fts is the lexical arm of find: the FTS5 index at <root>/.fts/fts.sqlite (its build, its
// staleness check, the topics flag it records), the BM25 query over it and the `build-index`
// command (Python okf.fts). The index file is shared with the Python CLI in both directions:
// schema, tokenizer and the four fts_meta keys read the same in either implementation.
package fts

import (
	"database/sql"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/sqlstore"
)

// archiveDir is the directory of archived concepts under the root.
const archiveDir = "_archive"

// Register attaches the `build-index` command.
func Register(app *cli.App) {
	app.Attach("build-index", cli.Spec{
		Args: []cli.Arg{
			{Flags: []string{"--include-topics"}, Action: cli.StoreTrue,
				Help: "widen beyond .okf.toml declared bundle to topic folders"},
			{Flags: []string{"--if-stale"}, Action: cli.StoreTrue,
				Help: "skip the rebuild when the existing index is already current (default: always rebuild)"},
			cli.JSON(),
		},
		Handler: run,
	})
}

// run is Python cmd_build_index.
func run(root string, a *cli.Args) (any, error) {
	includeTopics := a.Bool("include_topics")
	if a.Bool("if_stale") {
		dbPath := sqlstore.FTSPath(root)
		if catalogue.RealFS.IsFile(dbPath) {
			stale, err := staleAt(root, dbPath, includeTopics)
			if err != nil {
				return nil, err
			}
			if !stale {
				if a.JSON {
					return envelope.O("applied", false, "concepts", nil, "path", dbPath), nil
				}
				fmt.Printf("index is current, skipping rebuild -> %s\n", dbPath)
				return nil, nil
			}
		}
	}
	n, dbPath, err := Build(root, includeTopics)
	if err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", true, "concepts", n, "path", dbPath), nil
	}
	fmt.Printf("indexed %d concept(s) -> %s\n", n, dbPath)
	return nil, nil
}

// concept is one concept of the indexed corpus: its identity in the index (`<bundle>/<id>`, with
// `_archive/` in front for an archived one), its id inside the bundle and its file.
type concept struct {
	path, cid, abs string
	archived       bool
}

// walkCorpus visits every concept the index covers, the active bundles first and then the archive,
// in walk order: the order Python build_fts_index inserts and _fts_index_stale counts. Bundles come
// from ListSearchBundles, so a `.okf.toml` bundle key narrows the corpus unless includeTopics.
func walkCorpus(root string, includeTopics bool, visit func(concept) error) error {
	bundles, err := catalogue.ListSearchBundles(root, includeTopics, "")
	if err != nil {
		return err
	}
	for _, b := range bundles {
		for cid, ap := range catalogue.IterConcepts(catalogue.Join(root, b), true) {
			if err := visit(concept{path: b + "/" + cid, cid: cid, abs: ap}); err != nil {
				return err
			}
		}
	}
	archiveRoot := catalogue.Join(root, archiveDir)
	if !catalogue.RealFS.IsDir(archiveRoot) {
		return nil
	}
	archived, err := catalogue.ListSearchBundles(archiveRoot, includeTopics, root)
	if err != nil {
		return err
	}
	for _, b := range archived {
		for cid, ap := range catalogue.IterConcepts(catalogue.Join(archiveRoot, b), true) {
			if err := visit(concept{path: archiveDir + "/" + b + "/" + cid, cid: cid, abs: ap, archived: true}); err != nil {
				return err
			}
		}
	}
	return nil
}

// mtime is Python os.path.getmtime: st_mtime as CPython builds it from the stat result,
// `sec + 1e-9 * nsec` in double arithmetic. Python compares and stores exactly this value, so an
// index built by one implementation reads as current in the other.
func mtime(path string) (float64, error) {
	info, err := os.Stat(path)
	if err != nil {
		return 0, err
	}
	t := info.ModTime()
	return float64(t.Unix()) + float64(1e-9*float64(t.Nanosecond())), nil
}

// Build is Python build_fts_index: it indexes the corpus into a `.tmp` sibling of the index file
// and replaces the index with it, so a reader never sees a half-written index. It returns the
// number of indexed concepts (active and archived) and the index path.
func Build(root string, includeTopics bool) (int, string, error) {
	dbPath := sqlstore.FTSPath(root)
	if err := os.MkdirAll(filepath.Dir(dbPath), 0o777); err != nil {
		return 0, "", err
	}
	tmp := dbPath + ".tmp"
	if err := os.Remove(tmp); err != nil && !errors.Is(err, fs.ErrNotExist) {
		return 0, "", err
	}
	db, err := sqlstore.Open(tmp, sqlstore.Write)
	if err != nil {
		return 0, "", err
	}
	n, err := fill(db, root, includeTopics)
	if cerr := db.Close(); err == nil {
		err = cerr
	}
	if err != nil {
		return 0, "", err
	}
	if err := os.Rename(tmp, dbPath); err != nil {
		return 0, "", err
	}
	return n, dbPath, nil
}

// fill creates the tables, inserts the corpus and the four fts_meta rows in one transaction.
func fill(db *sql.DB, root string, includeTopics bool) (int, error) {
	if _, err := db.Exec(sqlstore.FTSSchema); err != nil {
		return 0, err
	}
	if _, err := db.Exec(sqlstore.FTSMetaSchema); err != nil {
		return 0, err
	}
	tx, err := db.Begin()
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()
	insert, err := tx.Prepare("INSERT INTO docs(path, ctype, title, tags, body) VALUES (?, ?, ?, ?, ?)")
	if err != nil {
		return 0, err
	}
	defer insert.Close()
	var nActive, nArchived int
	newest := 0.0
	err = walkCorpus(root, includeTopics, func(c concept) error {
		text, err := catalogue.ReadFile(c.abs)
		if err != nil {
			return err
		}
		doc := frontmatter.Read(text)
		fm := doc.Data()
		title := frontmatter.Text(fm, "title", "")
		if title == "" {
			title = c.cid
		}
		if _, err := insert.Exec(c.path, frontmatter.Text(fm, "type", ""), title,
			strings.Join(frontmatter.Tags(fm), " "), doc.Body); err != nil {
			return err
		}
		if c.archived {
			nArchived++
		} else {
			nActive++
		}
		mt, err := mtime(c.abs)
		if err != nil {
			return err
		}
		if mt > newest {
			newest = mt
		}
		return nil
	})
	if err != nil {
		return 0, err
	}
	topics := "0"
	if includeTopics {
		topics = "1"
	}
	meta := [][2]string{
		{"n_concepts", strconv.Itoa(nActive)},
		{"n_archived", strconv.Itoa(nArchived)},
		{"newest_mtime", pytext.ReprFloat(newest)},
		{"includes_topics", topics},
	}
	for _, kv := range meta {
		if _, err := tx.Exec("INSERT OR REPLACE INTO fts_meta(k, v) VALUES (?, ?)", kv[0], kv[1]); err != nil {
			return 0, err
		}
	}
	if err := tx.Commit(); err != nil {
		return 0, err
	}
	return nActive + nArchived, nil
}

// meta is what fts_meta says the index was built from.
type meta struct {
	nActive, nArchived int
	newest             float64
	storedTopics       bool
}

// readMeta is the first half of Python _fts_index_stale: ok is false when the rows are
// unreadable, missing or malformed, which counts as stale.
func readMeta(db *sql.DB) (m meta, ok bool) {
	rows, err := db.Query("SELECT k, v FROM fts_meta")
	if err != nil {
		return m, false
	}
	defer rows.Close()
	vals := map[string]sql.NullString{}
	for rows.Next() {
		var k, v sql.NullString
		if err := rows.Scan(&k, &v); err != nil {
			return m, false
		}
		vals[k.String] = v
	}
	if rows.Err() != nil {
		return m, false
	}
	text := func(key string) (string, bool) {
		v, found := vals[key]
		return pytext.Strip(v.String), found && v.Valid
	}
	count := func(key string) (int, bool) {
		s, ok := text(key)
		if !ok {
			return 0, false
		}
		n, err := strconv.Atoi(s)
		return n, err == nil
	}
	if m.nActive, ok = count("n_concepts"); !ok {
		return m, false
	}
	if m.nArchived, ok = count("n_archived"); !ok {
		return m, false
	}
	s, ok := text("newest_mtime")
	if !ok {
		return m, false
	}
	m.newest, err = strconv.ParseFloat(s, 64)
	if err != nil && !errors.Is(err, strconv.ErrRange) { // a range error is inf, as float() reads it
		return m, false
	}
	topics := vals["includes_topics"] // meta.get('includes_topics', '0') == '1'
	m.storedTopics = topics.Valid && topics.String == "1"
	return m, true
}

// indexStale is Python _fts_index_stale: whether the corpus differs from what the index was built
// from (concept counts or a newer file). With checkCorpus the index must also have been built for
// the same corpus as includeTopics asks for; without it the counts follow the stored flag. A
// malformed fts_meta counts as stale; an error of the file system is returned.
func indexStale(root string, db *sql.DB, includeTopics, checkCorpus bool) (bool, error) {
	m, ok := readMeta(db)
	if !ok {
		return true, nil
	}
	if checkCorpus && m.storedTopics != includeTopics {
		return true, nil
	}
	counted := includeTopics
	if !checkCorpus {
		counted = m.storedTopics
	}
	var nActive, nArchived int
	newest := 0.0
	err := walkCorpus(root, counted, func(c concept) error {
		if c.archived {
			nArchived++
		} else {
			nActive++
		}
		mt, err := mtime(c.abs)
		if err != nil {
			return err
		}
		if mt > newest {
			newest = mt
		}
		return nil
	})
	if err != nil {
		return false, err
	}
	return nActive != m.nActive || nArchived != m.nArchived || newest > m.newest, nil
}

// staleAt is indexStale over the index file at dbPath, opened for this call only.
func staleAt(root, dbPath string, includeTopics bool) (bool, error) {
	db, err := sqlstore.Open(dbPath, sqlstore.Read)
	if err != nil {
		return false, err
	}
	defer db.Close()
	return indexStale(root, db, includeTopics, true)
}

// IncludesTopics is Python _fts_index_includes_topics: whether the index was built with
// --include-topics. known is false when there is no index or it is unusable (Python None); an
// index without the key reads as built without topics.
func IncludesTopics(root string) (topics, known bool) {
	dbPath := sqlstore.FTSPath(root)
	if !catalogue.RealFS.IsFile(dbPath) {
		return false, false
	}
	db, err := sqlstore.Open(dbPath, sqlstore.Read)
	if err != nil {
		return false, false
	}
	defer db.Close()
	var v sql.NullString
	err = db.QueryRow("SELECT v FROM fts_meta WHERE k = 'includes_topics'").Scan(&v)
	switch {
	case errors.Is(err, sql.ErrNoRows):
		return false, true
	case err != nil:
		return false, false
	}
	return v.Valid && v.String == "1", true
}
