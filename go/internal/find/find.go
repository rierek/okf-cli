// Package find is the `find` command (Python okf.find): hybrid ranked search over the catalogue.
// The lexical arm (BM25 over the FTS5 index, or the substring scan when there is no usable index)
// and the semantic arm (cosine over the concept vectors) both run under one --where filter; a
// conditional handover decides per query which arm owns the ranking. Every degraded arm says so
// with exactly one stderr note and the command still answers.
package find

import (
	"fmt"
	"strings"
	"time"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/fts"
	"nas/volume1/data/git/okf-tools/go/internal/rank"
	"nas/volume1/data/git/okf-tools/go/internal/semantic"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
	"nas/volume1/data/git/okf-tools/go/internal/where"
)

// Register attaches the `find` command.
func Register(app *cli.App) {
	app.Attach("find", cli.Spec{
		Args: []cli.Arg{
			{Dest: "query", Help: "search terms; quote multi-word queries"},
			{Flags: []string{"--include-topics"}, Action: cli.StoreTrue,
				Help: "widen beyond .okf.toml declared bundle to topic folders"},
			{Flags: []string{"--limit"}, Type: cli.Int, Default: 10, Help: "max results to print (default 10)"},
			cli.WhereArg(),
			{Flags: []string{"--breakdown"}, Action: cli.StoreTrue,
				Help: "print per-hit contributing field(s)/term(s); output is byte-identical to today without this flag"},
			{Flags: []string{"--expand-tags"}, Action: cli.StoreTrue,
				Help: "expand the query with semantically near registered tags before lexical scoring; " +
					"measured against the full catalogue and found ineffective for the vocabulary-mismatch " +
					"class it was built for, so it stays off by default (Q05/D17)"},
			cli.JSON(),
		},
		Epilog:  findEpilog,
		Raw:     true,
		Handler: run,
	})
}

// run is Python cmd_find.
func run(root string, a *cli.Args) (any, error) {
	includeTopics := a.Bool("include_topics")
	config, err := catalogue.LoadConfig(root)
	if err != nil {
		return nil, err
	}
	var corpus []string
	if bundle, _ := config["bundle"].(string); bundle != "" && !includeTopics {
		if corpus, err = catalogue.ListSearchBundles(root, false, ""); err != nil {
			return nil, err
		}
	}
	var expression *string
	if a.Has("where") {
		text := a.String("where")
		expression = &text
	}
	filters, err := where.CompileWhere(expression, includeTopics, corpus)
	if err != nil {
		return nil, err
	}
	if includeTopics {
		if topics, known := fts.IncludesTopics(root); known && !topics {
			envelope.Note("lexical index excludes topic folders — run `okf build-index --include-topics`")
		}
	}
	query, limit := a.String("query"), a.Int("limit")
	terms := rank.Tokenize(query)
	if len(terms) == 0 {
		if a.JSON {
			return envelope.O("hits", []any{}, "nearest_tags", []any{}), nil
		}
		stdio.Println("(empty query)")
		return nil, nil
	}
	breakdown := a.Bool("breakdown")
	hits, maxScore, err := rankLexically(root, query, terms, limit, filters, true)
	if err != nil {
		return nil, err
	}
	ownedProvisionally := rank.Confident(hits)
	if a.Bool("expand_tags") && !ownedProvisionally {
		extra, err := semantic.ExpandQueryTags(root, query)
		if err != nil {
			return nil, err
		}
		if len(extra) > 0 {
			envelope.Note("query expanded with tag(s): " + strings.Join(extra, ", "))
			known := terms
			for _, t := range extra {
				if !contains(known, t) {
					terms = append(terms, t)
				}
			}
			if hits, maxScore, err = rankLexically(root, strings.Join(terms, " "), terms, limit, filters, false); err != nil {
				return nil, err
			}
			ownedProvisionally = rank.Confident(hits)
		}
	}
	var semanticHits []*rank.Hit
	if !ownedProvisionally || len(hits) < limit {
		if semanticHits, err = semanticHitList(root, query, limit, filters); err != nil {
			return nil, err
		}
	}
	if filters.IncludeArchive() && len(semanticHits) > 0 {
		envelope.Note("`archived` in --where covers the lexical arm only; embeddings stay on the active catalogue")
	}
	all, lexicalOwned := rank.FuseConditional(hits, semanticHits, limit)
	if !lexicalOwned && len(semanticHits) > 0 {
		envelope.Note("semantic arm owns this ranking (lexical top-1 lacked a clear margin)")
	}
	shown := rank.Cut(all, limit)
	if a.JSON {
		records := make([]envelope.Obj, len(shown))
		for i, h := range shown {
			records[i] = hitRecord(i+1, h, breakdown, maxScore, filters.Now())
		}
		nearest := []string{}
		if len(all) == 0 {
			if nearest, err = zeroHitSuggestions(root, query); err != nil {
				return nil, err
			}
		}
		return envelope.O("hits", records, "nearest_tags", nearest), nil
	}
	if len(all) == 0 {
		stdio.Printf("(no matches for: %s)\n", query)
		near, err := zeroHitSuggestions(root, query)
		if err != nil {
			return nil, err
		}
		if len(near) > 0 {
			stdio.Printf("nearest registered tags: %s\n", strings.Join(near, ", "))
			stdio.Printf("try: okf find \"%s\"\n", strings.Join(rank.Cut(near, 2), " "))
		}
		return nil, nil
	}
	for i, h := range shown {
		printHit(i+1, h, breakdown, maxScore)
	}
	stdio.Println("------")
	return nil, nil
}

