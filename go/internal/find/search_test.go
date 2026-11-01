package find

import (
	"os"
	"path/filepath"
	"slices"
	"sync"
	"testing"
)

func fixtureRoot(t *testing.T) string {
	t.Helper()
	dst := filepath.Join(t.TempDir(), "catalogue")
	if err := os.CopyFS(dst, os.DirFS(filepath.Join("..", "..", "..", "tests", "golden", "catalogue"))); err != nil {
		t.Fatal(err)
	}
	return dst
}

// Warnings belong to one call: a search on a root without indexes emits the same notes every
// time, also when searches run at once, and the notes of one call never show up in another.
func TestSearchWarningsPerCall(t *testing.T) {
	t.Setenv("VOYAGE_API_KEY", "")
	root := fixtureRoot(t)
	first, err := Search(root, Options{Query: "deploy", Limit: 50})
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Warnings) == 0 {
		t.Fatal("fixture has no index: want the lexical-index note")
	}
	var wg sync.WaitGroup
	results := make([]*Result, 4)
	for i := range results {
		wg.Add(1)
		go func() {
			defer wg.Done()
			results[i], _ = Search(root, Options{Query: "deploy", Limit: 50})
		}()
	}
	wg.Wait()
	for i, r := range results {
		if r == nil || !slices.Equal(r.Warnings, first.Warnings) {
			t.Errorf("call %d warnings = %v, want %v", i, r.Warnings, first.Warnings)
		}
	}
	// A query without a term is answered before any arm runs: no note at all.
	empty, err := Search(root, Options{Query: "!!", Limit: 50})
	if err != nil || !empty.Empty || len(empty.Warnings) != 0 || len(empty.Hits) != 0 {
		t.Errorf("empty query: result %+v, err %v; want Empty and no warnings", empty, err)
	}
}

// A hit carries what a screen shows: the absolute path is <root>/<path>.md, the bundle is the
// first path segment.
func TestSearchHitFields(t *testing.T) {
	t.Setenv("VOYAGE_API_KEY", "")
	root := fixtureRoot(t)
	r, err := Search(root, Options{Query: "deploy", Limit: 50})
	if err != nil || len(r.Hits) == 0 {
		t.Fatalf("hits = %d, err %v; want hits", len(r.Hits), err)
	}
	for _, h := range r.Hits {
		if want := filepath.Join(root, h.Path+".md"); h.Abs != want {
			t.Errorf("Abs = %q, want %q", h.Abs, want)
		}
		if want := h.Path[:len(h.Bundle)]; h.Bundle != want || h.Path[len(h.Bundle)] != '/' {
			t.Errorf("Bundle = %q of path %q", h.Bundle, h.Path)
		}
		if h.Title == "" || h.Tier == "" {
			t.Errorf("hit %+v lacks title or tier", h)
		}
	}
}
