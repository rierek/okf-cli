package rank_test

import (
	"slices"
	"strings"
	"testing"

	"nas/volume1/data/git/okf-tools/go/internal/rank"
)

// tags is a registered tag list, sorted as the caller hands it over.
var tags = []string{
	"architecture", "backup", "bean", "build", "catalogue", "cli", "config", "deploy", "docker",
	"docs", "embedding", "fts", "git", "go-port", "golang", "gopher", "just", "node18", "node20",
	"node22", "node24", "node26", "node28", "okf", "python", "semantic", "semantic-search",
	"sqlite", "tag", "tag-vectors", "tagged", "tagging", "tags", "tagvec", "test", "testbed",
	"tested", "tester", "testing", "tests", "tpic", "voyage",
}

func TestCloseMatches(t *testing.T) {
	// Python reference: difflib.get_close_matches(word, possibilities, n, cutoff).
	for _, c := range []struct {
		name          string
		word          string
		n             int
		cutoff        float64
		possibilities []string
		want          []string
	}{
		{
			name: "difflib docs example", word: "appel", n: 3, cutoff: 0.6,
			possibilities: []string{"ape", "apple", "peach", "puppy"},
			want:          []string{"apple", "ape"},
		},
		{
			name: "n cuts the result", word: "appel", n: 1, cutoff: 0.6,
			possibilities: []string{"ape", "apple", "peach", "puppy"},
			want:          []string{"apple"},
		},
		{
			name: "n larger than the matches", word: "appel", n: 10, cutoff: 0.6,
			possibilities: []string{"ape", "apple", "peach", "puppy"},
			want:          []string{"apple", "ape"},
		},
		{
			name: "equal ratios order by string descending", word: "ab", n: 5, cutoff: 0.5,
			possibilities: []string{"ac", "ad", "aa", "ae"},
			want:          []string{"ae", "ad", "ac", "aa"},
		},
		{
			name: "equal ratios, n cuts the tail of the order", word: "ab", n: 2, cutoff: 0.5,
			possibilities: []string{"ac", "ad", "aa", "ae"},
			want:          []string{"ae", "ad"},
		},
		{
			name: "cutoff equal to a ratio keeps it", word: "abcd", n: 3, cutoff: 0.75,
			possibilities: []string{"abxd", "wxyz"},
			want:          []string{"abxd"},
		},
		{
			name: "cutoff just above a ratio drops it", word: "abcd", n: 3, cutoff: 0.7500000000000001,
			possibilities: []string{"abxd", "wxyz"},
			want:          []string{},
		},
		{
			name: "cutoff 0 keeps every possibility", word: "abc", n: 5, cutoff: 0.0,
			possibilities: []string{"xyz", "abd", "abc"},
			want:          []string{"abc", "abd", "xyz"},
		},
		{
			name: "cutoff 1 keeps exact matches only", word: "abc", n: 5, cutoff: 1.0,
			possibilities: []string{"xyz", "abd", "abc", "abc"},
			want:          []string{"abc", "abc"},
		},
		{
			name: "no possibility", word: "abc", n: 3, cutoff: 0.6,
			possibilities: []string{},
			want:          []string{},
		},
		{
			name: "duplicate possibilities", word: "apple", n: 3, cutoff: 0.6,
			possibilities: []string{"apple", "apple", "ape"},
			want:          []string{"apple", "apple", "ape"},
		},
		{
			name: "empty word", word: "", n: 3, cutoff: 0.7,
			possibilities: []string{"", "a"},
			want:          []string{""},
		},
		{
			name: "word shorter than the possibilities", word: "a", n: 5, cutoff: 0.6,
			possibilities: []string{"ab", "a", "ba", "abc"},
			want:          []string{"a", "ba", "ab"},
		},
		{
			name: "the possibility is the first sequence: ratio 0.57 against the word", word: "bcba", n: 3, cutoff: 0.5,
			possibilities: []string{"cab"},
			want:          []string{"cab"},
		},
		{
			name: "the word is the second sequence: ratio 0.17 for the possibility", word: "cccca", n: 3, cutoff: 0.4,
			possibilities: []string{"acbcbac"},
			want:          []string{},
		},
		{
			name: "accented letters are one element", word: "caf\u00e9", n: 5, cutoff: 0.6,
			possibilities: []string{"cafe", "cafés", "caffè", "cave", "café"},
			want:          []string{"café", "cafés", "cafe", "caffè"},
		},
		{
			name: "sharp s", word: "stra\u00dfe", n: 5, cutoff: 0.6,
			possibilities: []string{"strasse", "strase", "straße", "strasz"},
			want:          []string{"straße", "strase", "strasse", "strasz"},
		},
		{
			name: "astral plane character is one element", word: "a\U0001f600b", n: 5, cutoff: 0.6,
			possibilities: []string{"a😀c", "a😀b", "ab", "a😀"},
			want:          []string{"a😀b", "a😀", "ab", "a😀c"},
		},
		{
			name: "cjk", word: "\u65e5\u672c\u8a9e", n: 5, cutoff: 0.6,
			possibilities: []string{"日本", "本語", "日本語語", "英語"},
			want:          []string{"日本語語", "本語", "日本"},
		},
		{
			name: "tag list: dokcer, n 5", word: "dokcer", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"docker"},
		},
		{
			name: "tag list: embeding, n 5", word: "embeding", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"embedding"},
		},
		{
			name: "tag list: semantik, n 5", word: "semantik", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"semantic"},
		},
		{
			name: "tag list: tagvect, n 5", word: "tagvect", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"tagvec", "tag-vectors"},
		},
		{
			name: "tag list: gitt, n 5", word: "gitt", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"git"},
		},
		{
			name: "tag list: pythn, n 5", word: "pythn", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"python"},
		},
		{
			name: "tag list: postgres, n 5", word: "postgres", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{},
		},
		{
			name: "tag list: buil, n 5", word: "buil", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"build"},
		},
		{
			name: "tag list: doc, n 5", word: "doc", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"docs"},
		},
		{
			name: "tag list: tests, n 5", word: "tests", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"tests", "test", "tester", "tested"},
		},
		{
			name: "tag list: node, n 5", word: "node", n: 5, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"node28", "node26", "node24", "node22", "node20"},
		},
		{
			name: "tag list: node, n 8", word: "node", n: 8, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"node28", "node26", "node24", "node22", "node20", "node18"},
		},
		{
			name: "tag list: tagz, n 3", word: "tagz", n: 3, cutoff: 0.7,
			possibilities: tags,
			want:          []string{"tag", "tags"},
		},
		{
			name: "tag list: low cutoff", word: "dokcer", n: 5, cutoff: 0.4,
			possibilities: tags,
			want:          []string{"docker", "docs", "gopher", "okf"},
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			got := rank.CloseMatches(c.word, c.possibilities, c.n, c.cutoff)
			if got == nil || !slices.Equal(got, c.want) {
				t.Errorf("CloseMatches(%q, n %d, cutoff %v) = %q, want %q", c.word, c.n, c.cutoff, got, c.want)
			}
		})
	}
}

