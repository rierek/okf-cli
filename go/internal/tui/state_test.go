package tui

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
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

// settleStart runs the commands Init starts and feeds the root-remembered answer back.
func settleStart(m model) model {
	var run func(cmd tea.Cmd)
	run = func(cmd tea.Cmd) {
		if cmd == nil {
			return
		}
		switch msg := cmd().(type) {
		case tea.BatchMsg:
			for _, c := range msg {
				if _, isCheck := c().(indexCheckedMsg); !isCheck { // checks are not the subject
					run(c)
				}
			}
		case rootRememberedMsg:
			next, _ := m.Update(msg)
			m = next.(model)
		}
	}
	run(m.Init())
	return m
}

// The start root is remembered once it is validated like a typed path: a directory with a
// catalogue is, a directory without one and a missing path are not.
func TestStartRootIsRememberedOnlyWhenValid(t *testing.T) {
	roots := func() []string {
		s, err := loadState()
		if err != nil {
			t.Fatal(err)
		}
		return s.Roots
	}
	stateHome(t)
	catalogue := fixtureRoot(t)
	for _, bad := range []string{t.TempDir(), filepath.Join(t.TempDir(), "nothing")} {
		settleStart(newModel(bad, defaultSettings(), nil))
		if got := roots(); len(got) != 0 {
			t.Fatalf("start root %q was remembered: %v", bad, got)
		}
	}
	settleStart(newModel(catalogue, defaultSettings(), nil))
	if got := roots(); !slices.Equal(got, []string{catalogue}) {
		t.Errorf("roots = %v, want the start root %q", got, catalogue)
	}
}

// A state file that cannot be written shows as a sticky toast, but never replaces another message.
func TestStartRootWriteFailureShowsAToast(t *testing.T) {
	home := stateHome(t)
	if err := os.MkdirAll(filepath.Join(home, "okf"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(home, "okf", "tui.json"), []byte("{"), 0o644); err != nil {
		t.Fatal(err)
	}
	root := fixtureRoot(t)
	m := settleStart(newModel(root, defaultSettings(), nil))
	if m.toast == nil || m.toast.title != "Could not remember the root" || !m.toast.sticky {
		t.Fatalf("toast = %+v, want the sticky remember warning", m.toast)
	}
	m = settleStart(newModel(root, defaultSettings(), errors.New("bad [tui]")))
	if m.toast == nil || m.toast.title != "Invalid [tui] settings, defaults in use" {
		t.Errorf("toast = %+v, want the settings error kept", m.toast)
	}
}
