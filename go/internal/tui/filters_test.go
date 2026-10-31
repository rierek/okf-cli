package tui

import (
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

// choose opens the menu of field from the list, flips the values and closes the menu with esc;
// cmd is the search the closing starts.
func choose(t *testing.T, m model, field filterField, values ...string) (model, tea.Cmd) {
	t.Helper()
	if m.inInput() {
		m, _ = press(m, "esc")
	}
	m, _ = press(m, "f")
	for range int(field) {
		m, _ = press(m, "l")
	}
	m, _ = press(m, "enter")
	if m.overlay != overlayFilterMenu {
		t.Fatalf("enter on field %v: overlay = %v, want its value menu", field, m.overlay)
	}
	for _, v := range values {
		i := slices.Index(m.filters.options[field], v)
		if i < 0 {
			t.Fatalf("the %v menu offers %v, not %q", field, m.filters.options[field], v)
		}
		for m.filters.cursor < i {
			m, _ = pressKey(m, tea.KeyDown)
		}
		for m.filters.cursor > i {
			m, _ = pressKey(m, tea.KeyUp)
		}
		m, _ = press(m, " ")
	}
	return pressKey(m, tea.KeyEsc)
}

// switchTo opens the root menu from the list and enters path in its path field.
func switchTo(t *testing.T, m model, path string) (model, tea.Cmd) {
	t.Helper()
	if m.inInput() {
		m, _ = press(m, "esc")
	}
	m, _ = press(m, "f", "enter")
	if m.overlay != overlayRoot {
		t.Fatalf("enter on the root field: overlay = %v, want the root menu", m.overlay)
	}
	for range len(m.rootMenu.roots) {
		m, _ = pressKey(m, tea.KeyDown)
	}
	m, _ = press(m, path)
	return pressKey(m, tea.KeyEnter)
}

// stateHome points the TUI state file at a fresh directory.
func stateHome(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("XDG_STATE_HOME", dir)
	return dir
}

// US 2, criterion 1: bundle B and type T return the hits of okf find with the same --where.
func TestBundleAndTypeReturnTheHitsOfOkfFindWhere(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 200, 40)
	cases := []struct{ query, bundle, typ string }{
		{"deploy", "handbook", "Runbook"},
		{"the", "handbook", "Concept"},
		{"the", "recipes", "Recipe"},
		{"ops incident", "handbook", "Note"},
	}
	nonEmpty := 0
	for _, c := range cases {
		_, done := search(t, m, c.query)
		var cmd tea.Cmd
		done, _ = choose(t, done, fieldBundle, c.bundle)
		done, cmd = choose(t, done, fieldType, c.typ)
		done = settle(t, done, cmd)
		want := cliPaths(t, m.root, c.query, "--where", "path ~ "+c.bundle+"/ and type = "+c.typ)
		if got := hitPaths(done); !slices.Equal(got, want) {
			t.Errorf("%+v: hits = %v, want those of okf find --where: %v", c, got, want)
		}
		if len(want) > 0 {
			nonEmpty++
		}
	}
	if nonEmpty < 3 {
		t.Errorf("only %d of the cases have hits: the comparison proves too little", nonEmpty)
	}
}

// A choice reruns the search of the query field's last run; the screen shows the choice.
func TestChoiceRerunsTheSearchAndShowsTheFilter(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 200, 40)
	_, done := search(t, m, "the")
	all := hitPaths(done)
	filtered, cmd := choose(t, done, fieldType, "Recipe")
	if filtered.overlay != overlayNone || cmd == nil {
		t.Fatalf("closing the menu: overlay = %v, cmd = %v; want a rerun", filtered.overlay, cmd)
	}
	filtered = settle(t, filtered, cmd)
	if got := hitPaths(filtered); len(got) == 0 || len(got) >= len(all) {
		t.Errorf("hits with type Recipe = %v, want fewer than the %d unfiltered", got, len(all))
	}
	if !strings.Contains(filtered.View(), "Recipe") {
		t.Errorf("the screen does not show the active filter:\n%s", filtered.View())
	}
	// Closing a menu without a change does not search again.
	if _, cmd := choose(t, filtered, fieldType); cmd != nil {
		t.Errorf("a menu closed without a change started a search")
	}
}

