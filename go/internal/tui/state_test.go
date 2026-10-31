package tui

import (
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

// The state file keeps the roots most recent first, without duplicates and capped. A corrupt file
// is an error that names its path, and it is not overwritten.
func TestStateFileRemembersRoots(t *testing.T) {
	home := stateHome(t)
	for i := range maxRememberedRoots + 2 {
		if err := rememberRoot(fmt.Sprintf("/r%d", i)); err != nil {
			t.Fatal(err)
		}
	}
	if err := rememberRoot("/r5"); err != nil {
		t.Fatal(err)
	}
	s, err := loadState()
	if err != nil {
		t.Fatal(err)
	}
	if len(s.Roots) != maxRememberedRoots || s.Roots[0] != "/r5" || s.Roots[1] != "/r21" || slices.Contains(s.Roots[1:], "/r5") {
		t.Errorf("roots = %v, want /r5 first, then the newest, %d at most, no duplicate", s.Roots, maxRememberedRoots)
	}

	path := filepath.Join(home, "okf", "tui.json")
	if err := os.WriteFile(path, []byte("{"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := loadState(); err == nil || !strings.Contains(err.Error(), path) {
		t.Errorf("corrupt state file: err = %v, want one naming %s", err, path)
	}
	if err := rememberRoot("/r0"); err == nil {
		t.Error("remembering a root into a corrupt state file did not fail")
	}
	if data, _ := os.ReadFile(path); string(data) != "{" {
		t.Errorf("the corrupt state file was overwritten: %q", data)
	}
}
