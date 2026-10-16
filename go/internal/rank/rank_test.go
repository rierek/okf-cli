package rank_test

import (
	"fmt"
	"reflect"
	"slices"
	"testing"

	"nas/volume1/data/git/okf-tools/go/internal/rank"
)

// The expected values of these tests are Python reference values: each table was produced by
// running the Python original named at the test (cli/okf/find.py, fts.py, semantic.py) with
// Python 3.14.6 on the same input, and is pinned literally. The tests call the production
// functions; they never recompute a ranking.

func TestTokenize(t *testing.T) {
	// Python reference: okf.fts.tokenize(s).
	for _, c := range []struct {
		name string
		in   string
		want []string
	}{
		{"empty", "", []string{}},
		{"only separators", "  \t\n -_- ", []string{}},
		{"ascii words", "Hello World", []string{"hello", "world"}},
		{"underscore separates", "build_tagvec __init__", []string{"build", "tagvec", "init"}},
		{"hyphen separates", "well-known state-of-the-art", []string{"well", "known", "state", "of", "the", "art"}},
		{"umlauts and sharp s", "Über Straße Café ÄÖÜ", []string{"über", "straße", "café", "äöü"}},
		{"digits", "x2 3d 42 v1.2.3", []string{"x2", "3d", "42", "v1", "2", "3"}},
		{"punctuation", "a+b=c; d/e.f (g) [h] {i}", []string{"a", "b", "c", "d", "e", "f", "g", "h", "i"}},
		{"combining acute splits", "cafe\u0301 e\u0301cole", []string{"cafe", "e", "cole"}},
		{"precomposed stays", "caf\u00e9 \u00e9cole", []string{"caf\u00e9", "\u00e9cole"}},
		{"dotted capital I lowers to i and a combining dot", "\u0130stanbul", []string{"i", "stanbul"}},
		{"final sigma", "ΟΔΥΣΣΕΥΣ ΑΣ", []string{"οδυσσευς", "ας"}},
		{"superscript, fraction and arabic digits", "x² ½ ٣", []string{"x²", "½", "٣"}},
		{"cjk run", "日本語のテスト テスト", []string{"日本語のテスト", "テスト"}},
		{"emoji separates", "ok 👍 ready", []string{"ok", "ready"}},
		{"unicode spaces", "a\u00a0b\u2003c\td\ne", []string{"a", "b", "c", "d", "e"}},
		{"full width", "ＡＢＣ １２", []string{"ａｂｃ", "１２"}},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := rank.Tokenize(c.in); !slices.Equal(got, c.want) {
				t.Errorf("Tokenize(%q) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

func TestCut(t *testing.T) {
	// Python reference: [1, 2, 3, 4, 5][:limit] and [][:limit].
	for _, c := range []struct {
		limit int
		want  []int
	}{
		{-9, []int{}},
		{-5, []int{}},
		{-4, []int{1}},
		{-1, []int{1, 2, 3, 4}},
		{0, []int{}},
		{1, []int{1}},
		{3, []int{1, 2, 3}},
		{5, []int{1, 2, 3, 4, 5}},
		{9, []int{1, 2, 3, 4, 5}},
	} {
		if got := rank.Cut([]int{1, 2, 3, 4, 5}, c.limit); !slices.Equal(got, c.want) {
			t.Errorf("Cut([1 2 3 4 5], %d) = %v, want %v", c.limit, got, c.want)
		}
	}
	for _, c := range []struct {
		limit int
		want  []int
	}{
		{-1, []int{}},
		{0, []int{}},
		{3, []int{}},
	} {
		if got := rank.Cut([]int{}, c.limit); !slices.Equal(got, c.want) {
			t.Errorf("Cut([], %d) = %v, want %v", c.limit, got, c.want)
		}
	}
}

// A cut list has no spare capacity: appending to it must not overwrite the items it was cut from.
func TestCutLeavesTheSourceAlone(t *testing.T) {
	src := []int{1, 2, 3, 4, 5}
	cut := append(rank.Cut(src, 2), 99)
	if !slices.Equal(src, []int{1, 2, 3, 4, 5}) || !slices.Equal(cut, []int{1, 2, 99}) {
		t.Errorf("after append src = %v, cut = %v", src, cut)
	}
}

func TestScoreSubstring(t *testing.T) {
	// Python reference: the score and contrib of the hit find._substring_ranking returns for the
	// concept over a throwaway catalogue of these concepts, query terms = fts.tokenize(query); a
	// concept the Python run does not list has score 0 and three empty term lists.
	for _, c := range []struct {
		name              string
		title, tags, body string
		terms             []string
		score             int
		contrib           rank.Contrib
	}{
		{
			name:  "a-title-only / docker",
			title: "Docker Compose Guide", tags: "ops", body: "\nsetup notes\n",
			terms:   []string{"docker"},
			score:   3,
			contrib: rank.Contrib{Title: []string{"docker"}, Tags: []string{}, Body: []string{}},
		},
		{
			name:  "f-tags-only / docker",
			title: "Other", tags: "docker-compose ops", body: "\nempty\n",
			terms:   []string{"docker"},
			score:   2,
			contrib: rank.Contrib{Title: []string{}, Tags: []string{"docker"}, Body: []string{}},
		},
		{
			name:  "e-body-only / docker",
			title: "Plain", tags: "x", body: "\nmentions docker once, docker twice\n",
			terms:   []string{"docker"},
			score:   1,
			contrib: rank.Contrib{Title: []string{}, Tags: []string{}, Body: []string{"docker"}},
		},
		{
			name:  "g-nomatch / docker",
			title: "Zzz", tags: "zzz", body: "\nzzz\n",
			terms:   []string{"docker"},
			score:   0,
			contrib: rank.Contrib{Title: []string{}, Tags: []string{}, Body: []string{}},
		},
		{
			name:  "b-all-fields / backup",
			title: "Backup strategy", tags: "backup restore", body: "\nHow to backup data safely.\n",
			terms:   []string{"backup"},
			score:   6,
			contrib: rank.Contrib{Title: []string{"backup"}, Tags: []string{"backup"}, Body: []string{"backup"}},
		},
		{
			name:  "d-substring / back",
			title: "Backups", tags: "misc", body: "\nnothing here\n",
			terms:   []string{"back"},
			score:   3,
			contrib: rank.Contrib{Title: []string{"back"}, Tags: []string{}, Body: []string{}},
		},
		{
			name:  "h-multiterm / docker backup",
			title: "Docker basics", tags: "x", body: "\nbackup of volumes\n",
			terms:   []string{"docker", "backup"},
			score:   4,
			contrib: rank.Contrib{Title: []string{"docker"}, Tags: []string{}, Body: []string{"backup"}},
		},
		{
			name:  "b-all-fields / backup backup",
			title: "Backup strategy", tags: "backup restore", body: "\nHow to backup data safely.\n",
			terms:   []string{"backup", "backup"},
			score:   12,
			contrib: rank.Contrib{Title: []string{"backup", "backup"}, Tags: []string{"backup", "backup"}, Body: []string{"backup", "backup"}},
		},
		{
			name:  "c-umlaut / über",
			title: "ÜBER Cloud", tags: "Über", body: "\nüber alles\n",
			terms:   []string{"über"},
			score:   6,
			contrib: rank.Contrib{Title: []string{"über"}, Tags: []string{"über"}, Body: []string{"über"}},
		},
		{
			name:  "i-sharp / C#",
			title: "Notes on C#", tags: "lang", body: "\nc# and F#\n",
			terms:   []string{"c"},
			score:   4,
			contrib: rank.Contrib{Title: []string{"c"}, Tags: []string{}, Body: []string{"c"}},
		},
		{
			name:  "b-all-fields / docker backup",
			title: "Backup strategy", tags: "backup restore", body: "\nHow to backup data safely.\n",
			terms:   []string{"docker", "backup"},
			score:   6,
			contrib: rank.Contrib{Title: []string{"backup"}, Tags: []string{"backup"}, Body: []string{"backup"}},
		},
		{
			name:  "j-caps-body / docker",
			title: "Shout", tags: "x", body: "\nTHE DOCKER DAEMON\n",
			terms:   []string{"docker"},
			score:   1,
			contrib: rank.Contrib{Title: []string{}, Tags: []string{}, Body: []string{"docker"}},
		},
		{
			name:  "k-caps-tags / docker",
			title: "Quiet", tags: "DOCKER Ops", body: "\nnone\n",
			terms:   []string{"docker"},
			score:   2,
			contrib: rank.Contrib{Title: []string{}, Tags: []string{"docker"}, Body: []string{}},
		},
		{
			name:  "k-caps-tags / OPS",
			title: "Quiet", tags: "DOCKER Ops", body: "\nnone\n",
			terms:   []string{"ops"},
			score:   2,
			contrib: rank.Contrib{Title: []string{}, Tags: []string{"ops"}, Body: []string{}},
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			score, contrib := rank.ScoreSubstring(c.title, c.tags, c.body, c.terms)
			if score != c.score {
				t.Errorf("score = %d, want %d", score, c.score)
			}
			// DeepEqual tells an empty list from a nil one: the lists are never nil.
			if !reflect.DeepEqual(contrib, c.contrib) {
				t.Errorf("contrib = %q, want %q", contrib, c.contrib)
			}
		})
	}
}

func paths(hits []*rank.Hit) []string {
	out := []string{}
	for _, h := range hits {
		out = append(out, h.Path)
	}
	return out
}

func TestOrderSubstring(t *testing.T) {
	// Python reference: find._substring_ranking(root, "C#", ["c"], limit, filters) over the
	// concepts of TestScoreSubstring. The catalogue walk yields the hits in path order, the
	// function returns them after `hits.sort(key=lambda h: -h["score"])` cut to `hits[:limit]`.
	for _, c := range []struct {
		limit int
		want  []string
	}{
		{100, []string{"refs/b-all-fields", "refs/d-substring", "refs/h-multiterm", "refs/i-sharp", "refs/a-title-only", "refs/c-umlaut", "refs/f-tags-only", "refs/k-caps-tags", "refs/e-body-only", "refs/j-caps-body"}},
		{3, []string{"refs/b-all-fields", "refs/d-substring", "refs/h-multiterm"}},
		{1, []string{"refs/b-all-fields"}},
		{0, []string{}},
		{-1, []string{"refs/b-all-fields", "refs/d-substring", "refs/h-multiterm", "refs/i-sharp", "refs/a-title-only", "refs/c-umlaut", "refs/f-tags-only", "refs/k-caps-tags", "refs/e-body-only"}},
		{-2, []string{"refs/b-all-fields", "refs/d-substring", "refs/h-multiterm", "refs/i-sharp", "refs/a-title-only", "refs/c-umlaut", "refs/f-tags-only", "refs/k-caps-tags"}},
		{-9, []string{"refs/b-all-fields"}},
		{-10, []string{}},
		{-11, []string{}},
	} {
		hits := []*rank.Hit{
			{Path: "refs/a-title-only", Score: 3},
			{Path: "refs/b-all-fields", Score: 6},
			{Path: "refs/c-umlaut", Score: 3},
			{Path: "refs/d-substring", Score: 5},
			{Path: "refs/e-body-only", Score: 1},
			{Path: "refs/f-tags-only", Score: 2},
			{Path: "refs/h-multiterm", Score: 4},
			{Path: "refs/i-sharp", Score: 4},
			{Path: "refs/j-caps-body", Score: 1},
			{Path: "refs/k-caps-tags", Score: 2},
		}
		if got := paths(rank.OrderSubstring(hits, c.limit)); !slices.Equal(got, c.want) {
			t.Errorf("OrderSubstring(limit %d) = %q, want %q", c.limit, got, c.want)
		}
	}
}

// Thirty hits are past the size where an unstable sort could still look stable by luck.
func TestOrderSubstringKeepsTies(t *testing.T) {
	// Python reference: hits = [{"path": "p%02d" % i, "score": 1 + i * 7 % 4} for i in range(30)];
	// hits.sort(key=lambda h: -h["score"]) -- the paths in sorted order.
	want := []string{
		"p01", "p05", "p09", "p13", "p17", "p21", "p25", "p29", "p02", "p06", "p10", "p14", "p18",
		"p22", "p26", "p03", "p07", "p11", "p15", "p19", "p23", "p27", "p00", "p04", "p08", "p12",
		"p16", "p20", "p24", "p28",
	}
	var hits []*rank.Hit
	for i := range 30 {
		hits = append(hits, &rank.Hit{Path: fmt.Sprintf("p%02d", i), Score: 1 + i*7%4})
	}
	if got := paths(rank.OrderSubstring(hits, 30)); !slices.Equal(got, want) {
		t.Errorf("OrderSubstring = %q, want %q", got, want)
	}
}

func TestNormaliseBM25(t *testing.T) {
	// Python reference: the hit scores of find._rank_lexically for the ranked (path, score) list,
	// i.e. int(round(100 * s / top)) if top else 0, with the index read and the hydration stubbed.
	for _, c := range []struct {
		name   string
		scores []float64
		want   []int
	}{
		{"half to even: 62.5, 63.5, 0.5, 1.5, 2.5", []float64{200.0, 125.0, 127.0, 1.0, 3.0, 5.0}, []int{100, 62, 64, 0, 2, 2}},
		{"100*s then / top, not 100*(s/top)", []float64{0.8, 0.7}, []int{100, 88}},
		{"100*s then / top again", []float64{6.4, 2.4}, []int{100, 38}},
		{"realistic bm25 values", []float64{7.123456, 3.5, 0.0001}, []int{100, 49, 0}},
		{"single hit", []float64{3.7}, []int{100}},
		{"top zero", []float64{0.0, 0.0}, []int{0, 0}},
		{"empty", []float64{}, []int{}},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := rank.NormaliseBM25(c.scores); !slices.Equal(got, c.want) {
				t.Errorf("NormaliseBM25(%v) = %v, want %v", c.scores, got, c.want)
			}
		})
	}
}

func scored(scores []int) []*rank.Hit {
	out := []*rank.Hit{}
	for _, s := range scores {
		out = append(out, &rank.Hit{Score: s})
	}
	return out
}

func TestConfident(t *testing.T) {
	// Python reference: find._keyword_top1_is_confident([{"score": s}, ...]).
	for _, c := range []struct {
		name   string
		scores []int
		want   bool
	}{
		{"no hit", []int{}, false},
		{"single hit", []int{1}, true},
		{"single hit with score 0", []int{0}, true},
		{"exactly 1.5x", []int{6, 4}, true},
		{"just below 1.5x", []int{5, 4}, false},
		{"exactly 1.5x, larger", []int{9, 6}, true},
		{"below 1.5x, larger", []int{8, 6}, false},
		{"far ahead", []int{100, 10}, true},
		{"runner-up zero", []int{3, 0}, true},
		{"top1 zero", []int{0, 0}, false},
		{"top1 negative", []int{-1, -2}, false},
		{"tie", []int{4, 4}, false},
		{"1.5x of 66 is 99", []int{100, 66}, true},
		{"three hits, only the first two count", []int{6, 4, 100}, true},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := rank.Confident(scored(c.scores)); got != c.want {
				t.Errorf("Confident(%v) = %v, want %v", c.scores, got, c.want)
			}
		})
	}
}

