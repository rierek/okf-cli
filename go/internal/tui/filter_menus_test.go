package tui

import (
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

const (
	longBundle = "an-extremely-long-bundle-name-that-certainly-exceeds-the-old-forty-four-column-modal"
	longTag    = "a-really-long-tag-name-for-wrapping-checks-in-the-menu-box-yes-very-long"
)

// longRoot is the golden fixture plus a bundle with a long name whose concept carries a long tag
// and the tag zebra-tag.
func longRoot(t *testing.T) string {
	t.Helper()
	root := fixtureRoot(t)
	dir := filepath.Join(root, longBundle)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	page := "---\ntype: Rule\ntitle: Long\ndescription: long bundle\ntags:\n  - zebra-tag\n  - " + longTag + "\n---\n\n# Long\n"
	if err := os.WriteFile(filepath.Join(dir, "long.md"), []byte(page), 0o644); err != nil {
		t.Fatal(err)
	}
	return root
}

func modelOn(t *testing.T, root string, w, h int) model {
	t.Helper()
	t.Setenv("VOYAGE_API_KEY", "")
	next, _ := newModel(root, defaultSettings(), nil).Update(tea.WindowSizeMsg{Width: w, Height: h})
	return next.(model)
}

// openMenu opens the value menu of field from the list.
func openMenu(t *testing.T, m model, field filterField) model {
	t.Helper()
	m, _ = press(m, "esc", "f")
	for range int(field) {
		m, _ = press(m, "l")
	}
	m, _ = press(m, "enter")
	if m.overlay != overlayFilterMenu {
		t.Fatalf("field %v: overlay = %v, want its menu", field, m.overlay)
	}
	return m
}

// lineWith is the screen line that holds s, "" when none does.
func lineWith(view, s string) string {
	for _, l := range strings.Split(view, "\n") {
		if strings.Contains(l, s) {
			return l
		}
	}
	return ""
}

// EARS 1: the box fits its longest option, so the name is on one line; on a narrow terminal the
// name ends in an ellipsis and does not wrap.
func TestFilterMenuFitsTheLongestOption(t *testing.T) {
	stateHome(t)
	root := longRoot(t)
	wide := openMenu(t, modelOn(t, root, 200, 40), fieldBundle)
	if lineWith(wide.View(), longBundle) == "" {
		t.Errorf("the long bundle name is not on one line:\n%s", wide.View())
	}
	if w, want := lipgloss.Width(wide.filterMenuBox()), len(longBundle)+6+4; w != want {
		t.Errorf("box width = %d, want the longest option plus chrome = %d", w, want)
	}
	// A menu of short options stays narrow.
	if w := lipgloss.Width(openMenu(t, modelOn(t, root, 200, 40), fieldStatus).filterMenuBox()); w >= 60 {
		t.Errorf("status menu width = %d, want a narrow box", w)
	}

	narrow := openMenu(t, modelOn(t, root, 60, 40), fieldBundle)
	box := narrow.filterMenuBox()
	if w := lipgloss.Width(box); w > 58 {
		t.Errorf("box width = %d on 60 columns, want at most the terminal width minus margin", w)
	}
	row := lineWith(narrow.View(), "an-extremely")
	if !strings.Contains(row, "…") || strings.Contains(narrow.View(), "column-modal") {
		t.Errorf("a long option is not cut with an ellipsis:\n%s", narrow.View())
	}
	if got := strings.Count(box, "\n"); got > 10 { // title, hint and five rows plus frame: no wrapped row
		t.Errorf("box has %d lines, want an unwrapped menu of 4 bundles:\n%s", got+1, box)
	}
}

// EARS 2: / shows a query line and lists the fuzzy matches; esc clears, a second esc closes.
func TestFilterMenuSlashNarrowsTheList(t *testing.T) {
	stateHome(t)
	m := openMenu(t, modelOn(t, longRoot(t), 200, 40), fieldTag)
	all := len(m.filters.visible())
	if all < 3 {
		t.Fatalf("tag menu = %v, want the fixture tags", m.filters.options[fieldTag])
	}
	m, _ = press(m, "/", "zbra")
	if got := m.filters.visible(); !slices.Equal(got, []string{"zebra-tag"}) {
		t.Errorf("tags matching zbra = %v, want [zebra-tag]", got)
	}
	view := m.View()
	if lineWith(view, "/ zbra") == "" || lineWith(view, "zebra-tag") == "" || strings.Contains(view, "food") {
		t.Errorf("the menu shows no query line or does not list only the matches:\n%s", view)
	}
	// Letters that are keys elsewhere (x, k, X, space) type into the query.
	m, _ = press(m, "x", "k", "X", " ")
	if got := m.filters.search.query; got != "zbraxkX " || len(m.filters.selected[fieldTag]) != 0 {
		t.Errorf("query = %q, tags = %v; want the keys typed, nothing chosen", got, m.filters.selected[fieldTag])
	}
	m, _ = press(m, "esc")
	if m.filters.search.query != "" || m.overlay != overlayFilterMenu || len(m.filters.visible()) != all {
		t.Errorf("first esc: query = %q, overlay = %v, visible = %d; want a cleared query in the open menu", m.filters.search.query, m.overlay, len(m.filters.visible()))
	}
	m, _ = press(m, "/", "zebra", "enter", "esc")
	if m.filters.search.query != "" || m.overlay != overlayFilterMenu {
		t.Errorf("esc on a kept query: query = %q, overlay = %v; want it cleared, menu open", m.filters.search.query, m.overlay)
	}
	if m, _ = press(m, "esc"); m.overlay != overlayNone {
		t.Errorf("second esc: overlay = %v, want the menu closed", m.overlay)
	}
}

// EARS 3: in the filtered list space, x and enter flip the option under the cursor.
func TestFilterMenuTogglesTheFilteredOption(t *testing.T) {
	stateHome(t)
	for _, k := range []string{" ", "x", "enter"} {
		m := openMenu(t, modelOn(t, longRoot(t), 200, 40), fieldTag)
		if m.filters.options[fieldTag][0] == "zebra-tag" {
			t.Fatal("the test needs zebra-tag not first in the menu")
		}
		m, _ = press(m, "/", "zebra", "enter", k)
		if got := m.filters.selected[fieldTag]; !slices.Equal(got, []string{"zebra-tag"}) {
			t.Errorf("%q in the filtered menu chose %v, want [zebra-tag]", k, got)
		}
		m, _ = press(m, k)
		if got := m.filters.selected[fieldTag]; len(got) != 0 {
			t.Errorf("%q twice left %v, want the choice flipped back", k, got)
		}
	}
	// With no match nothing happens and nothing panics.
	m := openMenu(t, modelOn(t, longRoot(t), 200, 40), fieldTag)
	m, _ = press(m, "/", "qqqqqq", "enter", " ", "enter", "x")
	if len(m.filters.selected[fieldTag]) != 0 {
		t.Errorf("a menu without a match chose %v", m.filters.selected[fieldTag])
	}
	// The cursor walks the filtered list.
	m = openMenu(t, modelOn(t, longRoot(t), 200, 40), fieldTag)
	m, _ = press(m, "/", "tag", "enter", "j", " ")
	vis := m.filters.visible()
	if len(vis) < 2 || !slices.Equal(m.filters.selected[fieldTag], []string{vis[1]}) {
		t.Errorf("j then space chose %v, want the second match of %v", m.filters.selected[fieldTag], vis)
	}
}

// EARS 4: space picks the root under the cursor as enter does, / narrows the roots, and in the
// path field space and / type.
func TestRootMenuSpaceSelectsAndSlashNarrows(t *testing.T) {
	stateHome(t)
	configured := filepath.Join(t.TempDir(), "zqxv-root")
	if err := os.CopyFS(configured, os.DirFS(filepath.Join("..", "..", "..", "tests", "golden", "catalogue"))); err != nil {
		t.Fatal(err)
	}
	writeConfig(t, "root = \""+configured+"\"\n")
	m := onFixture(t, 250, 40)
	menu, _ := press(m, "esc", "f", "enter")
	i := slices.Index(menu.rootMenu.roots, configured)
	if i < 0 {
		t.Fatalf("root menu = %v, lacks the configured root", menu.rootMenu.roots)
	}
	for range i {
		menu, _ = pressKey(menu, tea.KeyDown)
	}
	picked, _ := press(menu, " ")
	if picked.root != configured || picked.overlay != overlayNone {
		t.Errorf("space: root = %q, overlay = %v; want %q chosen", picked.root, picked.overlay, configured)
	}

	// / narrows the list; the cursor starts on the first match.
	narrowed, _ := press(menu, "/", "zqxv")
	if got := narrowed.rootMenu.visible(); !slices.Equal(got, []string{configured}) {
		t.Errorf("roots matching the configured one = %v, want only it", got)
	}
	if view := narrowed.View(); lineWith(view, "/ "+"zqxv") == "" {
		t.Errorf("the root menu shows no query line:\n%s", view)
	}
	narrowed, _ = press(narrowed, "enter", " ")
	if narrowed.root != configured {
		t.Errorf("space on the filtered list: root = %q, want %q", narrowed.root, configured)
	}
	if cleared, _ := press(menu, "/", "zzz", "esc"); cleared.overlay != overlayRoot || cleared.rootMenu.search.query != "" {
		t.Errorf("esc on a query: overlay = %v, query = %q; want it cleared, menu open", cleared.overlay, cleared.rootMenu.search.query)
	}

	// In the path field space and / are text.
	field, _ := press(m, "esc", "f", "enter")
	for range len(field.rootMenu.roots) {
		field, _ = pressKey(field, tea.KeyDown)
	}
	field, _ = press(field, "/", " ", "a")
	if got := field.rootMenu.input.Value(); got != "/ a" || field.overlay != overlayRoot {
		t.Errorf("path field = %q, overlay = %v; want the keys typed", got, field.overlay)
	}
}
