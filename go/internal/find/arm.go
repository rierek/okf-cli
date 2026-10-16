package find

import (
	"math"
	"path/filepath"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/fts"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/rank"
	"nas/volume1/data/git/okf-tools/go/internal/semantic"
	"nas/volume1/data/git/okf-tools/go/internal/where"
)

// rankLexically is Python _rank_lexically: the lexical arm's hits and the scale their score is
// printed against. The FTS index answers when there is a usable one (BM25, scores relative to the
// best hit, scale 100); otherwise the substring scan does (field-weighted counts, scale 6 per term).
func rankLexically(root, query string, terms []string, limit int, filters *where.FindFilters, notify bool) ([]*rank.Hit, int, error) {
	rows, ok, err := fts.Ranking(root, query, limit, filters, notify)
	if err != nil {
		return nil, 0, err
	}
	if !ok {
		hits, err := substringRanking(root, terms, limit, filters)
		return hits, 6 * len(terms), err
	}
	scores := make([]float64, len(rows))
	for i, r := range rows {
		scores[i] = r.Score
	}
	normalised := rank.NormaliseBM25(scores)
	hits := []*rank.Hit{}
	for i, r := range rows {
		hit, err := hydrate(root, r.Path, terms, normalised[i], "lexical")
		if err != nil {
			return nil, 0, err
		}
		if hit != nil {
			hits = append(hits, hit)
		}
	}
	return hits, 100, nil
}

// hydrate is Python _hydrate_hit: the hit a ranked path stands for, read from the concept file
// itself. Only the paths that rank are read, which is what makes the FTS arm cheaper than the full
// scan. It is nil when the path no longer resolves (an index or embedding newer than the tree).
func hydrate(root, path string, terms []string, score int, provenance string) (*rank.Hit, error) {
	ap := catalogue.Join(root, path+".md")
	if !catalogue.RealFS.IsFile(ap) {
		return nil, nil
	}
	text, err := catalogue.ReadFile(ap)
	if err != nil {
		return nil, err
	}
	doc := frontmatter.Read(text)
	fm := doc.Data()
	typ, title, desc := frontmatter.Meta(fm, path[strings.LastIndex(path, "/")+1:])
	return &rank.Hit{
		Score: score, Path: path, Title: title, Type: typ, Desc: desc,
		Snip: makeSnippet(doc.Body, terms), Provenance: provenance, FM: fm,
		SupersededBy: pytext.Strip(frontmatter.Text(fm, "superseded_by", "")),
	}, nil
}

// semanticHitList is Python _semantic_hit_dicts: the semantic arm's ranking hydrated into the shape
// of the lexical hits. The score is round(100 * cosine), on the same 0..100 scale as the BM25 score;
// the two are never fused by score (see rank.FuseConditional).
func semanticHitList(root, query string, limit int, filters *where.FindFilters) ([]*rank.Hit, error) {
	terms := rank.Tokenize(query)
	ranked, err := semantic.Ranking(root, query, limit, filters)
	if err != nil {
		return nil, err
	}
	hits := []*rank.Hit{}
	for _, s := range ranked {
		hit, err := hydrate(root, s.Path, terms, int(math.RoundToEven(100*s.Cosine)), "semantic")
		if err != nil {
			return nil, err
		}
		if hit != nil {
			hit.Cosine = s.Cosine
			hits = append(hits, hit)
		}
	}
	return hits, nil
}

// substringRanking is Python _substring_ranking, the pre-FTS lexical arm and the degradation
// target for a missing or unusable index: substring matching with field weights title 3, tags 2,
// body 1 over a full scan. The expression is enforced twice on purpose: ResolveScopes confines the
// traversal (the active catalogue, plus the archive when the expression names `archived`) and
// MatchesLoaded re-checks the assembled path against the whole expression.
func substringRanking(root string, terms []string, limit int, filters *where.FindFilters) ([]*rank.Hit, error) {
	scopes, err := catalogue.ResolveScopes(root, "", filters.IncludeArchive(), !filters.IncludeTopics())
	if err != nil {
		return nil, err
	}
	var hits []*rank.Hit
	for _, scope := range scopes {
		rel, err := filepath.Rel(root, scope.Path)
		if err != nil {
			return nil, err
		}
		// The prefix is the bundle's position under root (`_archive/<b>` for an archived one), so
		// a hit's path is one `okf read` resolves.
		prefix := filepath.ToSlash(rel)
		for cid, ap := range catalogue.IterConcepts(scope.Path, true) {
			text, err := catalogue.ReadFile(ap)
			if err != nil {
				return nil, err
			}
			doc := frontmatter.Read(text)
			fm, body := doc.Data(), doc.Body
			path := prefix + "/" + cid
			if !filters.MatchesLoaded(path, fm) {
				continue
			}
			title := frontmatter.Text(fm, "title", cid)
			score, contrib := rank.ScoreSubstring(title, strings.Join(frontmatter.Tags(fm), " "), body, terms)
			if score == 0 {
				continue
			}
			hits = append(hits, &rank.Hit{
				Score: score, Path: path, Title: title, Type: frontmatter.Text(fm, "type", ""),
				Desc: frontmatter.Text(fm, "description", ""), Snip: makeSnippet(body, terms),
				Contrib: &contrib, Provenance: "lexical", FM: fm,
				SupersededBy: pytext.Strip(frontmatter.Text(fm, "superseded_by", "")),
			})
		}
	}
	return rank.OrderSubstring(hits, limit), nil
}
