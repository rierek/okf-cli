package tui

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

// US 1, criterion 2: a long root shortens to its tail, the header stays one line and keeps the
// dots and the hints; the frame keeps the terminal height.
func TestHeaderStaysOneLineWithALongRoot(t *testing.T) {
	roots := map[string]string{ // root: text that must stay at its end
		"/Users/erik/.cache/okf-po/run/suche-latte/catalogue/with/a/very/long/tail/of/directories": "directories",
	}
	for _, pad := range []string{"", "a", "ab", "abc"} {
		roots["/Users/erik/"+strings.Repeat("日本語", 30)+pad+"/日本"] = "日本"
	}
	for root, tail := range roots {
		for _, w := range []int{100, 101, 120, 121, 140} {
			m := newModel(root, defaultSettings(), nil)
			next, _ := m.Update(tea.WindowSizeMsg{Width: w, Height: 30})
			lines := strings.Split(next.(model).View(), "\n")
			if len(lines) != 30 {
				t.Errorf("width %d: frame is %d rows high, want 30", w, len(lines))
			}
			head := strings.ReplaceAll(lines[1], "\u00a0", " ")
			for _, want := range []string{"> …", tail, "lexical ", "semantic ", "buffer 0", "f1 help", "ctrl+c quit now"} {
				if !strings.Contains(head, want) {
					t.Errorf("width %d: header row %q lacks %q", w, head, want)
				}
			}
			if strings.Contains(lines[2], "lexical") || strings.Contains(lines[2], "f1\u00a0help") {
				t.Errorf("width %d: header runs into a second row: %q", w, lines[2])
			}
		}
	}
}

// US 2, criterion 3: a root under two spellings (a symlink) is listed once, under the first.
func TestRootMenuListsOneDirectoryOnce(t *testing.T) {
	stateHome(t)
	real := fixtureRoot(t)
	link := filepath.Join(t.TempDir(), "link")
	if err := os.Symlink(real, link); err != nil {
		t.Fatal(err)
	}
	writeConfig(t, "root = \""+link+"\"\n")

	m := newModel(real, defaultSettings(), nil)
	next, _ := m.Update(tea.WindowSizeMsg{Width: 250, Height: 40})
	menu, _ := press(next.(model), "esc", "f", "enter")
	if got := menu.rootMenu.roots; len(got) != 1 || got[0] != real {
		t.Errorf("root menu = %v, want only %q", got, real)
	}
}
