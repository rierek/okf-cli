package find

import (
	"fmt"
	"path/filepath"
	"strings"
	"time"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/fts"
	"nas/volume1/data/git/okf-tools/go/internal/rank"
	"nas/volume1/data/git/okf-tools/go/internal/semantic"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
	"nas/volume1/data/git/okf-tools/go/internal/where"
)

// Options is one search: what `okf find <Query> --limit <Limit> --where <expression>` takes.
type Options struct {
	Query string
	Limit int
	// Filters is the compiled --where expression (see Compile). Nil searches the default scope,
	// as `okf find` without --where does.
	Filters *where.FindFilters
	// ExpandTags is --expand-tags.
	ExpandTags bool
}

// Hit is one hit as a screen shows it.
type Hit struct {
	Path        string // concept path under the root, without `.md`: `<bundle>/<concept-id>`
	Abs         string // the hit's identity: `<root>/<Path>.md`
	Bundle      string // `_archive/<bundle>` for an archived concept
	Title       string
	Type        string
	Description string
	Snippet     string
	Tags        []string
	Provenance  string // "lexical" | "semantic"
	Tier        string
	Stale       bool
}

// Result is the answer of one search.
type Result struct {
	Hits []Hit // filled by Search
	// Warnings are the notes this call emitted, in order, the ones `okf find` prints as
	// `note: ...` on stderr. They belong to this call alone.
	Warnings []string
	// Empty reports a query without a searchable term; nothing was searched.
	Empty bool

	ranked   []*rank.Hit // the shown hits as the ranking made them
	matched  int         // hits before the cut to Limit
	maxScore int
	now      time.Time
}

// Compile compiles a --where expression (nil for none) under the root's search scope: the bundle
// declared in `.okf.toml`, unless includeTopics widens it to the topic folders.
func Compile(root string, expression *string, includeTopics bool) (*where.FindFilters, error) {
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
	return where.CompileWhere(expression, includeTopics, corpus)
}

// Search runs one search on root and returns the hits in the order `okf find` lists them, plus the
// warnings of this call. Concurrent searches are safe and each collect their own warnings; they
// share only the process-wide cache of query embeddings, which is locked.
func Search(root string, opts Options) (*Result, error) {
	var warnings []string
	r, err := search(root, opts, func(s string) { warnings = append(warnings, s) })
	if err != nil {
		return r, err
	}
	r.Warnings = warnings
	for _, h := range r.ranked {
		r.Hits = append(r.Hits, newHit(root, h, r.now))
	}
	return r, nil
}

// search is the one search body. note receives every warning as it happens: Search collects them,
// `okf find` sends them to envelope.Note, which keeps their place among the command's other output.
func search(root string, opts Options, note func(string)) (*Result, error) {
	filters := opts.Filters
	if filters == nil {
		var err error
		if filters, err = Compile(root, nil, false); err != nil {
			return nil, err
		}
	}
	if filters.IncludeTopics() {
		if topics, known := fts.IncludesTopics(root); known && !topics {
			note("lexical index excludes topic folders — run `okf build-index --include-topics`")
		}
	}
	query, limit := opts.Query, opts.Limit
	terms := rank.Tokenize(query)
	result := &Result{Hits: []Hit{}, Empty: len(terms) == 0, now: filters.Now()}
	if result.Empty {
		return result, nil
	}
	hits, maxScore, err := rankLexically(root, query, terms, limit, filters, note)
	if err != nil {
		return nil, err
	}
	ownedProvisionally := rank.Confident(hits)
	if opts.ExpandTags && !ownedProvisionally {
		extra, err := semantic.ExpandQueryTags(root, query)
		if err != nil {
			return nil, err
		}
		if len(extra) > 0 {
			note("query expanded with tag(s): " + strings.Join(extra, ", "))
			known := terms
			for _, t := range extra {
				if !contains(known, t) {
					terms = append(terms, t)
				}
			}
			if hits, maxScore, err = rankLexically(root, strings.Join(terms, " "), terms, limit, filters, nil); err != nil {
				return nil, err
			}
			ownedProvisionally = rank.Confident(hits)
		}
	}
	var semanticHits []*rank.Hit
	if !ownedProvisionally || len(hits) < limit {
		if semanticHits, err = semanticHitList(root, query, limit, filters, note); err != nil {
			return nil, err
		}
	}
	if filters.IncludeArchive() && len(semanticHits) > 0 {
		note("`archived` in --where covers the lexical arm only; embeddings stay on the active catalogue")
	}
	all, lexicalOwned := rank.FuseConditional(hits, semanticHits, limit)
	if !lexicalOwned && len(semanticHits) > 0 {
		note("semantic arm owns this ranking (lexical top-1 lacked a clear margin)")
	}
	result.ranked = rank.Cut(all, limit)
	result.matched, result.maxScore = len(all), maxScore
	return result, nil
}

// Reload reads hit h again from its file: the title, type, description, tags and snippet as the
// file says them now, and the trust fields. query is the query h answers (for the snippet); the
// provenance of h stays. It fails when the file is gone or unreadable.
func Reload(root string, h Hit, query string) (Hit, error) {
	r, err := hydrate(root, h.Path, rank.Tokenize(query), 0, h.Provenance)
	if err != nil {
		return h, err
	}
	if r == nil {
		return h, fmt.Errorf("%s no longer exists", h.Abs)
	}
	return newHit(root, r, time.Now()), nil
}

// newHit is the screen form of a ranked hit.
func newHit(root string, h *rank.Hit, now time.Time) Hit {
	tier, stale := spec.TrustFields(h.FM, now)
	bundle, _, _ := strings.Cut(h.Path, "/")
	if rest, ok := strings.CutPrefix(h.Path, "_archive/"); ok {
		inner, _, _ := strings.Cut(rest, "/")
		bundle = "_archive/" + inner
	}
	return Hit{
		Path: h.Path, Abs: catalogue.Join(root, filepath.FromSlash(h.Path)+".md"), Bundle: bundle,
		Title: h.Title, Type: h.Type, Description: h.Desc, Snippet: h.Snip,
		Tags: frontmatter.Tags(h.FM), Provenance: provenance(h), Tier: tier, Stale: stale,
	}
}