// run is n distinct characters: the n consecutive code points from `from`.
func run(from rune, n int) string {
	var b strings.Builder
	for i := range n {
		b.WriteRune(from + rune(i))
	}
	return b.String()
}

// A word of 200 or more characters has its popular elements (more than n//100+1 occurrences)
// left out of the index the matches are found through; they are only picked up where a found
// match extends over them.
func TestCloseMatchesPopularElements(t *testing.T) {
	// Python reference: difflib.get_close_matches(word, possibilities, 5, 0.7), for the first case
	// with possibilities of 210, 211, 211, 212, 207 and 210 characters; their ratios without
	// autojunk would be 1.0, 0.9976, 0.9976, 0.9952, 0.9928 and 0.9952.
	word210 := strings.Repeat("abc", 70)
	possibilities := []string{
		word210, "x" + word210, word210 + "x", "x" + word210 + "x", strings.Repeat("abc", 69), strings.Repeat("cab", 70),
	}
	want := []string{word210, word210 + "x", strings.Repeat("abc", 69)}
	if got := rank.CloseMatches(word210, possibilities, 5, 0.7); !slices.Equal(got, want) {
		t.Errorf("word of 210 characters: got %d matches, want %d (indexes 0, 2, 4)", len(got), len(want))
	}

	// Python reference: difflib.get_close_matches(word, [cand], 3, cutoff) == [cand].
	word199 := strings.Repeat("abc", 66) + "a"
	word200 := word199 + "b"
	// A match that has to be found through a popular element: p and q break the alignment on both
	// sides of the run of a, which is popular from 4 occurrences on in a word of 200 characters.
	three1, three2 := run(0x4e00, 98), run(0x4e00+98, 97)
	four1, four2 := run(0x4e00, 97), run(0x4e00+97, 97)
	// A run of a popular element left of a matched block: found by extending that block to the left.
	left := strings.Repeat("a", 60) + run(0x4e00, 140)
	for _, c := range []struct {
		name       string
		word, cand string
		cutoff     float64
		matches    bool
	}{
		// ratio 0.9975 without autojunk for both words
		{"199 characters are compared in full", word199, "x" + word199, 0.7, true},
		{"200 characters drop their popular elements", word200, "x" + word200, 0.7, false},
		// ratio 0.995, 0.6965 without the extension to the left
		{"popular run extends a block to the left", left, "xy" + left, 0.7, true},
		// ratio 0.99, 0.975 if the 3 occurrences of a were popular
		{"n//100+1 occurrences are not popular",
			three1 + "b" + "aaa" + "c" + three2, three1 + "p" + "aaa" + "q" + three2, 0.99, true},
		// ratio 0.97, 0.99 if the 4 occurrences of a were not popular
		{"n//100+2 occurrences are popular",
			four1 + "b" + "aaaa" + "c" + four2, four1 + "p" + "aaaa" + "q" + four2, 0.975, false},
	} {
		t.Run(c.name, func(t *testing.T) {
			got := rank.CloseMatches(c.word, []string{c.cand}, 3, c.cutoff)
			if matches := len(got) == 1; matches != c.matches {
				t.Errorf("matches = %v, want %v", matches, c.matches)
			}
		})
	}
}

