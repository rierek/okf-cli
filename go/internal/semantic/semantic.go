// Package semantic is the semantic arm of find (Python okf.semantic): the concept vectors of the
// tag-vector store, the query embedding, cosine ranking and the tag expansion of --expand-tags,
// plus the `build-semantic-index` command that fills the store. Every read degrades to "arm
// skipped" with one note and never raises; the vectors are written only through the tagvec
// package, the one write path shared with `build-tagvec`.
package semantic

import (
	"database/sql"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"math"
	"os"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/rank"
	"nas/volume1/data/git/okf-tools/go/internal/sqlstore"
	"nas/volume1/data/git/okf-tools/go/internal/tagvec"
	"nas/volume1/data/git/okf-tools/go/internal/where"
)

// Register attaches the `build-semantic-index` command.
func Register(app *cli.App) {
	app.Attach("build-semantic-index", cli.Spec{
		Args: []cli.Arg{
			{Flags: []string{"--if-stale"}, Action: cli.StoreTrue,
				Help: "skip the run when semantic_coverage() already reports every on-disk concept embedded " +
					"(default: always fill the delta)"},
			cli.JSON(),
		},
		Handler: build,
	})
}

// queryVectors is Python's _QUERY_VEC_CACHE: one query text is embedded once per process, so
// --expand-tags and the semantic arm share one call. A failure is not cached.
var queryVectors = map[string][]float64{}

func queryVector(text string) ([]float64, error) {
	if v, ok := queryVectors[text]; ok {
		return v, nil
	}
	v, err := tagvec.EmbedVoyageQuery(text)
	if err != nil {
		return nil, err
	}
	queryVectors[text] = v
	return v, nil
}

// unpack is struct.unpack('<{dim}f', blob): the little-endian float32 values of a stored vector.
func unpack(dim int64, blob []byte) ([]float32, error) {
	if dim < 0 || int64(len(blob)) != 4*dim {
		return nil, fmt.Errorf("unpack requires a buffer of %d bytes", 4*dim)
	}
	vec := make([]float32, dim)
	for i := range vec {
		vec[i] = math.Float32frombits(binary.LittleEndian.Uint32(blob[4*i:]))
	}
	return vec, nil
}

// vectorRow is one row of a vector query, still packed.
type vectorRow struct {
	name string
	dim  int64
	blob []byte
}

// fetchRows runs a `SELECT <name>, dim, vec ...` query against the store file; an error of SQLite
// comes back as it is.
func fetchRows(dbPath, query string, args ...any) ([]vectorRow, error) {
	db, err := sqlstore.Open(dbPath, sqlstore.Read)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	cursor, err := db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer cursor.Close()
	var rows []vectorRow
	for cursor.Next() {
		var r vectorRow
		if err := cursor.Scan(&r.name, &r.dim, &r.blob); err != nil {
			return nil, err
		}
		rows = append(rows, r)
	}
	return rows, cursor.Err()
}

// hasConceptVectors is `SELECT 1 FROM concept_emb WHERE model = ? LIMIT 1`.
func hasConceptVectors(dbPath string) (bool, error) {
	db, err := sqlstore.Open(dbPath, sqlstore.Read)
	if err != nil {
		return false, err
	}
	defer db.Close()
	var one int
	err = db.QueryRow("SELECT 1 FROM concept_emb WHERE model = ? LIMIT 1", tagvec.SemanticModel).Scan(&one)
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	return err == nil, err
}

