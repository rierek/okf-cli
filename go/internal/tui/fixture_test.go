package tui

import (
	"os"
	"path/filepath"
	"testing"
)

// fixtureRoot copies the golden fixture catalogue into a temp dir and returns its path.
func fixtureRoot(t *testing.T) string {
	t.Helper()
	dst := filepath.Join(t.TempDir(), "catalogue")
	if err := os.CopyFS(dst, os.DirFS(filepath.Join("..", "..", "..", "tests", "golden", "catalogue"))); err != nil {
		t.Fatal(err)
	}
	return dst
}
