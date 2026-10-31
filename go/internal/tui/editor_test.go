package tui

import (
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"strings"
	"testing"
	"unsafe"

	tea "github.com/charmbracelet/bubbletea"
)

// fakeEditor writes an executable script that runs body with the file to edit as $1, and returns
// its path. The script stands for the user's editor.
func fakeEditor(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "fake-editor")
	if err := os.WriteFile(path, []byte("#!/bin/sh\n"+body+"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	return path
}

// runExec runs the editor process a tea.ExecProcess command stands for, the way the program does
// without a terminal: it runs the exec command, then the callback with its error, and returns the
// callback's message. bubbletea keeps the exec message unexported, so the test reads its two
// fields through reflection.
func runExec(t *testing.T, cmd tea.Cmd) tea.Msg {
	t.Helper()
	if cmd == nil {
		t.Fatal("no command")
	}
	msg := cmd()
	if reflect.TypeOf(msg).Name() != "execMsg" {
		return msg // not an exec: an immediate failure message
	}
	v := reflect.New(reflect.TypeOf(msg)).Elem()
	v.Set(reflect.ValueOf(msg))
	field := func(name string) reflect.Value {
		f := v.FieldByName(name)
		return reflect.NewAt(f.Type(), unsafe.Pointer(f.UnsafeAddr())).Elem()
	}
	run := field("cmd").Interface().(tea.ExecCommand)
	callback := field("fn").Interface().(tea.ExecCallback)
	return callback(run.Run())
}

// feed sends msg to m and returns the new model.
func feed(m model, msg tea.Msg) model {
	next, _ := m.Update(msg)
	return next.(model)
}

// searchedOnFixture is a model with the hits of "deploy", focus on the list, and the setting
// editor pointing at script.
func searchedOnFixture(t *testing.T, script string) model {
	t.Helper()
	m := onFixture(t, 200, 40)
	m.settings.Editor = script
	_, m = search(t, m, "deploy")
	if m.focus != focusList || len(m.search.hits) < 2 {
		t.Fatalf("focus = %v, hits = %d: want the list focused with several hits", m.focus, len(m.search.hits))
	}
	return m
}

// Criterion 5: the setting, then $VISUAL, then $EDITOR, then vi; arguments stay arguments.
func TestEditorResolutionOrder(t *testing.T) {
	cases := []struct {
		setting, visual, editor string
		want                    []string
	}{
		{"nvim", "code", "nano", []string{"nvim"}},
		{"", "code", "nano", []string{"code"}},
		{"", "", "nano", []string{"nano"}},
		{"", "", "", []string{"vi"}},
		{"  ", " ", "", []string{"vi"}},
		{"code --wait", "x", "y", []string{"code", "--wait"}},
		{"", "emacs -nw", "y", []string{"emacs", "-nw"}},
	}
	for _, c := range cases {
		t.Setenv("VISUAL", c.visual)
		t.Setenv("EDITOR", c.editor)
		if got := editorCommand(c.setting); !slices.Equal(got, c.want) {
			t.Errorf("setting %q, VISUAL %q, EDITOR %q: got %v, want %v", c.setting, c.visual, c.editor, got, c.want)
		}
	}
	t.Setenv("VISUAL", "")
	t.Setenv("EDITOR", "")
	if got := editorExec("code --wait", "/x.md").Args; !slices.Equal(got, []string{"code", "--wait", "/x.md"}) {
		t.Errorf("args = %v, want the file last", got)
	}
}

// Criteria 1, 2 and 3: `e` opens the focused hit's file in the editor; afterwards root, query,
// hit order and focus are as before, and the detail pane shows the changed description, tags and
// headings.
func TestEditOpensHitAndReloadsIt(t *testing.T) {
	dir := t.TempDir()
	log, replacement := filepath.Join(dir, "log"), filepath.Join(dir, "new.md")
	// The editor logs its argument and replaces the file with a prepared text.
	script := fakeEditor(t, `echo "$1" >> `+log+`
cp `+replacement+` "$1"`)
	m := searchedOnFixture(t, script)
	before := m
	hit := *m.search.focused()
	if !strings.HasSuffix(hit.Abs, "handbook/ops/deploy.md") {
		t.Fatalf("focused hit %s: the test edits the deploy runbook", hit.Abs)
	}
	original, err := os.ReadFile(hit.Abs)
	if err != nil {
		t.Fatal(err)
	}
	edited := strings.Replace(string(original), "description: \"How to deploy: build, ship, verify\"", "description: \"Rewritten in the editor\"", 1)
	edited = strings.Replace(edited, "  - deploy\n", "  - deploy\n  - freshly-tagged\n", 1)
	edited += "\n## Added By Editor\n\ntext\n"
	if edited == string(original) || strings.Contains(strings.Join(m.detailRows(200), "\n"), "Rewritten in the editor") {
		t.Fatal("precondition: the fixture text differs from the test's expectation")
	}
	if err := os.WriteFile(replacement, []byte(edited), 0o644); err != nil {
		t.Fatal(err)
	}

	// `e` starts the editor: the command is an exec of the setting on the hit's file.
	_, cmd := press(m, "e")
	msg := runExec(t, cmd)
	if edited, ok := msg.(fileEditedMsg); !ok || edited.path != hit.Abs || edited.err != nil {
		t.Fatalf("editor answer = %#v, want a clean fileEditedMsg for %s", msg, hit.Abs)
	}
	after := feed(m, msg)

	if got, _ := os.ReadFile(log); strings.TrimSpace(string(got)) != hit.Abs {
		t.Errorf("editor opened %q, want %q", strings.TrimSpace(string(got)), hit.Abs)
	}
	rows := strings.Join(after.detailRows(200), "\n")
	for _, want := range []string{"Rewritten in the editor", "freshly-tagged", "Added By Editor"} {
		if !strings.Contains(rows, want) {
			t.Errorf("detail pane lacks %q after the edit:\n%s", want, rows)
		}
	}
	if view := after.View(); !strings.Contains(view, "Rewritten in the editor") {
		t.Errorf("the screen does not show the new description:\n%s", view)
	}
	if after.toast != before.toast { // the ranking's warning of the search stays, nothing new
		t.Errorf("toast = %+v after a clean exit, want the one from before", after.toast)
	}

	// Criterion 2: what the session shows stays. Filters and buffer do not exist yet; the exec
	// path only replaces the one hit and never builds a new model, so later fields survive.
	if after.root != before.root || after.search.query != before.search.query ||
		after.focus != before.focus || after.search.cursor != before.search.cursor ||
		after.layout != before.layout || after.query.Value() != before.query.Value() {
		t.Errorf("session changed: root %q→%q, query %q→%q, focus %v→%v, cursor %d→%d",
			before.root, after.root, before.search.query, after.search.query, before.focus, after.focus,
			before.search.cursor, after.search.cursor)
	}
	if !slices.Equal(hitPaths(after), hitPaths(before)) {
		t.Errorf("hit order = %v, want %v", hitPaths(after), hitPaths(before))
	}
	for i, h := range after.search.hits {
		if i != before.search.cursor && h.Description != before.search.hits[i].Description {
			t.Errorf("hit %s was reloaded, only the edited hit may change", h.Path)
		}
	}
	if before.search.focused().Description != hit.Description {
		t.Error("the model before the edit changed: lists are shared between copies")
	}
}

// A hit that is not under the cursor but is the edited file reloads too; the cursor stays.
func TestReloadKeepsCursorAndScroll(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	m = m.moveCursor(1)
	m.search.detailScroll = 0
	other := m.search.hits[0]
	if err := os.WriteFile(other.Abs, []byte("---\ntype: Runbook\ntitle: Changed\ndescription: gone different\n---\n\n## New\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	next, _ := m.Update(fileEditedMsg{path: other.Abs})
	after := next.(model)
	if after.search.cursor != 1 || after.search.hits[0].Description != "gone different" || after.search.hits[0].Title != "Changed" {
		t.Errorf("cursor %d, hit 0 %+v: want the cursor on 1 and hit 0 reloaded", after.search.cursor, after.search.hits[0])
	}
	if m.search.hits[0].Title == "Changed" {
		t.Error("reload wrote into the list of the earlier model")
	}
}

// Criterion 4: an editor that exits with an error gives a toast and keeps the session.
func TestEditorErrorShowsToastAndKeepsSession(t *testing.T) {
	m := searchedOnFixture(t, fakeEditor(t, "exit 1"))
	before := m
	_, cmd := press(m, "e")
	after := feed(m, runExec(t, cmd))
	if after.toast == nil || after.toast.kind != toastError || after.toast.title != "Editor failed" ||
		!strings.Contains(after.toast.context, "exit status 1") {
		t.Fatalf("toast = %+v, want an error toast with the exit status", after.toast)
	}
	if !strings.Contains(after.View(), "Editor failed") {
		t.Errorf("the toast is not on screen:\n%s", after.View())
	}
	if after.root != before.root || after.search.query != before.search.query || after.focus != before.focus ||
		after.search.cursor != before.search.cursor || !slices.Equal(hitPaths(after), hitPaths(before)) {
		t.Error("session changed after an editor error")
	}
	if after.overlay != overlayNone {
		t.Errorf("overlay = %v, want none", after.overlay)
	}
}

// `e` with no editor binary at all is an editor error too, not a crash.
func TestMissingEditorShowsToast(t *testing.T) {
	m := searchedOnFixture(t, filepath.Join(t.TempDir(), "no-such-editor"))
	_, cmd := press(m, "e")
	after := feed(m, runExec(t, cmd))
	if after.toast == nil || after.toast.title != "Editor failed" {
		t.Fatalf("toast = %+v, want an Editor failed toast", after.toast)
	}
}

// A file the editor deleted keeps its row and says so.
func TestDeletedFileKeepsRowAndToasts(t *testing.T) {
	m := searchedOnFixture(t, fakeEditor(t, `rm "$1"`))
	_, cmd := press(m, "e")
	after := feed(m, runExec(t, cmd))
	if len(after.search.hits) != len(m.search.hits) || after.toast == nil || after.toast.title != "Hit not reloaded" {
		t.Fatalf("hits %d, toast %+v: want the row kept and a Hit not reloaded toast", len(after.search.hits), after.toast)
	}
}

// `e` does nothing without a hit, inside the query field, and under an overlay.
func TestEditKeyOnlyOnFocusedHit(t *testing.T) {
	m := onFixture(t, 100, 30)
	if _, cmd := press(m, "esc", "e"); cmd != nil {
		t.Error("e without hits started a command")
	}
	m = searchedOnFixture(t, "unused")
	typed, _ := press(m, "/", "e")
	if !strings.HasSuffix(typed.query.Value(), "e") {
		t.Errorf("e in the query field: value %q, want the typed letter", typed.query.Value())
	}
	if _, cmd := press(m, "?", "e"); cmd != nil {
		t.Error("e under the help overlay started a command")
	}
}

// The footer and the help list the key while a hit is focused.
func TestEditKeyInFooterAndHelp(t *testing.T) {
	m := searchedOnFixture(t, "unused")
	if !strings.Contains(m.View(), "edit"+nbsp+"hit") {
		t.Errorf("footer lacks the edit hint:\n%s", m.View())
	}
	help, _ := press(m, "?")
	if !strings.Contains(help.View(), "edit hit") {
		t.Errorf("help lacks the edit key:\n%s", help.View())
	}
}

// editText hands initial to the editor in a temp file and delivers the edited text with the
// caller's identifier; the temp file is gone afterwards.
func TestEditTextReturnsEditedText(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("TMPDIR", tmp)
	seen := filepath.Join(t.TempDir(), "seen")
	m := onFixture(t, 100, 30)
	m.settings.Editor = fakeEditor(t, `cat "$1" > `+seen+`
printf ' and more' >> "$1"`)

	got, _ := runExec(t, m.editText("notes", "first words")).(textEditedMsg)

	if got.caller != "notes" || got.text != "first words and more" || got.err != nil {
		t.Errorf("answer = %+v, want caller notes, text %q", got, "first words and more")
	}
	if b, _ := os.ReadFile(seen); string(b) != "first words" {
		t.Errorf("editor saw %q, want the initial text", b)
	}
	if left, _ := os.ReadDir(tmp); len(left) != 0 {
		t.Errorf("temp files left behind: %v", left)
	}
}

// An editor error comes back as the message's error, and the temp file is removed too.
func TestEditTextEditorError(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("TMPDIR", tmp)
	m := onFixture(t, 100, 30)
	m.settings.Editor = fakeEditor(t, "exit 3")
	got, _ := runExec(t, m.editText("tracker", "x")).(textEditedMsg)
	if got.caller != "tracker" || got.err == nil || !strings.Contains(got.err.Error(), "exit status 3") || got.text != "" {
		t.Errorf("answer = %+v, want caller tracker and the exit error", got)
	}
	if left, _ := os.ReadDir(tmp); len(left) != 0 {
		t.Errorf("temp files left behind: %v", left)
	}
}

// A temp file that cannot be made is an error message, not a panic.
func TestEditTextTempFileFailure(t *testing.T) {
	t.Setenv("TMPDIR", filepath.Join(t.TempDir(), "missing"))
	msg := onFixture(t, 100, 30).editText("notes", "x")()
	if got, ok := msg.(textEditedMsg); !ok || got.caller != "notes" || got.err == nil {
		t.Errorf("message = %#v, want a textEditedMsg with caller and error", msg)
	}
}
