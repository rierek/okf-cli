package fts

import (
	"os"
	"path/filepath"
	"slices"
	"testing"

	"nas/volume1/data/git/okf-tools/go/internal/rank"
	"nas/volume1/data/git/okf-tools/go/internal/where"
)

// indexed writes the given concepts (path -> file text) under a temp root and builds its index.
func indexed(t *testing.T, files map[string]string) string {
	t.Helper()
	root := t.TempDir()
	for name, text := range files {
		path := filepath.Join(root, name)
		if err := os.MkdirAll(filepath.Dir(path), 0o777); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(text), 0o666); err != nil {
			t.Fatal(err)
		}
	}
	if _, _, err := Build(root, false); err != nil {
		t.Fatal(err)
	}
	return root
}

func ranked(t *testing.T, root, query string) []Row {
	t.Helper()
	filters, err := where.CompileWhere(nil, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	rows, ok, err := Ranking(root, query, 10, filters, false)
	if err != nil || !ok {
		t.Fatalf("Ranking: ok=%v err=%v", ok, err)
	}
	return rows
}

// Equal BM25 scores order by path, whatever the insertion order was (`ORDER BY r, path`). The
// file in the bundle root is walked, and so inserted, before the one in the subdirectory, yet its
// path sorts after it. Python reference: the same catalogue indexed and queried by okf-cli.py
// gives b/a/y before b/z with identical scores.
func TestRankingTiesBreakByPath(t *testing.T) {
	same := "---\ntype: Note\ntitle: Same\n---\nsoup of the day\n"
	root := indexed(t, map[string]string{"b/z.md": same, "b/a/y.md": same})
	rows := ranked(t, root, "soup")
	if len(rows) != 2 || rows[0].Path != "b/a/y" || rows[1].Path != "b/z" {
		t.Fatalf("rows = %+v, want b/a/y then b/z", rows)
	}
	if rows[0].Score != rows[1].Score || rows[0].Score <= 0 {
		t.Fatalf("scores %v and %v, want equal and positive", rows[0].Score, rows[1].Score)
	}
}

// The column weights are title 3, tags 2, body 1: the same term ranks the title hit before the
// tag hit before the body hit (Python reference order, same catalogue).
func TestRankingWeightsTitleOverTagsOverBody(t *testing.T) {
	root := indexed(t, map[string]string{
		"b/inbody.md":  "---\ntype: Note\ntitle: Other one\n---\nsoup\n",
		"b/intags.md":  "---\ntype: Note\ntitle: Other two\ntags: [soup]\n---\nplain\n",
		"b/intitle.md": "---\ntype: Note\ntitle: Soup\n---\nplain\n",
	})
	rows := ranked(t, root, "soup")
	var got []string
	var raw []float64
	for _, r := range rows {
		got = append(got, r.Path)
		raw = append(raw, r.Score)
	}
	want := []string{"b/intitle", "b/intags", "b/inbody"}
	if !slices.Equal(got, want) {
		t.Fatalf("paths = %v, want %v", got, want)
	}
	// 100, 74, 59: the normalised scores okf-cli.py prints under --breakdown for this catalogue,
	// which also pins the raw bm25 values of this SQLite against the one Python links.
	if scores := rank.NormaliseBM25(raw); !slices.Equal(scores, []int{100, 74, 59}) {
		t.Fatalf("normalised scores = %v, want [100 74 59]", scores)
	}
}

// A term matches as a prefix and is stemmed, and a diacritic folds: `soups` finds `soup`,
// `cafe` finds `Café` (tokenizer porter unicode61 remove_diacritics 2).
func TestRankingStemsAndFolds(t *testing.T) {
	root := indexed(t, map[string]string{
		"b/one.md": "---\ntype: Note\ntitle: One\n---\nsoup\n",
		"b/two.md": "---\ntype: Note\ntitle: Café\n---\nplain\n",
	})
	if rows := ranked(t, root, "soups"); len(rows) != 1 || rows[0].Path != "b/one" {
		t.Fatalf("soups: %+v", rows)
	}
	if rows := ranked(t, root, "cafe"); len(rows) != 1 || rows[0].Path != "b/two" {
		t.Fatalf("cafe: %+v", rows)
	}
}
