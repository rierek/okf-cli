package tui

import (
	"reflect"
	"slices"
	"strings"
	"testing"

	keybind "github.com/charmbracelet/bubbles/key"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// pickCmd opens the command center, types the filter and runs the first row.
func pickCmd(m model, filter string) model {
	m, _ = press(m, "ctrl+k", filter)
	m, _ = press(m, "enter")
	return m
}

// Criterion 2: every binding of the key map is a command or one of the keys that only act inside
// a dialog, a menu, the text box, the focus ring or as a cursor step; help, footer and command
// center cannot drift apart.
func TestPaletteCoversKeyMap(t *testing.T) {
	notCommands := []string{"Up", "Down", "FocusIn", "FocusOut", "Palette", "Back", "Confirm", "Cancel", "QuitNow",
		"FieldPrev", "FieldNext", "Open", "Toggle", "TextSave", "TextEdit"}
	id := func(b keybind.Binding) string { return strings.Join(b.Keys(), ",") + "|" + b.Help().Desc }
	listed := map[string]bool{}
	for _, c := range paletteCommands() {
		listed[id(c.key)] = true
	}
	v := reflect.ValueOf(keys)
	for i := 0; i < v.NumField(); i++ {
		name := v.Type().Field(i).Name
		b := v.Field(i).Interface().(keybind.Binding)
		if !listed[id(b)] && !slices.Contains(notCommands, name) {
			t.Errorf("key map entry %s is no command and not on the list of keys that are none", name)
		}
		if listed[id(b)] && slices.Contains(notCommands, name) {
			t.Errorf("key map entry %s is a command and also on the list of keys that are none", name)
		}
	}
	for _, want := range []string{"add: note", "add: task", "view: buffer", "view: types", "view: tags",
		"refresh: index", "copy: buffer", "send: buffer", "help"} {
		if !slices.ContainsFunc(paletteCommands(), func(c command) bool { return c.name == want }) {
			t.Errorf("no command %q", want)
		}
	}
}

// The keys the commands press match their binding.
func TestKeyOfMatchesBinding(t *testing.T) {
	for _, b := range []keybind.Binding{keys.Note, keys.Task, keys.BufferToggle, keys.Edit, keys.Top, keys.Bottom,
		keys.DetailUp, keys.DetailDown, keys.BufferDrop, keys.BufferClear} {
		if !keybind.Matches(keyOf(b), b) {
			t.Errorf("keyOf(%v) does not match its binding", b.Keys())
		}
	}
}

// Criterion 1: ctrl+k opens the command center in every view, also inside the query field, where
// it leaves the text alone; a second ctrl+k and esc close it.
func TestCtrlKOpensEverywhere(t *testing.T) {
	m := sized(t, nil)
	m.query.SetValue("keep me")
	m, _ = press(m, "ctrl+k")
	if m.overlay != overlayPalette || m.query.Value() != "keep me" {
		t.Fatalf("query field: overlay = %v, query = %q", m.overlay, m.query.Value())
	}
	if out := m.View(); !strings.Contains(out, "Command center") || !strings.Contains(out, "add: note") {
		t.Errorf("view lacks the command center:\n%s", out)
	}
	assertGolden(t, "palette", m)
	if m, _ = press(m, "ctrl+k"); m.overlay != overlayNone {
		t.Errorf("second ctrl+k: overlay = %v, want none", m.overlay)
	}
	for name, start := range map[string][]string{"list": {"esc"}, "buffer": {"esc", "b"}} {
		m, _ := press(sized(t, nil), start...)
		if m, _ = press(m, "ctrl+k"); m.overlay != overlayPalette {
			t.Errorf("%s: overlay = %v, want the command center", name, m.overlay)
		}
		if m, _ = press(m, "esc"); m.overlay != overlayNone {
			t.Errorf("%s: esc leaves overlay = %v", name, m.overlay)
		}
	}
	// One overlay at a time: ctrl+k inside the help does not stack another.
	h, _ := press(sized(t, nil), "esc", "?", "ctrl+k")
	if h.overlay != overlayHelp {
		t.Errorf("ctrl+k inside the help: overlay = %v, want the help", h.overlay)
	}
}

// Criterion 2: typing filters the rows fuzzily; a filter that matches nothing says so.
func TestPaletteFiltersFuzzily(t *testing.T) {
	m, _ := press(sized(t, nil), "ctrl+k", "vtyp")
	if got := m.palFiltered(); len(got) == 0 || got[0].name != "view: tags" && got[0].name != "view: types" {
		t.Fatalf("rows for vtyp = %v", got)
	}
	out := m.View()
	if !strings.Contains(out, "view: types") || strings.Contains(out, "add: note") {
		t.Errorf("filtered view wrong:\n%s", out)
	}
	if m, _ = press(m, "zzz"); !strings.Contains(m.View(), "(no matches)") {
		t.Errorf("no row left, view lacks the hint:\n%s", m.View())
	}
}

// Criterion 3: a picked entry runs what its key runs, wherever the focus was.
func TestPaletteRunsKeyActions(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	m, _ = press(m, "/") // the query field has the focus

	if n := pickCmd(m, "toggle: hit"); len(n.buf.entries) != 1 || n.focus != focusList {
		t.Errorf("toggle: hit left %d buffer entries, focus %v", len(n.buf.entries), n.focus)
	}
	if n := pickCmd(m, "add: note"); n.overlay != overlayText {
		t.Errorf("add: note: overlay = %v, want the text box", n.overlay)
	}
	if n := pickCmd(m, "help"); n.overlay != overlayHelp {
		t.Errorf("help: overlay = %v", n.overlay)
	}
	if n := pickCmd(m, "refresh: index"); n.overlay != overlayRefresh {
		t.Errorf("refresh: index: overlay = %v", n.overlay)
	}
	if n := pickCmd(m, "view: buffer"); n.screen != screenBuffer {
		t.Errorf("view: buffer: screen = %v", n.screen)
	}
	if n := pickCmd(m, "quit"); n.overlay != overlayConfirm {
		t.Errorf("quit: overlay = %v, want the confirm dialog", n.overlay)
	}
	if n := pickCmd(m, "next: layout"); n.layout != layoutList {
		t.Errorf("next: layout = %v", n.layout)
	}
	if n := pickCmd(m, "go: last hit"); n.search.cursor != len(n.search.hits)-1 {
		t.Errorf("go: last hit: cursor %d of %d", n.search.cursor, len(n.search.hits))
	}
	// Commands of the buffer view say where they work.
	if n := pickCmd(m, "remove: entry"); n.toast == nil || !strings.Contains(n.toast.context, "buffer view") {
		t.Errorf("remove: entry outside the buffer view: toast = %+v", n.toast)
	}
	b := pickCmd(addHits(t, searchedOnFixture(t, "unused"), 0, 1), "view: buffer")
	if n := pickCmd(b, "remove: entry"); len(n.buf.entries) != 1 {
		t.Errorf("remove: entry in the buffer view left %d entries, want 1", len(n.buf.entries))
	}
	if n := pickCmd(b, "clear: buffer"); n.overlay != overlayConfirm {
		t.Errorf("clear: buffer: overlay = %v, want the confirm dialog", n.overlay)
	}
	// A hit command without a hit only says so.
	if n := pickCmd(sized(t, nil), "edit: hit"); n.toast == nil || n.overlay != overlayNone {
		t.Errorf("edit: hit without a hit: toast = %+v, overlay = %v", n.toast, n.overlay)
	}
}

// Criteria 4 and 5: view: types shows name and description of TYPES.md, view: tags the tags with
// their counts; esc goes back, and the views have no key of their own.
func TestTypesAndTagsViews(t *testing.T) {
	m := onFixture(t, 120, 40)
	types := pickCmd(m, "view: types")
	if types.screen != screenTypes {
		t.Fatalf("screen = %v, want the types view", types.screen)
	}
	out := types.View()
	for _, want := range []string{"Types", "Guide", "Step-by-step instructions", "Runbook", "Operational procedure"} {
		if !strings.Contains(out, want) {
			t.Errorf("types view lacks %q:\n%s", want, out)
		}
	}
	if back, _ := press(types, "esc"); back.screen != screenSearch {
		t.Errorf("esc: screen = %v, want the search screen", back.screen)
	}

	tags := pickCmd(m, "view: tags")
	if tags.screen != screenTags {
		t.Fatalf("screen = %v, want the tags view", tags.screen)
	}
	counts, err := catalogue.AllTags(tags.root)
	if err != nil || len(counts) == 0 {
		t.Fatalf("fixture tags: %v, %v", counts, err)
	}
	out = tags.View()
	top := counts.Ranked()[0]
	if !strings.Contains(out, "Tags") || !strings.Contains(out, top.Tag) {
		t.Errorf("tags view lacks the header or %q:\n%s", top.Tag, out)
	}
	if rows := strings.Count(out, "\n"); rows != 39 {
		t.Errorf("tags view is %d rows high, want 40", rows+1)
	}
	for _, key := range []string{"t", "T", "y"} { // no key opens either view
		if n, _ := press(m, "esc", key); n.screen != screenSearch {
			t.Errorf("key %q opened screen %v", key, n.screen)
		}
	}
}
