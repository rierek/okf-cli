package tui

import (
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

// sendKey sends a key of the given type: the keys the press helper has no name for.
func sendKey(m model, types ...tea.KeyType) model {
	for _, ty := range types {
		m = feed(m, tea.KeyMsg{Type: ty})
	}
	return m
}

// research runs a new search on the list-focused model.
func research(t *testing.T, m model, query string) model {
	t.Helper()
	m, _ = press(m, "/")
	m.query.SetValue(query)
	m, cmd := press(m, "enter")
	return settle(t, m, cmd)
}

// titles are the titles of the buffer entries in order.
func titles(m model) []string {
	var out []string
	for _, e := range m.buf.Entries() {
		out = append(out, e.Title)
	}
	return out
}

// addHits buffers the hits at the given list positions, in that order.
func addHits(t *testing.T, m model, positions ...int) model {
	t.Helper()
	for _, p := range positions {
		m = m.moveCursor(p)
		m, _ = press(m, " ")
	}
	return m
}

// saveNote opens the note box on the focused hit, types text and saves.
func saveNote(m model, text string) model {
	m, _ = press(m, "n", text)
	return sendKey(m, tea.KeyCtrlS)
}

// Criteria 1 and 2: space adds the focused hit and marks its row, a second space removes it and
// unmarks it.
func TestSpaceTogglesHitAndMark(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	if strings.Contains(m.View(), "◆") {
		t.Fatalf("a fresh list shows a buffer mark:\n%s", m.View())
	}
	added, _ := press(m, " ")
	if len(added.buf.entries) != 1 || added.buf.entries[0].Abs != m.search.hits[0].Abs {
		t.Fatalf("buffer after space = %+v, want the focused hit", added.buf.entries)
	}
	if got := strings.Count(added.View(), "◆"); got != 1 {
		t.Errorf("view shows %d marks, want 1:\n%s", got, added.View())
	}
	if !strings.Contains(added.header(added.width-2), "buffer 1") {
		t.Errorf("header lacks the buffer count:\n%s", added.View())
	}
	removed, _ := press(added, " ")
	if len(removed.buf.entries) != 0 || strings.Contains(removed.View(), "◆") || !strings.Contains(removed.header(removed.width-2), "buffer 0") {
		t.Errorf("second space: buffer %+v, view:\n%s", removed.buf.entries, removed.View())
	}
	if len(m.buf.entries) != 0 || len(added.buf.entries) != 1 {
		t.Error("an earlier copy of the model changed: the buffer shares its slice")
	}
}

// space and b type inside the query field instead of acting.
func TestBufferKeysTypeInQueryField(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	m, _ = press(m, "/", " ", "b", "n")
	if len(m.buf.entries) != 0 || m.screen != screenSearch || m.overlay != overlayNone {
		t.Errorf("buffer keys acted in the query field: buf %+v screen %v overlay %v", m.buf.entries, m.screen, m.overlay)
	}
	if !strings.HasSuffix(m.query.Value(), " bn") {
		t.Errorf("query = %q, want the typed keys at its end", m.query.Value())
	}
}

// Criterion 3: the same file found by a later search, or under a symlinked spelling of the root,
// shows as buffered and is not added twice.
func TestSameFileIsOneEntryAcrossSearchesAndSpellings(t *testing.T) {
	real := fixtureRoot(t)
	link := filepath.Join(t.TempDir(), "link")
	if err := os.Symlink(real, link); err != nil {
		t.Fatal(err)
	}
	t.Setenv("VOYAGE_API_KEY", "")
	next, _ := newModel(link, defaultSettings(), nil).Update(tea.WindowSizeMsg{Width: 200, Height: 40})
	_, m := search(t, next.(model), "deploy")
	m = addHits(t, m, 0)
	first := m.buf.entries[0]
	if !strings.HasPrefix(first.Abs, link) {
		t.Fatalf("entry path %q is not under the symlinked root %q", first.Abs, link)
	}

	// Later search, other spelling: the root is the real path now.
	m, _ = m.setRoot(real)
	m = research(t, m, "deploy")
	if got := m.search.hits[0].Abs; got == first.Abs || !strings.HasPrefix(got, real) {
		t.Fatalf("hit path %q: want the real spelling, not %q", got, first.Abs)
	}
	if !m.buffered(0) || !strings.Contains(m.View(), "◆") {
		t.Errorf("the same file under another spelling is not shown as buffered:\n%s", m.View())
	}
	m = saveNote(m, "same file") // writes onto the entry, never a second one
	if len(m.buf.entries) != 1 || m.buf.entries[0].Note != "same file" || m.buf.entries[0].Abs != first.Abs {
		t.Errorf("buffer = %+v, want the one first entry carrying the note", m.buf.entries)
	}
	// A new search that finds the file at another rank still marks it.
	m = research(t, m, "ops incident")
	if len(m.buf.entries) != 1 {
		t.Errorf("buffer has %d entries, want 1", len(m.buf.entries))
	}
}

// Criterion 4 (searches and root changes; filters only rerun the search): the entries stay with
// their snapshot while a new search lists other hits and while the root is another one.
func TestBufferSurvivesSearchesAndRootChange(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	m = addHits(t, m, 0, 1)
	want := m.buf.Entries()
	if len(want) != 2 || want[0].Title == "" || want[0].Type == "" || want[0].Bundle == "" || want[0].Abs == "" {
		t.Fatalf("entries lack their snapshot: %+v", want)
	}

	m = research(t, m, "security")
	if !slices.EqualFunc(m.buf.Entries(), want, func(a, b bufferEntry) bool { return a.id == b.id && a.Title == b.Title }) {
		t.Errorf("buffer after a new search = %+v, want %+v", m.buf.Entries(), want)
	}
	other := fixtureRoot(t)
	m, _ = m.setRoot(other)
	if !strings.Contains(m.header(m.width-2), "buffer 2") {
		t.Errorf("header lost the count after the root change:\n%s", m.View())
	}
	m = research(t, m, "recipe")
	if got := m.buf.Entries(); len(got) != 2 || got[0].Abs != want[0].Abs || got[1].Abs != want[1].Abs {
		t.Errorf("buffer after a root change = %+v, want %+v", got, want)
	}
}

// Criterion 5: the buffer view lists the entries in the order they were added, each with title,
// type, bundle and a note marker; the accessor gives the same order.
func TestBufferViewListsInInsertionOrder(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	m = addHits(t, m, 2, 0, 1)
	m = m.moveCursor(0)
	m = saveNote(m, "worth a look")
	if len(m.buf.entries) != 3 {
		t.Fatalf("buffer = %+v", m.buf.entries)
	}
	order := titles(m)
	if order[0] != m.search.hits[2].Title || order[1] != m.search.hits[0].Title || order[2] != m.search.hits[1].Title {
		t.Fatalf("accessor order = %v", order)
	}
	got := m.buf.Entries()
	got[0].Title = "changed" // the accessor hands out a copy
	if m.buf.entries[0].Title == "changed" {
		t.Error("Entries returns the buffer's own slice")
	}

	m, _ = press(m, "b")
	m.toast = nil // the ranking warning of the search covers the top right
	view := m.View()
	if m.screen != screenBuffer || !strings.Contains(view, "> "+m.root+": Buffer") {
		t.Fatalf("b did not open the buffer view:\n%s", view)
	}
	lines := strings.Split(view, "\n")
	row := func(i int) string {
		for _, l := range lines {
			if strings.Contains(l, order[i]) && strings.Contains(l, m.buf.entries[i].Type+" · "+m.buf.entries[i].Bundle) {
				return l
			}
		}
		t.Fatalf("no row with title, type and bundle of entry %d (%q):\n%s", i, order[i], view)
		return ""
	}
	at := func(i int) int { return slices.Index(lines, row(i)) }
	if !(at(0) < at(1) && at(1) < at(2)) {
		t.Errorf("rows are not in insertion order: %d %d %d", at(0), at(1), at(2))
	}
	// Only the entry that carries the note has the marker: hit 0 is the second entry.
	for i, wantMark := range []bool{false, true, false} {
		if got := strings.Contains(row(i), noteMark); got != wantMark {
			t.Errorf("entry %d: note marker = %v, want %v", i, got, wantMark)
		}
	}
	if !strings.Contains(view, "none, press n") {
		t.Errorf("detail pane of the entry without a note lacks the hint:\n%s", view)
	}
	if noted, _ := press(m, "j"); !strings.Contains(noted.View(), "worth a look") {
		t.Errorf("detail pane of the entry with a note lacks the note:\n%s", noted.View())
	}
	back, _ := press(m, "esc")
	if back.screen != screenSearch || !strings.Contains(back.View(), "Search") {
		t.Errorf("esc did not leave the buffer view:\n%s", back.View())
	}
}

// x removes the entry under the cursor; the cursor stays inside the list.
func TestBufferViewRemovesOneEntry(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	m = addHits(t, m, 0, 1, 2)
	order := titles(m)
	m, _ = press(m, "b", "j", "x")
	if got := titles(m); !slices.Equal(got, []string{order[0], order[2]}) {
		t.Errorf("after x on the second entry: %v, want %v", got, []string{order[0], order[2]})
	}
	m, _ = press(m, "G", "x", "x", "x")
	if len(m.buf.entries) != 0 || m.bufCursor != 0 {
		t.Errorf("emptied buffer: entries %d, cursor %d", len(m.buf.entries), m.bufCursor)
	}
	if view := m.View(); !strings.Contains(view, "The buffer is empty.") {
		t.Errorf("empty buffer view:\n%s", view)
	}
}

// The buffer view keeps the list focus: / and tab do not move it to the hidden query field. A
// cursor left behind by entries removed on the search screen is pulled back into the list.
func TestBufferViewKeepsFocusAndCursor(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	m = addHits(t, m, 0, 1, 2)
	m, _ = press(m, "b")
	for _, k := range []string{"/", "tab", "shift+tab"} {
		if next, _ := press(m, k); next.screen != screenBuffer || next.focus != focusList {
			t.Errorf("%s in the buffer view: screen %v, focus %v", k, next.screen, next.focus)
		}
	}
	m, _ = press(m, "G", "b")
	m = m.moveCursor(0)
	m, _ = press(m, " ")
	m = m.moveCursor(1)
	m, _ = press(m, " ", "b")
	if len(m.buf.entries) != 1 || m.bufCursor != 0 {
		t.Fatalf("after removing two entries on the search screen: %d entries, cursor %d", len(m.buf.entries), m.bufCursor)
	}
	if m, _ = press(m, "n"); m.overlay != overlayText {
		t.Errorf("n on the one entry opened overlay %v", m.overlay)
	}
}

// The open text box follows a resize of the terminal.
func TestTextBoxFollowsResize(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	m, _ = press(m, "n")
	m = feed(m, tea.WindowSizeMsg{Width: 50, Height: 12})
	if m.text.area.Width() != m.textWidth() || m.text.area.Height() != m.textHeight() {
		t.Errorf("text area %dx%d after resize, want %dx%d", m.text.area.Width(), m.text.area.Height(), m.textWidth(), m.textHeight())
	}
}

// Criteria 6 and 7: c asks in the red dialog; cancel keeps the buffer, confirm empties it.
func TestClearBufferConfirmAndCancel(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	m = addHits(t, m, 0, 1)
	m, _ = press(m, "b", "c")
	if m.overlay != overlayConfirm || !m.confirm.destructive || !strings.Contains(m.View(), "Clear buffer?") {
		t.Fatalf("c opened overlay %v, confirm %+v:\n%s", m.overlay, m.confirm, m.View())
	}
	before := m.buf.Entries()
	for _, cancel := range []tea.KeyMsg{key("n"), key("esc")} {
		kept := feed(m, cancel)
		if kept.overlay != overlayNone || !slices.EqualFunc(kept.buf.Entries(), before, func(a, b bufferEntry) bool { return a.id == b.id }) || len(before) != 2 {
			t.Errorf("cancel with %q: overlay %v, buffer %+v", cancel.String(), kept.overlay, kept.buf.entries)
		}
	}
	for _, confirm := range []tea.KeyMsg{key("y"), key("enter")} {
		cleared := feed(m, confirm)
		if cleared.overlay != overlayNone || len(cleared.buf.entries) != 0 || !strings.Contains(cleared.header(cleared.width-2), "buffer 0") {
			t.Errorf("confirm with %q: overlay %v, buffer %+v", confirm.String(), cleared.overlay, cleared.buf.entries)
		}
	}
	if empty := feed(feed(m, key("y")), key("c")); empty.overlay != overlayNone {
		t.Error("c on an empty buffer opened a dialog")
	}
}

// Criterion 8: saving a note puts it on the entry; n adds an unbuffered hit; esc cancels; an
// empty note clears the note and keeps the entry; a note on an unbuffered hit that is empty adds
// nothing. The text area takes several lines.
func TestNoteSaveCancelAndEmpty(t *testing.T) {
	m := searchedOnFixture(t, "unused")

	cancelled, _ := press(m, "n", "draft")
	if cancelled.overlay != overlayText || !strings.Contains(cancelled.View(), "draft") {
		t.Fatalf("n did not open the text box:\n%s", cancelled.View())
	}
	cancelled = sendKey(cancelled, tea.KeyEsc)
	if cancelled.overlay != overlayNone || len(cancelled.buf.entries) != 0 {
		t.Errorf("esc: overlay %v, buffer %+v; want a closed box and no entry", cancelled.overlay, cancelled.buf.entries)
	}
	if empty := saveNote(m, "   "); len(empty.buf.entries) != 0 {
		t.Errorf("an empty note added %+v", empty.buf.entries)
	}

	m, _ = press(m, "n", "first line")
	m = sendKey(m, tea.KeyEnter)
	m, _ = press(m, "second line")
	m = sendKey(m, tea.KeyCtrlS)
	if m.overlay != overlayNone || len(m.buf.entries) != 1 || m.buf.entries[0].Note != "first line\nsecond line" {
		t.Fatalf("saved note: overlay %v, buffer %+v", m.overlay, m.buf.entries)
	}
	if m.buf.entries[0].Abs != m.search.hits[0].Abs {
		t.Error("the note landed on another hit")
	}

	// The box opens with the note; backspace to empty it; the entry stays.
	m, _ = press(m, "n")
	if !strings.Contains(m.View(), "first line") {
		t.Fatalf("note box does not show the saved note:\n%s", m.View())
	}
	for range "first line\nsecond line" {
		m = sendKey(m, tea.KeyBackspace)
	}
	m = sendKey(m, tea.KeyCtrlS)
	if len(m.buf.entries) != 1 || m.buf.entries[0].Note != "" {
		t.Errorf("empty note: buffer %+v, want the entry without a note", m.buf.entries)
	}

	// n in the buffer view writes the note of the entry under the cursor.
	m, _ = press(m, "b", "n", "from the buffer view")
	m = sendKey(m, tea.KeyCtrlS)
	if m.screen != screenBuffer || m.buf.entries[0].Note != "from the buffer view" {
		t.Errorf("note from the buffer view: screen %v, buffer %+v", m.screen, m.buf.entries)
	}
}

// Criterion 9: ctrl+e hands the current text to the editor and puts the edited text back into the
// input; ctrl+s then saves it. An editor error leaves the text as it was.
func TestCtrlEEditsTextInEditor(t *testing.T) {
	seen := filepath.Join(t.TempDir(), "seen")
	m := searchedOnFixture(t, fakeEditor(t, `cp "$1" `+seen+`
printf 'from the editor\nline two\n' > "$1"`))
	m, _ = press(m, "n", "typed text")
	next, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlE})
	msg := runExec(t, cmd)
	if got, _ := os.ReadFile(seen); string(got) != "typed text" {
		t.Errorf("the editor was handed %q, want the text of the input", got)
	}
	edited, ok := msg.(textEditedMsg)
	if !ok || edited.caller != noteCaller {
		t.Fatalf("editor answer = %#v, want a textEditedMsg of caller %q", msg, noteCaller)
	}
	m = feed(next.(model), msg)
	if m.overlay != overlayText || m.text.area.Value() != "from the editor\nline two" {
		t.Errorf("input = %q, overlay %v; want the edited text in the open box", m.text.area.Value(), m.overlay)
	}
	m = sendKey(m, tea.KeyCtrlS)
	if len(m.buf.entries) != 1 || m.buf.entries[0].Note != "from the editor\nline two" {
		t.Errorf("saved note = %+v", m.buf.entries)
	}

	// An editor that fails: toast, text unchanged.
	fail := searchedOnFixture(t, fakeEditor(t, "exit 1"))
	fail, _ = press(fail, "n", "keep me")
	_, cmd = fail.Update(tea.KeyMsg{Type: tea.KeyCtrlE})
	fail = feed(fail, runExec(t, cmd))
	if fail.text.area.Value() != "keep me" || fail.toast == nil || fail.toast.kind != toastError {
		t.Errorf("after a failing editor: input %q, toast %+v", fail.text.area.Value(), fail.toast)
	}
}