func contains(list []string, s string) bool {
	for _, v := range list {
		if v == s {
			return true
		}
	}
	return false
}

// zeroHitSuggestions is Python _zero_hit_suggestions: the registered tags nearest to the query's
// terms, for an answer without a hit.
func zeroHitSuggestions(root, query string) ([]string, error) {
	counts, err := catalogue.AllTags(root)
	if err != nil {
		return nil, err
	}
	return rank.ZeroHitSuggestions(rank.Tokenize(query), counts.Sorted(), 5), nil
}

// printHit is one hit block of the text answer.
func printHit(n int, h *rank.Hit, breakdown bool, maxScore int) {
	stdio.Println("------")
	stdio.Printf("rank: %d\n", n)
	stdio.Printf("title: %s\n", h.Title)
	stdio.Printf("type: %s\n", h.Type)
	if h.SupersededBy != "" {
		stdio.Printf("superseded_by: %s\n", h.SupersededBy)
	}
	stdio.Printf("path: %s\n", h.Path)
	stdio.Printf("description: %s\n", h.Desc)
	stdio.Printf("body-snippet: %s\n", h.Snip)
	stdio.Printf("provenance: %s\n", provenance(h))
	if !breakdown {
		return
	}
	switch {
	case h.Provenance == "semantic":
		stdio.Printf("score: cosine %.2f\n", h.Cosine)
		stdio.Printf("contrib: semantic-only (cosine=%.2f, no keyword field match)\n", h.Cosine)
	default:
		stdio.Printf("score: %d/%d\n", h.Score, maxScore)
		if h.Contrib != nil {
			stdio.Printf("contrib: %s\n", formatContrib(h.Contrib))
		} else {
			stdio.Println("contrib: bm25 (fts5 index; field-level breakdown not available)")
		}
	}
}

// provenance is the arm that produced a hit; a hit without one is lexical.
func provenance(h *rank.Hit) string {
	if h.Provenance == "" {
		return "lexical"
	}
	return h.Provenance
}

// formatContrib is Python _format_contrib: which field(s) each term hit.
func formatContrib(c *rank.Contrib) string {
	var parts []string
	for _, f := range []struct {
		name  string
		terms []string
	}{{"title", c.Title}, {"tags", c.Tags}, {"body", c.Body}} {
		if len(f.terms) > 0 {
			parts = append(parts, fmt.Sprintf("%s=[%s]", f.name, strings.Join(f.terms, ",")))
		}
	}
	if len(parts) == 0 {
		return "(none)"
	}
	return strings.Join(parts, "; ")
}

// hitRecord is Python _hit_record: one hit as the envelope carries it, with its trust tier and
// staleness at now, and under --breakdown the values of the arm that produced it.
func hitRecord(n int, h *rank.Hit, breakdown bool, maxScore int, now time.Time) envelope.Obj {
	record := envelope.O("rank", n, "title", h.Title, "type", h.Type)
	if h.SupersededBy != "" {
		record.Set("superseded_by", h.SupersededBy)
	}
	tier, stale := spec.TrustFields(h.FM, now)
	record.Set("path", h.Path)
	record.Set("description", h.Desc)
	record.Set("snippet", h.Snip)
	record.Set("provenance", provenance(h))
	record.Set("tier", tier)
	record.Set("stale", stale)
	if breakdown {
		if h.Provenance == "semantic" {
			record.Set("breakdown", envelope.O("cosine", h.Cosine))
		} else {
			var contrib any
			if h.Contrib != nil {
				contrib = envelope.O("title", h.Contrib.Title, "tags", h.Contrib.Tags, "body", h.Contrib.Body)
			}
			record.Set("breakdown", envelope.O("score", h.Score, "max_score", maxScore, "contrib", contrib))
		}
	}
	return record
}