// US 2, criterion 2: two values of one field are ORed; the fields stay ANDed.
func TestTwoValuesOfOneFieldAreOred(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 200, 40)
	_, done := search(t, m, "the")
	var cmd tea.Cmd
	done, cmd = choose(t, done, fieldType, "Recipe", "Runbook")
	if got, want := done.filters.exprText(), "(type = Recipe or type = Runbook)"; got != want {
		t.Errorf("expression = %q, want %q", got, want)
	}
	done = settle(t, done, cmd)
	want := cliPaths(t, m.root, "the", "--where", "type = Recipe or type = Runbook")
	got := hitPaths(done)
	if !slices.Equal(got, want) {
		t.Errorf("hits = %v, want those of okf find --where 'type = Recipe or type = Runbook': %v", got, want)
	}
	recipe := cliPaths(t, m.root, "the", "--where", "type = Recipe")
	runbook := cliPaths(t, m.root, "the", "--where", "type = Runbook")
	if len(recipe) == 0 || len(runbook) == 0 || len(got) != len(recipe)+len(runbook) {
		t.Errorf("or must give the union: %d Recipe + %d Runbook hits, got %d", len(recipe), len(runbook), len(got))
	}
	// Fields are ANDed: a bundle narrows the union.
	done, cmd = choose(t, done, fieldBundle, "recipes")
	done = settle(t, done, cmd)
	want = cliPaths(t, m.root, "the", "--where", "path ~ recipes/ and (type = Recipe or type = Runbook)")
	if got := hitPaths(done); !slices.Equal(got, want) || len(want) != len(recipe) {
		t.Errorf("hits with bundle and two types = %v, want %v (the %d Recipe hits)", got, want, len(recipe))
	}
}

// The status, tier and tag fields filter like the others.
func TestStatusTierAndTagFilter(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 200, 40)
	_, done := search(t, m, "the")
	for _, c := range []struct {
		field filterField
		value string
		where string
	}{
		{fieldTag, "food", "tag = food"},
		{fieldStatus, "deprecated", "status = deprecated"},
		{fieldTier, "human-reviewed", "tier = human-reviewed"},
	} {
		filtered, cmd := choose(t, done, c.field, c.value)
		filtered = settle(t, filtered, cmd)
		if got, want := hitPaths(filtered), cliPaths(t, m.root, "the", "--where", c.where); !slices.Equal(got, want) {
			t.Errorf("%s: hits = %v, want %v", c.where, got, want)
		}
	}
}

// US 2, criterion 3: another root reruns the current query there and shows in the header.
func TestOtherRootRerunsTheQueryAndShowsInTheHeader(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 250, 40)
	other := fixtureRoot(t)
	if err := os.Remove(filepath.Join(other, "handbook", "ops", "deploy.md")); err != nil {
		t.Fatal(err)
	}
	_, done := search(t, m, "deploy")
	before := hitPaths(done)
	next, cmd := switchTo(t, done, other)
	if next.root != other || next.overlay != overlayNone {
		t.Fatalf("root = %q, overlay = %v; want %q and no overlay", next.root, next.overlay, other)
	}
	if !strings.Contains(strings.SplitN(next.View(), "\n", 3)[1], other) {
		t.Errorf("the header does not show the new root %q:\n%s", other, next.View())
	}
	next = settle(t, next, cmd)
	want := cliPaths(t, other, "deploy")
	if got := hitPaths(next); !slices.Equal(got, want) || slices.Equal(got, before) {
		t.Errorf("hits on the new root = %v, want %v (not the old root's %v)", got, want, before)
	}
}

// A root switch drops the list of the old root even when no query ran there.
func TestRootSwitchWithoutQueryRunsNothing(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 250, 40)
	next, cmd := switchTo(t, m, fixtureRoot(t))
	next = settle(t, next, cmd)
	if next.search.running || next.search.ran || len(next.search.hits) != 0 {
		t.Errorf("a root switch without a query started a search: %+v", next.search)
	}
}

