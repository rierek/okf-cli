package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestGenerate(t *testing.T) {
	out := t.TempDir()
	write := func(rel, text string) {
		t.Helper()
		p := filepath.Join(out, rel)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write("okf-gone.md", "stale")
	write("index.mdx", "hand-written")
	write("_supplements/_okf_find.md", "\nSUPPLEMENT TEXT\n")

	if err := generate(out); err != nil {
		t.Fatal(err)
	}
	exists := func(rel string) bool {
		_, err := os.Stat(filepath.Join(out, rel))
		return err == nil
	}
	if exists("okf-gone.md") {
		t.Error("stale okf-gone.md was not removed")
	}
	if !exists("index.mdx") {
		t.Error("hand-written index.mdx was removed")
	}
	if exists("okf-build-tagvec.md") {
		t.Error("hidden command build-tagvec got a page")
	}
	if !exists("okf-ctx-show.md") {
		t.Error("verb page okf-ctx-show.md is missing")
	}
	find, err := os.ReadFile(filepath.Join(out, "okf-find.md"))
	if err != nil {
		t.Fatal(err)
	}
	supplement, usage := strings.Index(string(find), "SUPPLEMENT TEXT"), strings.Index(string(find), "## Usage")
	if supplement < 0 || usage < 0 || supplement > usage {
		t.Errorf("okf-find.md: supplement at %d, usage at %d; want supplement before usage", supplement, usage)
	}
}