// loadConceptVectors is Python _load_concept_vectors: the voyage vectors of the concepts the
// filter lets through (the SQL part of it; the residual comes back for the caller to apply). found
// is false (Python None) when there is no store, it is unusable, or it holds no vector for the
// model; an empty result with found true means the filter excluded every stored vector.
func loadConceptVectors(dbPath string, filters *where.FindFilters) (vecs []rank.PathVec, found bool, residual *where.FindFilters, err error) {
	clause, params, residual := filters.SQLWhere(where.EMBFilterColumns)
	if !catalogue.RealFS.IsFile(dbPath) {
		return nil, false, residual, nil
	}
	args := append([]any{tagvec.SemanticModel}, anys(params)...)
	rows, err := fetchRows(dbPath, "SELECT path, dim, vec FROM concept_emb WHERE model = ?"+clause, args...)
	if err == nil && len(rows) == 0 && filters.HasExpression() {
		var have bool
		if have, err = hasConceptVectors(dbPath); err == nil && have {
			return []rank.PathVec{}, true, residual, nil
		}
	}
	if err != nil {
		if sqlstore.IsDatabaseError(err) {
			return nil, false, residual, nil
		}
		return nil, false, residual, err
	}
	if len(rows) == 0 {
		return nil, false, residual, nil
	}
	vecs = make([]rank.PathVec, len(rows))
	for i, r := range rows {
		vec, err := unpack(r.dim, r.blob)
		if err != nil {
			return nil, false, residual, err
		}
		vecs[i] = rank.PathVec{Path: r.name, Vec: vec}
	}
	return vecs, true, residual, nil
}

func anys(ss []string) []any {
	out := make([]any, len(ss))
	for i, s := range ss {
		out[i] = s
	}
	return out
}

// loadTagVectors is Python _load_tag_vectors: the voyage vectors of the registered tags, nil when
// there is no store, it is unusable or it holds none.
func loadTagVectors(dbPath string) ([]rank.TagVec, error) {
	if !catalogue.RealFS.IsFile(dbPath) {
		return nil, nil
	}
	rows, err := fetchRows(dbPath, "SELECT tag, dim, vec FROM emb WHERE model = ?", tagvec.SemanticModel)
	if err != nil {
		if sqlstore.IsDatabaseError(err) {
			return nil, nil
		}
		return nil, err
	}
	vecs := make([]rank.TagVec, len(rows))
	for i, r := range rows {
		vec, err := unpack(r.dim, r.blob)
		if err != nil {
			return nil, err
		}
		vecs[i] = rank.TagVec{Tag: r.name, Vec: vec}
	}
	return vecs, nil
}

// ExpandQueryTags is Python _expand_query_tags: the (up to 3) registered tags whose vector is
// within cosine 0.6 of the query, best first. Silent: no tag vectors or no embedding backend
// gives none.
func ExpandQueryTags(root, query string) ([]string, error) {
	vecs, err := loadTagVectors(sqlstore.TagvecPath(root))
	if err != nil || len(vecs) == 0 {
		return nil, err
	}
	qvec, err := queryVector(query)
	if err != nil {
		return nil, nil
	}
	return rank.NearestTags(qvec, vecs, 3, 0.6), nil
}

// Ranking is Python semantic_ranking: the concepts closest to the query by cosine, best first,
// at most limit of them after the --where filter, each with its cosine. No vectors or no
// embedding backend skips the arm with one note and gives none.
func Ranking(root, query string, limit int, filters *where.FindFilters) ([]rank.Scored, error) {
	vecs, found, residual, err := loadConceptVectors(sqlstore.TagvecPath(root), filters)
	if err != nil {
		return nil, err
	}
	if !found {
		envelope.Note("semantic arm skipped (.tagvec cache/concept embeddings absent) — lexical results only")
		return []rank.Scored{}, nil
	}
	if len(vecs) == 0 {
		return []rank.Scored{}, nil
	}
	qvec, err := queryVector(query)
	if err != nil {
		envelope.Note(fmt.Sprintf("semantic arm skipped (embedding backend unavailable: %v) — lexical results only", err))
		return []rank.Scored{}, nil
	}
	ranked := rank.RankCosine(qvec, vecs)
	if !residual.HasExpression() {
		return rank.Cut(ranked, limit), nil
	}
	out := []rank.Scored{}
	for _, s := range ranked {
		if len(out) >= limit {
			break
		}
		matched, err := residual.Matches(root, s.Path)
		if err != nil {
			return nil, err
		}
		if matched {
			out = append(out, s)
		}
	}
	return out, nil
}