// A root switch while a search runs keeps the running indicator ticking.
func TestRootSwitchDuringASearchKeepsTheSpinner(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 250, 40)
	running, _ := press(m, "deploy", "enter")
	if !running.search.running {
		t.Fatal("no search runs")
	}
	tick := running.search.spinner.Tick()
	next, _ := switchTo(t, running, fixtureRoot(t))
	if _, cmd := next.Update(tick); cmd == nil {
		t.Error("the tick chain of the running search ends at the root switch: the spinner freezes")
	}
}

// US 2, criterion 4: the root menu offers the configured root and the roots of earlier sessions.
func TestRootMenuOffersConfiguredAndRememberedRoots(t *testing.T) {
	stateHome(t)
	configured, earlier := fixtureRoot(t), fixtureRoot(t)
	writeConfig(t, "root = \""+configured+"\"\n")

	// Session one switches from the start root to `earlier`.
	first := onFixture(t, 250, 40)
	if _, cmd := switchTo(t, first, earlier); cmd == nil {
		t.Fatal("the switch did nothing")
	}

	// Session two starts on yet another root and finds both in the menu.
	startRoot := fixtureRoot(t)
	t.Setenv("VOYAGE_API_KEY", "")
	second := newModel(startRoot, defaultSettings(), nil)
	next, _ := second.Update(tea.WindowSizeMsg{Width: 250, Height: 40})
	menu, _ := press(next.(model), "esc", "f", "enter")
	for _, want := range []string{startRoot, configured, earlier} {
		if !slices.Contains(menu.rootMenu.roots, want) {
			t.Errorf("root menu = %v, lacks %q", menu.rootMenu.roots, want)
		}
		if end := want[len(want)-30:]; !strings.Contains(menu.View(), end) { // long paths show their tail
			t.Errorf("the menu on screen lacks the end of %q", want)
		}
	}
}

// Choosing a listed root switches to it.
func TestRootMenuSwitchesToAListedRoot(t *testing.T) {
	stateHome(t)
	configured := fixtureRoot(t)
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
	menu, _ = pressKey(menu, tea.KeyEnter)
	if menu.root != configured {
		t.Errorf("root = %q, want the chosen %q", menu.root, configured)
	}
}

// US 2, criterion 5: a path without a catalogue keeps the root and shows the error as a toast.
func TestPathWithoutCatalogueKeepsTheRoot(t *testing.T) {
	home := stateHome(t)
	m := onFixture(t, 250, 40)
	_, done := search(t, m, "deploy")
	for name, path := range map[string]string{
		"a directory without a catalogue": t.TempDir(),
		"a missing path":                  filepath.Join(t.TempDir(), "nothing"),
		"a file":                          filepath.Join(m.root, "SPEC.md"),
	} {
		next, _ := switchTo(t, done, path)
		if next.root != m.root {
			t.Errorf("%s: root = %q, want %q kept", name, next.root, m.root)
		}
		if next.toast == nil || next.toast.title != "Root not changed" || !strings.Contains(next.View(), "Root not changed") {
			t.Errorf("%s: no error toast on screen:\n%s", name, next.View())
		}
		if !slices.Equal(hitPaths(next), hitPaths(done)) {
			t.Errorf("%s: the hits changed", name)
		}
	}
	if _, err := os.Stat(filepath.Join(home, "okf", "tui.json")); err == nil {
		t.Error("a refused root was remembered")
	}
}

