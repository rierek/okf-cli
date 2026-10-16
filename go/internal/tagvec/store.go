package tagvec

import (
	"database/sql"

	"nas/volume1/data/git/okf-tools/go/internal/sqlstore"
)

// TagRow is one row of the `emb` table; Vec is the PackVec blob.
type TagRow struct {
	Key, Tag, Model string
	Dim             int
	Vec             []byte
}

// ConceptRow is one row of the `concept_emb` table; Vec is the PackVec blob.
type ConceptRow struct {
	Key, Path, Model string
	Dim              int
	Vec              []byte
}

// WriteTagRows is Python write_rows: it creates the store (directory and file) and the `emb`
// table when they are absent and replaces or adds all rows in one transaction.
func WriteTagRows(dbPath string, rows []TagRow) error {
	return write(dbPath, Schema, func(tx *sql.Tx) error {
		for _, r := range rows {
			if _, err := tx.Exec("INSERT OR REPLACE INTO emb(key, tag, model, dim, vec) VALUES (?,?,?,?,?)",
				r.Key, r.Tag, r.Model, r.Dim, r.Vec); err != nil {
				return err
			}
		}
		return nil
	})
}

// WriteConceptRows is Python write_concept_rows: it creates the store and the `concept_emb`
// table when they are absent, then, in one transaction, prunes the previous row(s) of every
// (path, model) of rows (a content change derives a new key, so replacing by key alone would
// leave the old row behind; a row of another model for the same path is never touched) and
// inserts rows.
func WriteConceptRows(dbPath string, rows []ConceptRow) error {
	return write(dbPath, ConceptSchema, func(tx *sql.Tx) error {
		pruned := map[[2]string]bool{}
		for _, r := range rows {
			id := [2]string{r.Path, r.Model}
			if pruned[id] {
				continue
			}
			pruned[id] = true
			if _, err := tx.Exec("DELETE FROM concept_emb WHERE path = ? AND model = ?", r.Path, r.Model); err != nil {
				return err
			}
		}
		for _, r := range rows {
			if _, err := tx.Exec("INSERT OR REPLACE INTO concept_emb(key, path, model, dim, vec) VALUES (?,?,?,?,?)",
				r.Key, r.Path, r.Model, r.Dim, r.Vec); err != nil {
				return err
			}
		}
		return nil
	})
}

// write opens the store, runs ddl and then body in one transaction, and closes the store.
func write(dbPath, ddl string, body func(*sql.Tx) error) error {
	db, err := sqlstore.Open(dbPath, sqlstore.Write)
	if err != nil {
		return err
	}
	defer db.Close()
	if _, err := db.Exec(ddl); err != nil {
		return err
	}
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	if err := body(tx); err != nil {
		tx.Rollback()
		return err
	}
	return tx.Commit()
}