type pathScore struct {
	path  string
	score int
}

type fusedHit struct {
	path       string
	score      int
	provenance string
}

func TestFuseConditional(t *testing.T) {
	// Python reference: find.fuse_conditional(lexical, semantic, limit) over hit dicts of path,
	// score and provenance; want lists the fused hits and owned is lexical_owned.
	hits := func(list []pathScore, provenance string) []*rank.Hit {
		out := []*rank.Hit{}
		for _, h := range list {
			out = append(out, &rank.Hit{Path: h.path, Score: h.score, Provenance: provenance})
		}
		return out
	}
	for _, c := range []struct {
		name              string
		limit             int
		lexical, semantic []pathScore
		want              []fusedHit
		owned             bool
	}{
		{
			name: "lexical owns: semantic is appended, a duplicate keeps the lexical entry", limit: 10,
			lexical:  []pathScore{{"c/a", 6}, {"c/b", 2}},
			semantic: []pathScore{{"c/c", 70}, {"c/a", 65}, {"c/d", 60}},
			want:     []fusedHit{{"c/a", 6, "lexical"}, {"c/b", 2, "lexical"}, {"c/c", 70, "semantic"}, {"c/d", 60, "semantic"}}, owned: true,
		},
		{
			name: "semantic owns: its entry wins the duplicate, lexical follows", limit: 10,
			lexical:  []pathScore{{"c/a", 4}, {"c/b", 3}},
			semantic: []pathScore{{"c/c", 70}, {"c/b", 65}, {"c/e", 50}},
			want:     []fusedHit{{"c/c", 70, "semantic"}, {"c/b", 65, "semantic"}, {"c/e", 50, "semantic"}, {"c/a", 4, "lexical"}}, owned: false,
		},
		{
			name: "single lexical hit owns, semantic fills the tail", limit: 3,
			lexical:  []pathScore{{"c/a", 1}},
			semantic: []pathScore{{"c/b", 80}, {"c/c", 70}, {"c/d", 60}},
			want:     []fusedHit{{"c/a", 1, "lexical"}, {"c/b", 80, "semantic"}, {"c/c", 70, "semantic"}}, owned: true,
		},
		{
			name: "limit cuts the fused list", limit: 2,
			lexical:  []pathScore{{"c/a", 4}, {"c/b", 3}},
			semantic: []pathScore{{"c/c", 70}, {"c/b", 65}, {"c/e", 50}},
			want:     []fusedHit{{"c/c", 70, "semantic"}, {"c/b", 65, "semantic"}}, owned: false,
		},
		{
			name: "limit zero", limit: 0,
			lexical:  []pathScore{{"c/a", 6}, {"c/b", 2}},
			semantic: []pathScore{{"c/c", 70}},
			want:     []fusedHit{}, owned: true,
		},
		{
			name: "both empty", limit: 10,
			lexical:  []pathScore{},
			semantic: []pathScore{},
			want:     []fusedHit{}, owned: false,
		},
		{
			name: "no lexical hits", limit: 10,
			lexical:  []pathScore{},
			semantic: []pathScore{{"c/x", 90}, {"c/y", 80}},
			want:     []fusedHit{{"c/x", 90, "semantic"}, {"c/y", 80, "semantic"}}, owned: false,
		},
		{
			name: "no semantic hits, lexical without margin", limit: 10,
			lexical:  []pathScore{{"c/a", 4}, {"c/b", 3}},
			semantic: []pathScore{},
			want:     []fusedHit{{"c/a", 4, "lexical"}, {"c/b", 3, "lexical"}}, owned: false,
		},
		{
			name: "a path twice in the owning list keeps the first", limit: 10,
			lexical:  []pathScore{{"c/a", 6}, {"c/a", 1}},
			semantic: []pathScore{{"c/b", 50}},
			want:     []fusedHit{{"c/a", 6, "lexical"}, {"c/b", 50, "semantic"}}, owned: true,
		},
		{
			name: "negative limit drops from the end", limit: -1,
			lexical:  []pathScore{{"c/a", 4}, {"c/b", 3}},
			semantic: []pathScore{{"c/c", 70}, {"c/b", 65}, {"c/e", 50}},
			want:     []fusedHit{{"c/c", 70, "semantic"}, {"c/b", 65, "semantic"}, {"c/e", 50, "semantic"}}, owned: false,
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			fused, owned := rank.FuseConditional(hits(c.lexical, "lexical"), hits(c.semantic, "semantic"), c.limit)
			got := []fusedHit{}
			for _, h := range fused {
				got = append(got, fusedHit{h.Path, h.Score, h.Provenance})
			}
			if !slices.Equal(got, c.want) || owned != c.owned {
				t.Errorf("FuseConditional = %v, %v; want %v, %v", got, owned, c.want, c.owned)
			}
		})
	}
}
