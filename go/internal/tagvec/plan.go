package tagvec

import (
	"os"
	"path/filepath"
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/sqlstore"
)

// storedKeys is Python existing_keys and existing_concept_keys, the delta-reuse gate: the cache
// keys already in the store, empty when the file does not exist. As in Python an existing file
// is opened for writing and ddl runs first, so a store that lacks the table gets it created;
// an error of SQLite is returned as it is (sqlstore.IsDatabaseError).
func storedKeys(dbPath, ddl, query string) (map[string]struct{}, error) {
	have := map[string]struct{}{}
	if _, err := os.Stat(dbPath); err != nil {
		return have, nil
	}
	db, err := sqlstore.Open(dbPath, sqlstore.Write)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	if _, err := db.Exec(ddl); err != nil {
		return nil, err
	}
	rows, err := db.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var key any // a key column holds whatever was inserted; only text can equal a cache key
		if err := rows.Scan(&key); err != nil {
			return nil, err
		}
		if s, ok := key.(string); ok {
			have[s] = struct{}{}
		}
	}
	return have, rows.Err()
}

// PlanDelta is Python plan_delta: the (tag, slug text, key) triples of tags, in sorted tag order,
// whose key for model is not yet in the `emb` table of the store at dbPath. The tags are not
// de-duplicated: a caller that hands Python a set hands distinct tags here. A store that does not
// exist plans every tag.
func PlanDelta(tags []string, model, dbPath string) ([]Triple, error) {
	have, err := storedKeys(dbPath, Schema, "SELECT key FROM emb")
	if err != nil {
		return nil, err
	}
	out := []Triple{}
	for _, tag := range slices.Sorted(slices.Values(tags)) {
		text := SlugText(tag)
		key := CacheKey(model, text)
		if _, ok := have[key]; !ok {
			out = append(out, Triple{tag, text, key})
		}
	}
	return out, nil
}

// concept is one catalogue concept: its identity `<bundle>/<concept-id>` and its file.
type concept struct{ path, abs string }

// concepts is Python _iter_all_concepts under sorted(): every concept of every bundle (ListBundles,
// so scaffolding directories included) ordered by identity, then file.
func concepts(root string) ([]concept, error) {
	bundles, err := catalogue.ListBundles(root)
	if err != nil {
		return nil, err
	}
	var all []concept
	for _, b := range bundles {
		for cid, ap := range catalogue.IterConcepts(catalogue.Join(root, b), true) {
			all = append(all, concept{b + "/" + cid, ap})
		}
	}
	slices.SortFunc(all, func(x, y concept) int {
		if c := strings.Compare(x.path, y.path); c != 0 {
			return c
		}
		return strings.Compare(x.abs, y.abs)
	})
	return all, nil
}

// PlanConceptDelta is Python plan_concept_delta: the (path, title+body text, key) triples of
// every concept of the catalogue at root, in path order, whose key for model is not yet in the
// `concept_emb` table of the store at dbPath. A concept path that does not start with pathPrefix
// is skipped (the empty prefix keeps all). Planning stops once limit triples are collected, after
// the prefix filter; 0 means no limit, and a negative limit stops after the first triple, as in
// Python. A store that does not exist plans every concept.
func PlanConceptDelta(root, model, dbPath, pathPrefix string, limit int) ([]Triple, error) {
	have, err := storedKeys(dbPath, ConceptSchema, "SELECT key FROM concept_emb")
	if err != nil {
		return nil, err
	}
	all, err := concepts(root)
	if err != nil {
		return nil, err
	}
	out := []Triple{}
	for _, c := range all {
		if !strings.HasPrefix(c.path, pathPrefix) {
			continue
		}
		raw, err := catalogue.ReadFile(c.abs)
		if err != nil {
			return nil, err
		}
		parsed := frontmatter.Read(raw)
		_, title, _ := frontmatter.Meta(parsed.Data(), strings.TrimSuffix(filepath.Base(c.abs), ".md"))
		text := ConceptText(title, parsed.Body)
		key := ConceptCacheKey(model, c.path, text)
		if _, ok := have[key]; !ok {
			out = append(out, Triple{c.path, text, key})
			if limit != 0 && len(out) >= limit {
				break
			}
		}
	}
	return out, nil
}

// Coverage is the answer of SemanticCoverage: of Total concepts asked about, Embedded have an
// embedding that matches their current content.
type Coverage struct{ Embedded, Total int }

// SemanticCoverage is Python semantic_coverage: the coverage of the concepts named in paths
// (`<bundle>/<concept-id>`, as many entries as the caller lists, duplicates included in Total),
// or ok false when the catalogue has no tag-vector store file or the store is unusable (an
// error of SQLite). It plans the concept delta against SemanticModel, the same content-hash
// comparison the producer acts on, and counts the asked paths the delta does not name. It reads
// and hashes every concept, so it is not for a hot path. Any other failure, such as an
// unreadable concept, is returned.
func SemanticCoverage(root string, paths []string) (cov Coverage, ok bool, err error) {
	db := sqlstore.TagvecPath(root)
	if !catalogue.RealFS.IsFile(db) {
		return Coverage{}, false, nil
	}
	delta, err := PlanConceptDelta(root, SemanticModel, db, "", 0)
	if err != nil {
		if sqlstore.IsDatabaseError(err) {
			return Coverage{}, false, nil
		}
		return Coverage{}, false, err
	}
	asked := make(map[string]struct{}, len(paths))
	for _, p := range paths {
		asked[p] = struct{}{}
	}
	stale := map[string]struct{}{}
	for _, t := range delta {
		if _, named := asked[t.Item]; named {
			stale[t.Item] = struct{}{}
		}
	}
	return Coverage{len(paths) - len(stale), len(paths)}, true, nil
}