// Python raises ValueError("n must be > 0") for n <= 0; the port returns an empty list instead
// (its one caller passes 5). Not a Python reference value: this pins the documented deviation.
func TestCloseMatchesNonPositiveN(t *testing.T) {
	for _, n := range []int{0, -1} {
		if got := rank.CloseMatches("appel", []string{"apple"}, n, 0.6); got == nil || len(got) != 0 {
			t.Errorf("CloseMatches(n %d) = %q, want an empty list", n, got)
		}
	}
}

func TestZeroHitSuggestions(t *testing.T) {
	// Python reference: find._zero_hit_suggestions(root, query, limit) with the tag list stubbed;
	// the terms are okf.fts.tokenize(query). The result is an empty list, never nil, for no match.
	for _, c := range []struct {
		name  string
		query string
		limit int
		tags  []string
		want  []string
	}{
		{
			name: "one misspelt term", query: "dokcer", limit: 5,
			tags: tags,
			want: []string{"docker"},
		},
		{
			name: "terms in order, each tag once", query: "embeding semantik tagvect", limit: 5,
			tags: tags,
			want: []string{"embedding", "semantic", "tagvec", "tag-vectors"},
		},
		{
			name: "two terms near the same tag", query: "tagvect tagvec", limit: 5,
			tags: tags,
			want: []string{"tagvec", "tag-vectors"},
		},
		{
			name: "limit cuts the collected list", query: "semantik golng gitt", limit: 2,
			tags: tags,
			want: []string{"semantic", "golang"},
		},
		{
			name: "limit of one", query: "semantik golng gitt", limit: 1,
			tags: tags,
			want: []string{"semantic"},
		},
		{
			name: "every term misses", query: "postgres kubernetes", limit: 5,
			tags: tags,
			want: []string{},
		},
		{
			name: "empty query", query: "", limit: 5,
			tags: tags,
			want: []string{},
		},
		{
			name: "query without word characters", query: "?! -_-", limit: 5,
			tags: tags,
			want: []string{},
		},
		{
			name: "query is tokenised: case and separators", query: "Dokcer-Compose, SEMANTIK_index", limit: 5,
			tags: tags,
			want: []string{"docker", "semantic"},
		},
		{
			name: "no tags registered", query: "docker", limit: 5,
			tags: nil,
			want: []string{},
		},
		{
			name: "more near tags than the limit: equal ratios, string descending", query: "node", limit: 5,
			tags: tags,
			want: []string{"node28", "node26", "node24", "node22", "node20"},
		},
		{
			name: "near tags below the limit", query: "tagz", limit: 5,
			tags: tags,
			want: []string{"tag", "tags"},
		},
		{
			name: "near tags of two terms, deduplicated", query: "tagz testz", limit: 8,
			tags: tags,
			want: []string{"tag", "tags", "test", "tests", "tester", "tested"},
		},
		{
			name: "several near tags, limit 2", query: "tests", limit: 2,
			tags: tags,
			want: []string{"tests", "test"},
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			got := rank.ZeroHitSuggestions(rank.Tokenize(c.query), c.tags, c.limit)
			if got == nil || !slices.Equal(got, c.want) {
				t.Errorf("ZeroHitSuggestions(%q, limit %d) = %q, want %q", c.query, c.limit, got, c.want)
			}
		})
	}
}