// An editor answer for a box that is closed, or of another caller, is dropped.
func TestStrayEditorAnswerIsDropped(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	closed := feed(m, textEditedMsg{caller: noteCaller, text: "late"})
	if closed.overlay != overlayNone {
		t.Errorf("an answer opened overlay %v", closed.overlay)
	}
	open, _ := press(m, "n", "mine")
	open = feed(open, textEditedMsg{caller: "task", text: "theirs"})
	if open.text.area.Value() != "mine" {
		t.Errorf("input = %q, want the answer of another caller dropped", open.text.area.Value())
	}
}

// The overlay is one reusable box: another asker passes its own title and save action.
func TestTextOverlayRunsTheCallersSave(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	var got string
	m, _ = m.openText("task", "Task prompt", "title\nbody", func(m model, text string) (model, tea.Cmd) {
		got = text
		return m, nil
	})
	if view := m.View(); !strings.Contains(view, "Task prompt") || !strings.Contains(view, "body") {
		t.Errorf("box lacks title or text:\n%s", view)
	}
	m = sendKey(m, tea.KeyCtrlS)
	if got != "title\nbody" || m.overlay != overlayNone {
		t.Errorf("save got %q, overlay %v", got, m.overlay)
	}
}

// An edited file refreshes the snapshot of its buffer entry and keeps note and place.
func TestEditRefreshesBufferSnapshot(t *testing.T) {
	dir := t.TempDir()
	replacement := filepath.Join(dir, "new.md")
	m := searchedOnFixture(t, fakeEditor(t, `cp `+replacement+` "$1"`))
	hit := *m.search.focused()
	original, err := os.ReadFile(hit.Abs)
	if err != nil {
		t.Fatal(err)
	}
	edited := strings.Replace(string(original), "description: \"How to deploy: build, ship, verify\"", "description: \"Rewritten in the editor\"", 1)
	if edited == string(original) {
		t.Fatal("precondition: the fixture text differs from the test's expectation")
	}
	if err := os.WriteFile(replacement, []byte(edited), 0o644); err != nil {
		t.Fatal(err)
	}
	m = addHits(t, m, 1, 0)
	m = saveNote(m, "keep")
	_, cmd := press(m, "e")
	after := feed(m, runExec(t, cmd))
	if got := after.buf.entries[1]; got.Description != "Rewritten in the editor" || got.Note != "keep" || got.Abs != hit.Abs {
		t.Errorf("entry after the edit = %+v", got)
	}
	if m.buf.entries[1].Description == "Rewritten in the editor" {
		t.Error("the model before the edit changed: the buffer shares its slice")
	}
	if after.buf.entries[0].id != m.buf.entries[0].id {
		t.Error("an edit moved the entries")
	}
}

// Goldens of the two new screens on a model with a given buffer: the buffer view with a note and
// the note box.
func TestBufferGoldens(t *testing.T) {
	m := sized(t, nil)
	m.buf = buffer{entries: []bufferEntry{
		{id: "/srv/catalogue/handbook/ops/deploy.md", Abs: "/srv/catalogue/handbook/ops/deploy.md", Title: "Deploy runbook",
			Type: "runbook", Bundle: "handbook", Tags: []string{"ops", "deploy"}, Note: "Check the rollback section.\nStill current?"},
		{id: "/srv/catalogue/recipes/soup.md", Abs: "/srv/catalogue/recipes/soup.md", Title: "Leek soup", Type: "recipe", Bundle: "recipes"},
	}}
	m.focus, m.screen = focusList, screenBuffer
	assertGolden(t, "buffer_view", m)

	m, _ = press(m, "n", "Check the rollback")
	assertGolden(t, "buffer_note_box", m)

	m.overlay = overlayNone
	m, _ = press(m, "c")
	assertGolden(t, "buffer_clear_confirm", m)
}