// US 2, criterion 6: X clears every filter and keeps the root.
func TestXClearsAllFiltersButTheRoot(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 250, 40)
	other := fixtureRoot(t)
	next, cmd := switchTo(t, m, other)
	next = settle(t, next, cmd)
	next, _ = press(next, "/")
	_, done := search(t, next, "the")
	all := hitPaths(done)
	done, cmd2 := choose(t, done, fieldBundle, "recipes")
	done, _ = choose(t, settle(t, done, cmd2), fieldType, "Recipe")
	if !done.filters.active() {
		t.Fatal("no filter set")
	}
	cleared, cmd3 := press(done, "X")
	if cleared.filters.active() || cleared.root != other || cmd3 == nil {
		t.Fatalf("after X: active = %v, root = %q, cmd = %v; want no filter, root %q, a rerun", cleared.filters.active(), cleared.root, cmd3, other)
	}
	cleared = settle(t, cleared, cmd3)
	if got := hitPaths(cleared); !slices.Equal(got, all) {
		t.Errorf("hits after X = %v, want the unfiltered %v", got, all)
	}
}

// US 2, criterion 7: the menus list the values of the active root only.
func TestMenusListOnlyValuesOfTheActiveRoot(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 250, 40)
	open := func(m model, field filterField) []string {
		t.Helper()
		next, _ := press(m, "esc", "f")
		for range int(field) {
			next, _ = press(next, "l")
		}
		next, _ = press(next, "enter")
		if next.overlay != overlayFilterMenu {
			t.Fatalf("field %v: overlay = %v, want its menu", field, next.overlay)
		}
		got := slices.Clone(next.filters.options[field])
		for _, v := range got {
			if !strings.Contains(next.View(), v) {
				t.Errorf("the %v menu on screen lacks %q", field, v)
			}
		}
		return got
	}
	if got, want := open(m, fieldBundle), []string{"_ctx", "handbook", "kc-gov", "recipes"}; !slices.Equal(got, want) {
		t.Errorf("bundles = %v, want %v", got, want)
	}
	if got := open(m, fieldType); !slices.Equal(got, []string{"Concept", "Context", "Guide", "Note", "Recipe", "Rule", "Runbook"}) {
		t.Errorf("types = %v, want the types of TYPES.md", got)
	}
	if got := open(m, fieldTag); !slices.Contains(got, "food") || !slices.Contains(got, "ops") || slices.Contains(got, "nosuch") {
		t.Errorf("tags = %v, want the tags the concepts use", got)
	}

	other := fixtureRoot(t)
	if err := os.RemoveAll(filepath.Join(other, "recipes")); err != nil {
		t.Fatal(err)
	}
	next, _ := switchTo(t, m, other)
	if got := open(next, fieldBundle); slices.Contains(got, "recipes") || !slices.Contains(got, "handbook") {
		t.Errorf("bundles of the other root = %v, want no recipes", got)
	}
	if got := open(next, fieldTag); slices.Contains(got, "food") || !slices.Contains(got, "ops") {
		t.Errorf("tags of the other root = %v, want no food", got)
	}
}

// A filter value the new root does not hold is dropped, and the toast names it.
func TestRootSwitchDropsFilterValuesMissingThere(t *testing.T) {
	stateHome(t)
	m := onFixture(t, 250, 40)
	other := fixtureRoot(t)
	if err := os.RemoveAll(filepath.Join(other, "recipes")); err != nil {
		t.Fatal(err)
	}
	_, done := search(t, m, "the")
	done, _ = choose(t, done, fieldBundle, "recipes", "handbook")
	done, _ = choose(t, done, fieldType, "Runbook")
	next, _ := switchTo(t, done, other)
	if got, want := next.filters.exprText(), "path ~ handbook/ and type = Runbook"; got != want {
		t.Errorf("expression on the new root = %q, want %q", got, want)
	}
	if next.toast == nil || !strings.Contains(next.toast.context, "bundle recipes") || strings.Contains(next.toast.context, "handbook") {
		t.Errorf("toast = %+v, want one naming only the dropped bundle recipes", next.toast)
	}
}

// Values that are not plain words are quoted.
func TestExpressionQuotesValues(t *testing.T) {
	f := filterState{}
	f.selected[fieldTag] = []string{"two words", "it's", "and", "plain-1"}
	want := `(tag = "two words" or tag = "it's" or tag = "and" or tag = plain-1)`
	if got := f.exprText(); got != want {
		t.Errorf("expression = %q, want %q", got, want)
	}
}