// build is Python cmd_build_semantic_index: embed every concept whose voyage vector is missing or
// out of date and store it. It never raises on an unavailable or failing backend: a missing key,
// a failed batch or any error of the build is a note, and the lexical arm is unaffected.
func build(root string, a *cli.Args) (any, error) {
	dbPath := sqlstore.TagvecPath(root)
	result := envelope.O("applied", false, "embedded", 0, "path", dbPath)
	if a.Bool("if_stale") {
		bundles, err := catalogue.ListIndexableBundles(root, "")
		if err != nil {
			return nil, err
		}
		var paths []string
		for _, b := range bundles {
			for cid := range catalogue.IterConcepts(catalogue.Join(root, b), true) {
				paths = append(paths, b+"/"+cid)
			}
		}
		cov, ok, err := tagvec.SemanticCoverage(root, paths)
		if err != nil {
			return nil, err
		}
		if ok && cov.Embedded >= cov.Total {
			if !a.JSON {
				fmt.Printf("semantic index is current, skipping rebuild -> %s\n", dbPath)
			}
			return result, nil
		}
	}
	if os.Getenv("VOYAGE_API_KEY") == "" {
		envelope.Note("semantic index build skipped (VOYAGE_API_KEY not set) -- run again once it is set, " +
			"or set it before the next SessionStart hook run")
		return result, nil
	}
	// The retry lines of embed_resilient are stdout in Python; under --json they would break the
	// one-envelope contract, so they go to stderr there.
	progress := io.Writer(os.Stdout)
	if a.JSON {
		progress = os.Stderr
	}
	written, left, err := fill(root, dbPath, progress)
	if err != nil {
		class, message, ok := sqlstore.PyError(err)
		if !ok {
			class, message = "Error", err.Error()
		}
		envelope.Note(fmt.Sprintf("semantic index build failed (%s: %s) -- lexical arm unaffected", class, message))
		return result, nil
	}
	result.Set("applied", written > 0)
	result.Set("embedded", written)
	if !a.JSON {
		fmt.Printf("embedded %d concept(s) -> %s\n", written, dbPath)
	}
	if left > 0 {
		envelope.Note(fmt.Sprintf("semantic index build incomplete -- %d concept(s) left unembedded after retries; "+
			"rerun to pick up the rest", left))
	}
	return result, nil
}

// fill embeds the concept delta in batches and writes each batch as it arrives, so a failure
// later keeps what is done. It returns the rows written and the planned concepts left unembedded
// when a batch was skipped (0 when none was).
func fill(root, dbPath string, progress io.Writer) (written, left int, err error) {
	delta, err := tagvec.PlanConceptDelta(root, tagvec.SemanticModel, dbPath, "", 0)
	if err != nil {
		return 0, 0, err
	}
	maxItems, maxChars := tagvec.BatchLimits(tagvec.SemanticModel)
	incomplete := false
	for _, batch := range tagvec.Batches(delta, maxItems, maxChars) {
		texts := make([]string, len(batch))
		for i, t := range batch {
			texts[i] = t.Text
		}
		vectors := tagvec.EmbedResilient(tagvec.EmbedVoyage, texts, "voyage concepts "+batch[0].Item+"..", progress)
		if vectors == nil {
			incomplete = true
			continue
		}
		rows := make([]tagvec.ConceptRow, 0, len(batch))
		for i, t := range batch {
			if i >= len(vectors) { // zip(): the shorter of the two decides
				break
			}
			rows = append(rows, tagvec.ConceptRow{Key: t.Key, Path: t.Item, Model: tagvec.SemanticModel,
				Dim: tagvec.Dim(tagvec.SemanticModel), Vec: tagvec.PackVec(vectors[i])})
		}
		if err := tagvec.WriteConceptRows(dbPath, rows); err != nil {
			return 0, 0, err
		}
		written += len(rows)
	}
	if incomplete {
		left = len(delta) - written
	}
	return written, left, nil
}
