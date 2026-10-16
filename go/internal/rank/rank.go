// Package rank is the pure ranking code of `okf find` (Python cli/okf/find.py, fts.py tokenize and
// semantic.py cosine ranking): the query tokeniser, the substring arm's scoring and order, the BM25
// normalisation, the margin rule and the conditional fusion of the two arms, the cosine ranking of
// the semantic arm and the difflib suggestions of a zero-hit query. Nothing here reads a file, runs
// SQL or touches the network; every function reproduces the arithmetic and the ordering of its
// Python original, ties and rounding included.
package rank

import (
	"cmp"
	"math"
	"slices"
	"strings"
	"unicode"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Contrib is the per-field term breakdown of a substring hit (Python hit["contrib"]): the terms
// found in the title, the tags and the body, in term order. The slices are never nil.
type Contrib struct{ Title, Tags, Body []string }

// Hit is Python find's hit dict.
type Hit struct {
	Score                   int
	Path                    string
	Title, Type, Desc, Snip string
	SupersededBy            string // "" when absent
	Provenance              string // "lexical" | "semantic"
	Cosine                  float64
	Contrib                 *Contrib // nil unless the substring arm made the hit
	FM                      *yaml.Node
}

// Tokenize is fts.tokenize: `re.split(r"[\W_]+", s.lower())` without the empty items. A token is
// a run of Unicode letters and numbers (Python's \w without the underscore); everything else,
// underscore, hyphen and combining marks included, separates. Go's regexp \w is ASCII only, so the
// scan is a rune loop.
func Tokenize(s string) []string {
	s = pytext.Lower(s)
	out := []string{}
	start := -1
	for i, r := range s {
		if unicode.IsLetter(r) || unicode.IsNumber(r) {
			if start < 0 {
				start = i
			}
		} else if start >= 0 {
			out = append(out, s[start:i])
			start = -1
		}
	}
	if start >= 0 {
		out = append(out, s[start:])
	}
	return out
}

// Cut is the Python slice s[:limit]: the first limit items, all of them when limit exceeds the
// length, and for a negative limit everything but the last -limit items. The result shares s and
// has no spare capacity, so an append on it never writes into s.
func Cut[T any](s []T, limit int) []T {
	n := min(len(s), limit)
	if limit < 0 {
		n = max(len(s)+limit, 0)
	}
	return s[:n:n]
}

// ScoreSubstring is the scoring of find._substring_ranking for one concept. A term counts once per
// field it occurs in (str.count truthy), weighted title 3, tags 2, body 1; a term listed twice
// counts twice. The three texts are lower-cased here; the caller passes the tags already joined by
// a space and tokenises the query into terms. Zero score means no hit.
func ScoreSubstring(title, tags, body string, terms []string) (score int, contrib Contrib) {
	title, tags, body = pytext.Lower(title), pytext.Lower(tags), pytext.Lower(body)
	contrib = Contrib{Title: []string{}, Tags: []string{}, Body: []string{}}
	for _, term := range terms {
		if strings.Contains(title, term) {
			score += 3
			contrib.Title = append(contrib.Title, term)
		}
		if strings.Contains(tags, term) {
			score += 2
			contrib.Tags = append(contrib.Tags, term)
		}
		if strings.Contains(body, term) {
			score++
			contrib.Body = append(contrib.Body, term)
		}
	}
	return score, contrib
}

// OrderSubstring is `hits.sort(key=lambda h: -h["score"]); return hits[:limit]`: it sorts hits in
// place, best score first, equal scores keeping their input order, and cuts the list to limit.
func OrderSubstring(hits []*Hit, limit int) []*Hit {
	slices.SortStableFunc(hits, func(a, b *Hit) int { return cmp.Compare(b.Score, a.Score) })
	return Cut(hits, limit)
}

// NormaliseBM25 is `int(round(100 * s / top)) if top else 0` over the positive BM25 scores in rank
// order, top being the first score (1.0 for no scores). Python's round() rounds half to even.
func NormaliseBM25(scores []float64) []int {
	out := make([]int, len(scores))
	if len(scores) == 0 || scores[0] == 0 {
		return out
	}
	top := scores[0]
	for i, s := range scores {
		scaled := 100 * s
		out[i] = int(math.RoundToEven(scaled / top))
	}
	return out
}

// SemanticMarginRatio is find.SEMANTIC_MARGIN_RATIO: the lexical top hit must lead the runner-up
// by at least 1+ratio times to own the ranking.
const SemanticMarginRatio = 0.5

// Confident is find._keyword_top1_is_confident: the lexical arm may own the ranking when it has
// one hit, or a first hit scoring at least (1+SemanticMarginRatio) times the second.
func Confident(hits []*Hit) bool {
	switch len(hits) {
	case 0:
		return false
	case 1:
		return true
	}
	top1, top2 := hits[0].Score, hits[1].Score
	if top1 <= 0 {
		return false
	}
	return float64(top1) >= (1+SemanticMarginRatio)*float64(top2)
}

// FuseConditional is find.fuse_conditional: the arm that owns the ranking (the lexical one when
// Confident, else the semantic one) comes first in its own order, the other arm follows, a path
// already listed is dropped, and the list is cut to limit. lexicalOwned reports who owned it.
func FuseConditional(lexical, semantic []*Hit, limit int) (fused []*Hit, lexicalOwned bool) {
	lexicalOwned = Confident(lexical)
	primary, secondary := semantic, lexical
	if lexicalOwned {
		primary, secondary = lexical, semantic
	}
	fused = make([]*Hit, 0, len(primary)+len(secondary))
	seen := make(map[string]struct{}, len(primary)+len(secondary))
	for _, list := range [2][]*Hit{primary, secondary} {
		for _, hit := range list {
			if _, dup := seen[hit.Path]; dup {
				continue
			}
			seen[hit.Path] = struct{}{}
			fused = append(fused, hit)
		}
	}
	return Cut(fused, limit), lexicalOwned
}
