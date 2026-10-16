package fts

import (
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/rank"
	"nas/volume1/data/git/okf-tools/go/internal/sqlstore"
	"nas/volume1/data/git/okf-tools/go/internal/where"
)

// Row is one hit of the BM25 query: the concept path and its raw score, positive (Python's
// -bm25(); a better match scores higher).
type Row struct {
	Path  string
	Score float64
}

// Ranking is Python _fts_ranking: the concepts matching any term of query as a prefix, best first
// (BM25 with title 3, tags 2, body 1; ties by path), at most limit of them after the --where
// filter. The filter is pushed into SQL as far as it goes; what it cannot cover is applied to each
// row before the cut to limit.
//
// ok is false when the caller must fall back to the substring scan (Python None): no index file,
// or one SQLite cannot read. Either way exactly one note says so when notify is set. A query
// without a term gives no rows and ok true. A stale index is answered and, under notify, noted.
func Ranking(root, query string, limit int, filters *where.FindFilters, notify bool) (rows []Row, ok bool, err error) {
	dbPath := sqlstore.FTSPath(root)
	if !catalogue.RealFS.IsFile(dbPath) {
		if notify {
			envelope.Note("lexical index absent — falling back to substring scan; run `okf build-index` for BM25 ranking")
		}
		return nil, false, nil
	}
	terms := rank.Tokenize(query)
	if len(terms) == 0 {
		return []Row{}, true, nil
	}
	quoted := make([]string, len(terms))
	for i, t := range terms {
		quoted[i] = `"` + strings.ReplaceAll(t, `"`, "") + `"*`
	}
	sql := "SELECT path, bm25(docs, " + sqlstore.FTSBM25Weights + ") AS r FROM docs WHERE docs MATCH ?"
	params := []any{strings.Join(quoted, " OR ")}
	clause, clauseParams, residual := filters.SQLWhere(where.FTSFilterColumns)
	sql += clause
	for _, p := range clauseParams {
		params = append(params, p)
	}
	sql += " ORDER BY r, path"
	pushed := !residual.HasExpression()
	if pushed {
		sql += " LIMIT ?"
		params = append(params, limit)
	}
	rows, err = fetch(root, dbPath, sql, params, limit, residual, filters, notify)
	if err != nil {
		if sqlstore.IsDatabaseError(err) {
			if notify {
				envelope.Note("lexical index unusable — falling back to substring scan")
			}
			return nil, false, nil
		}
		return nil, false, err
	}
	return rows, true, nil
}

// fetch runs the query, applies the residual filter and, under notify, checks the index for
// staleness (after the query: a corrupt index must give only the "unusable" note). An error of
// SQLite comes back as it is.
func fetch(root, dbPath, sql string, params []any, limit int, residual, filters *where.FindFilters, notify bool) ([]Row, error) {
	db, err := sqlstore.Open(dbPath, sqlstore.Read)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	cursor, err := db.Query(sql, params...)
	if err != nil {
		return nil, err
	}
	defer cursor.Close()
	out := []Row{}
	for cursor.Next() {
		if residual.HasExpression() && len(out) >= limit {
			break
		}
		var path string
		var raw float64
		if err := cursor.Scan(&path, &raw); err != nil {
			return nil, err
		}
		if residual.HasExpression() {
			matched, err := residual.Matches(root, path)
			if err != nil {
				return nil, err
			}
			if !matched {
				continue
			}
		}
		out = append(out, Row{Path: path, Score: -raw})
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	cursor.Close() // the staleness check below reads from the same handle
	if notify {
		topicsMissing := false
		if filters.IncludeTopics() {
			topics, known := IncludesTopics(root)
			topicsMissing = known && !topics
		}
		if !topicsMissing {
			stale, err := indexStale(root, db, filters.IncludeTopics(), false)
			if err != nil {
				return nil, err
			}
			if stale {
				envelope.Note("lexical index is stale (catalogue changed since build) — run `okf build-index`")
			}
		}
	}
	return out, nil
}
