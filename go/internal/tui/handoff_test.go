package tui

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

// herdrFixture is a fake `herdr` on PATH: `pane get` and `agent list` answer from the fixture
// files, every other call (send-text, focus) answers success, and every call is logged.
type herdrFixture struct{ dir string }

// fakeHerdr installs the fake herdr. paneJSON is the answer of `pane get`, agentsJSON the answer
// of `agent list`. HERDR_ACTIVE_PANE_ID names pane "wA:p1" the popup sits over.
func fakeHerdr(t *testing.T, paneJSON, agentsJSON string) herdrFixture {
	t.Helper()
	dir := t.TempDir()
	script := `#!/bin/sh
{ printf '%s\037' "$@"; printf '\036'; } >> "` + dir + `/log"
if [ -e "` + dir + `/down" ]; then echo '{"id":"x","error":{"code":"down","message":"herdr down"}}' >&2; exit 1; fi
case "$1 $2" in
"pane get") cat "` + dir + `/pane.json" ;;
"agent list") cat "` + dir + `/agents.json" ;;
*) if [ -e "` + dir + `/fail" ]; then
     echo '{"id":"x","error":{"code":"pane_not_found","message":"pane gone"}}' >&2
     exit 1
   else
     echo '{"id":"x","result":{}}'
   fi ;;
esac
`
	for name, body := range map[string]string{"herdr": script, "pane.json": paneJSON, "agents.json": agentsJSON} {
		mode := os.FileMode(0o644)
		if name == "herdr" {
			mode = 0o755
		}
		if err := os.WriteFile(filepath.Join(dir, name), []byte(body), mode); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("PATH", dir+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("HERDR_ACTIVE_PANE_ID", "wA:p1")
	t.Setenv("HERDR_PANE_ID", "")
	return herdrFixture{dir}
}

// calls are the logged herdr calls, one argv each.
func (f herdrFixture) calls(t *testing.T) [][]string {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join(f.dir, "log"))
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		t.Fatal(err)
	}
	var out [][]string
	for _, rec := range strings.Split(string(raw), "\x1e") {
		if rec != "" {
			out = append(out, strings.Split(strings.TrimSuffix(rec, "\x1f"), "\x1f"))
		}
	}
	return out
}

// writes are the logged calls that change something: everything but the two reads.
func (f herdrFixture) writes(t *testing.T) [][]string {
	t.Helper()
	var out [][]string
	for _, c := range f.calls(t) {
		if c[0]+" "+c[1] != "pane get" && c[0]+" "+c[1] != "agent list" {
			out = append(out, c)
		}
	}
	return out
}

// fail makes send-text and focus fail; down makes every call fail. A failing call writes its
// error to stderr and exits 1, as herdr does.
func (f herdrFixture) fail(t *testing.T) { t.Helper(); f.marker(t, "fail") }
func (f herdrFixture) down(t *testing.T) { t.Helper(); f.marker(t, "down") }

func (f herdrFixture) marker(t *testing.T, name string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(f.dir, name), nil, 0o644); err != nil {
		t.Fatal(err)
	}
}

// fakeClipboard replaces the clipboard writer; the returned slice grows with every copy.
func fakeClipboard(t *testing.T) *[]string {
	t.Helper()
	var got []string
	old := copyToClipboard
	copyToClipboard = func(s string) error { got = append(got, s); return nil }
	t.Cleanup(func() { copyToClipboard = old })
	return &got
}

// ctrlS presses ctrl+s, a key the press helper has no name for.
func ctrlS(m model) (model, tea.Cmd) {
	next, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlS})
	return next.(model), cmd
}

// answer runs the command cmd stands for: the one answer goes back into the model.
func answer(t *testing.T, m model, cmd tea.Cmd) (model, tea.Cmd) {
	t.Helper()
	if cmd == nil {
		t.Fatal("no command")
	}
	next, follow := m.Update(cmd())
	return next.(model), follow
}

// buffered is a model on the list with three buffered hits, the first with a note.
func buffered(t *testing.T) model {
	t.Helper()
	m := addHits(t, searchedOnFixture(t, "unused"), 0, 1, 2)
	m = saveNote(m.moveCursor(0), "check the rollback\nstep first")
	m.toast = nil
	return m
}

const (
	noAgentPane = `{"id":"x","result":{"pane":{"pane_id":"wA:p1","workspace_id":"wA"},"type":"pane_info"}}`
	agentPane   = `{"id":"x","result":{"pane":{"agent":"omp","agent_status":"working","pane_id":"wA:p1","workspace_id":"wA"}}}`
	// Three agents: another workspace first in herdr's order, then two of the current one.
	listed = `{"id":"x","result":{"type":"agent_list","agents":[
	 {"agent":"claude","agent_status":"idle","pane_id":"wB:p2","workspace_id":"wB","cwd":"/srv/b","terminal_title_stripped":"other workspace"},
	 {"agent":"omp","agent_status":"blocked","pane_id":"wA:p3","workspace_id":"wA","cwd":"/srv/a","terminal_title_stripped":"waits for approval"},
	 {"agent":"omp","agent_status":"working","pane_id":"wA:p4","workspace_id":"wA","cwd":"/srv/a","terminal_title_stripped":"busy agent"}]}}`
)

// Criterion 1: the export holds the header and every entry in buffer order with title, `@` path,
// type, bundle, tags, description and the note when there is one.
func TestExportHoldsEveryEntryInOrder(t *testing.T) {
	m := buffered(t)
	entries := m.buf.Entries()
	got := exportText(entries)
	if !strings.HasPrefix(got, "Fundstellen aus okf (3)\n") {
		t.Fatalf("header: %q", got)
	}
	last := 0
	for _, e := range entries {
		block := "## " + e.Title + "\n@" + e.Abs + "\n"
		i := strings.Index(got, block)
		if i < last {
			t.Fatalf("block of %q missing or out of order in\n%s", e.Title, got)
		}
		last = i
		for _, want := range []string{"type: " + e.Type, "bundle: " + e.Bundle, e.Description} {
			if !strings.Contains(got[i:], want) {
				t.Errorf("entry %q: %q missing in\n%s", e.Title, want, got)
			}
		}
		if len(e.Tags) > 0 && !strings.Contains(got, "tags: "+strings.Join(e.Tags, ", ")) {
			t.Errorf("entry %q: tags %v missing", e.Title, e.Tags)
		}
	}
	if !strings.HasPrefix(entries[0].Abs, "/") || !strings.Contains(got, "> check the rollback\n> step first\n") {
		t.Errorf("absolute path or quoted note missing in\n%s", got)
	}
	if strings.Count(got, "\n> ") != 2 {
		t.Errorf("only the first entry has a note:\n%s", got)
	}
}

// An entry without tags, description or note leaves those lines out.
func TestExportLeavesMissingFieldsOut(t *testing.T) {
	got := exportText([]bufferEntry{{Title: "T", Abs: "/r/b/t.md", Type: "doc", Bundle: "b"}})
	want := "Fundstellen aus okf (1)\n\n## T\n@/r/b/t.md\ntype: doc · bundle: b\n"
	if got != want {
		t.Errorf("export = %q, want %q", got, want)
	}
}

// Criterion 2: the pane under the popup runs an agent: ctrl+s writes the export there without
// Enter, focuses the pane and exits. It works on the buffer screen too.
func TestCtrlSSendsToTheAgentUnderThePopup(t *testing.T) {
	for _, screen := range []string{"search", "buffer"} {
		t.Run(screen, func(t *testing.T) {
			f := fakeHerdr(t, agentPane, listed)
			clipboard := fakeClipboard(t)
			m := buffered(t)
			if screen == "buffer" {
				m, _ = press(m, "b")
			}
			want := strings.TrimRight(exportText(m.buf.Entries()), "\n")
			m, cmd := ctrlS(m)
			if cmd == nil {
				t.Fatalf("ctrl+s ran nothing:\n%s", m.View())
			}
			if m.overlay != overlayNone {
				t.Errorf("the picker opened for an agent pane")
			}
			_, follow := answer(t, m, cmd)
			if !quits(follow) {
				t.Error("the TUI did not exit after the send")
			}
			writes := f.writes(t)
			if len(writes) != 2 ||
				fmt.Sprint(writes[0]) != fmt.Sprint([]string{"pane", "send-text", "wA:p1", want}) ||
				fmt.Sprint(writes[1]) != fmt.Sprint([]string{"agent", "focus", "wA:p1"}) {
				t.Errorf("writes = %q, want send-text of the export then focus of wA:p1", writes)
			}
			if len(*clipboard) != 0 {
				t.Errorf("clipboard touched: %q", *clipboard)
			}
		})
	}
}

// Criterion 3: no agent under the popup: a picker of the listed agents, the current workspace
// first, each with agent, status, title and directory. Nothing is sent yet.
func TestCtrlSOpensThePickerWithTheCurrentWorkspaceFirst(t *testing.T) {
	f := fakeHerdr(t, noAgentPane, listed)
	m, cmd := ctrlS(buffered(t))
	m, _ = answer(t, m, cmd)
	if m.overlay != overlayAgents {
		t.Fatalf("overlay = %v, want the agent picker:\n%s", m.overlay, m.View())
	}
	var panes []string
	for _, a := range m.agents.agents {
		panes = append(panes, a.Pane)
	}
	if fmt.Sprint(panes) != "[wA:p3 wA:p4 wB:p2]" {
		t.Errorf("order = %v, want the workspace of the popup first, herdr's order kept", panes)
	}
	view := m.View()
	for _, want := range []string{"Send to agent", "omp  blocked  waits for approval  /srv/a", "claude  idle  other workspace  /srv/b"} {
		if !strings.Contains(view, want) {
			t.Errorf("picker lacks %q:\n%s", want, view)
		}
	}
	if w := f.writes(t); len(w) != 0 {
		t.Errorf("sent before a pick: %q", w)
	}
}

// Criterion 4: picking an agent writes the export into its pane without Enter, focuses it and
// exits. The cursor starts on the first agent that can be chosen.
func TestPickingAnAgentSendsToIt(t *testing.T) {
	f := fakeHerdr(t, noAgentPane, listed)
	m, cmd := ctrlS(buffered(t))
	m, _ = answer(t, m, cmd)
	if m.agents.cursor != 1 {
		t.Fatalf("cursor = %d, want 1: the first agent is blocked", m.agents.cursor)
	}
	m, _ = press(m, "down") // wB:p2
	m, cmd = press(m, "enter")
	if cmd == nil {
		t.Fatal("enter sent nothing")
	}
	_, follow := answer(t, m, cmd)
	if !quits(follow) {
		t.Error("the TUI did not exit after the send")
	}
	want := strings.TrimRight(exportText(m.buf.Entries()), "\n")
	writes := f.writes(t)
	if len(writes) != 2 ||
		fmt.Sprint(writes[0]) != fmt.Sprint([]string{"pane", "send-text", "wB:p2", want}) ||
		fmt.Sprint(writes[1]) != fmt.Sprint([]string{"agent", "focus", "wB:p2"}) {
		t.Errorf("writes = %q, want send-text then focus of wB:p2", writes)
	}
}

// Esc closes the picker and sends nothing.
func TestPickerEscSendsNothing(t *testing.T) {
	f := fakeHerdr(t, noAgentPane, listed)
	m, cmd := ctrlS(buffered(t))
	m, _ = answer(t, m, cmd)
	m, cmd = press(m, "esc")
	if m.overlay != overlayNone || cmd != nil || len(f.writes(t)) != 0 {
		t.Errorf("overlay = %v, cmd = %v, writes = %q", m.overlay, cmd != nil, f.writes(t))
	}
}

// Criterion 5: a blocked agent is greyed and cannot be chosen: enter on it sends nothing and the
// picker stays open. A blocked agent under the popup is not sent to either; it lands in the picker.
func TestBlockedAgentIsGreyAndNotSentTo(t *testing.T) {
	f := fakeHerdr(t, noAgentPane, listed)
	lipgloss.SetColorProfile(termenv.TrueColor)
	t.Cleanup(func() { lipgloss.SetColorProfile(termenv.Ascii) })
	m, cmd := ctrlS(buffered(t))
	m, _ = answer(t, m, cmd)
	var blocked, free string
	for _, l := range strings.Split(m.View(), "\n") {
		if strings.Contains(l, "waits for approval") {
			blocked = l
		}
		if strings.Contains(l, "other workspace") {
			free = l
		}
	}
	grey := func(l, text string) string { // the escape sequence that precedes the text
		i := strings.Index(l, text)
		return l[max(strings.LastIndex(l[:i], "\x1b["), 0):i]
	}
	if blocked == "" || grey(blocked, "omp  blocked") == grey(free, "claude  idle") {
		t.Errorf("blocked row not styled differently from a free row:\n%q\n%q", blocked, free)
	}
	m, _ = press(m, "up") // onto the blocked agent
	if m.agents.cursor != 0 {
		t.Fatalf("cursor = %d", m.agents.cursor)
	}
	m, cmd = press(m, "enter")
	if cmd == nil && m.toast == nil {
		t.Error("no toast for the blocked pick")
	}
	if m.overlay != overlayAgents || len(f.writes(t)) != 0 {
		t.Errorf("overlay = %v, writes = %q: want the picker open and nothing sent", m.overlay, f.writes(t))
	}

	blockedPane := strings.Replace(agentPane, `"working"`, `"blocked"`, 1)
	fakeHerdr(t, blockedPane, listed)
	m, cmd = ctrlS(buffered(t))
	m, _ = answer(t, m, cmd)
	if m.overlay != overlayAgents {
		t.Errorf("a blocked agent under the popup got the text:\n%s", m.View())
	}
}

// Criterion 6: outside herdr, or with no agent listed, the export goes to the clipboard, the
// toast says so and the TUI stays open.
func TestNoAgentCopiesToTheClipboard(t *testing.T) {
	cases := map[string]func(t *testing.T) herdrFixture{
		"outside herdr": func(t *testing.T) herdrFixture {
			f := fakeHerdr(t, noAgentPane, listed)
			t.Setenv("HERDR_ACTIVE_PANE_ID", "")
			return f
		},
		"no agent listed": func(t *testing.T) herdrFixture {
			return fakeHerdr(t, noAgentPane, `{"id":"x","result":{"type":"agent_list","agents":[]}}`)
		},
		"herdr fails": func(t *testing.T) herdrFixture {
			f := fakeHerdr(t, noAgentPane, listed)
			f.down(t)
			return f
		},
	}
	for name, setup := range cases {
		t.Run(name, func(t *testing.T) {
			f := setup(t)
			clipboard := fakeClipboard(t)
			m, _ := press(buffered(t), "/") // from the query field, where ctrl+s types nothing
			want := exportText(m.buf.Entries())
			m, cmd := ctrlS(m)
			m, follow := answer(t, m, cmd)
			if quits(follow) {
				t.Error("the TUI exited")
			}
			if len(*clipboard) != 1 || (*clipboard)[0] != want {
				t.Errorf("clipboard = %q, want the export", *clipboard)
			}
			if m.toast == nil || m.toast.title != "no agent found – copied to clipboard" {
				t.Errorf("toast = %+v", m.toast)
			}
			if m.overlay != overlayNone || len(f.writes(t)) != 0 {
				t.Errorf("overlay = %v, writes = %q", m.overlay, f.writes(t))
			}
		})
	}
}

// Criterion 7: y copies the export and the TUI stays open; herdr is not called.
func TestYCopiesTheExport(t *testing.T) {
	f := fakeHerdr(t, agentPane, listed)
	clipboard := fakeClipboard(t)
	for _, screen := range []string{"search", "buffer"} {
		m := buffered(t)
		if screen == "buffer" {
			m, _ = press(m, "b")
		}
		*clipboard = nil
		m, cmd := press(m, "y")
		m, follow := answer(t, m, cmd)
		if quits(follow) || len(*clipboard) != 1 || (*clipboard)[0] != exportText(m.buf.Entries()) {
			t.Errorf("%s: clipboard = %q, quit = %v", screen, *clipboard, quits(follow))
		}
		if m.toast == nil || !strings.Contains(m.toast.title, "copied 3 entries") {
			t.Errorf("%s: toast = %+v", screen, m.toast)
		}
	}
	if len(f.calls(t)) != 0 {
		t.Errorf("herdr called: %q", f.calls(t))
	}
}

// y types in the query field.
func TestYTypesInTheQueryField(t *testing.T) {
	clipboard := fakeClipboard(t)
	m, _ := press(buffered(t), "/", "y")
	if !strings.HasSuffix(m.query.Value(), "y") || len(*clipboard) != 0 {
		t.Errorf("query = %q, clipboard = %q", m.query.Value(), *clipboard)
	}
}

// Criterion 8: an empty buffer sends and copies nothing and shows a toast.
func TestEmptyBufferSendsNothing(t *testing.T) {
	f := fakeHerdr(t, agentPane, listed)
	clipboard := fakeClipboard(t)
	for _, k := range []string{"ctrl+s", "y"} {
		m := searchedOnFixture(t, "unused")
		if k == "y" {
			m, _ = press(m, k)
		} else {
			m, _ = ctrlS(m)
		}
		if m.toast == nil || !strings.Contains(m.toast.title, "empty") || m.handoffBusy {
			t.Errorf("%s: toast = %+v, busy = %v", k, m.toast, m.handoffBusy)
		}
	}
	if len(*clipboard) != 0 || len(f.calls(t)) != 0 {
		t.Errorf("clipboard = %q, herdr calls = %q", *clipboard, f.calls(t))
	}
}

// A failed send shows an error toast and the TUI stays open with its buffer.
func TestFailedSendStaysOpen(t *testing.T) {
	f := fakeHerdr(t, agentPane, listed)
	f.fail(t)
	m, cmd := ctrlS(buffered(t))
	m, follow := answer(t, m, cmd)
	if quits(follow) {
		t.Error("the TUI exited after a failed send")
	}
	if m.toast == nil || m.toast.kind != toastError || !strings.Contains(m.toast.context, "pane gone") {
		t.Errorf("toast = %+v", m.toast)
	}
	if len(m.buf.entries) != 3 || m.handoffBusy {
		t.Errorf("buffer = %d entries, busy = %v", len(m.buf.entries), m.handoffBusy)
	}
}

// The text box captures ctrl+s first: it saves the note and hands nothing off.
func TestCtrlSInTheTextBoxSavesTheNote(t *testing.T) {
	f := fakeHerdr(t, agentPane, listed)
	m := addHits(t, searchedOnFixture(t, "unused"), 0)
	m, _ = press(m, "n", "hello")
	m, _ = ctrlS(m)
	if m.overlay != overlayNone || m.buf.entries[0].Note != "hello" || len(f.calls(t)) != 0 {
		t.Errorf("overlay = %v, note = %q, herdr calls = %q", m.overlay, m.buf.entries[0].Note, f.calls(t))
	}
}

// A TUI in a plain herdr pane has no HERDR_ACTIVE_PANE_ID: its own pane, HERDR_PANE_ID, is the
// one asked, and it runs no agent, so the picker opens.
func TestOwnPaneIsAskedWithoutAnActivePane(t *testing.T) {
	f := fakeHerdr(t, noAgentPane, listed)
	t.Setenv("HERDR_ACTIVE_PANE_ID", "")
	t.Setenv("HERDR_PANE_ID", "wA:p9")
	m, cmd := ctrlS(buffered(t))
	m, _ = answer(t, m, cmd)
	calls := f.calls(t)
	if m.overlay != overlayAgents || len(calls) < 1 || fmt.Sprint(calls[0]) != "[pane get wA:p9]" {
		t.Errorf("overlay = %v, calls = %q: want `pane get wA:p9`, then the picker", m.overlay, calls)
	}
}

// A second ctrl+s while the first resolves starts nothing; the answer frees the key again.
func TestSecondCtrlSWhileResolvingIsIgnored(t *testing.T) {
	f := fakeHerdr(t, noAgentPane, listed)
	m, cmd := ctrlS(buffered(t))
	m, again := ctrlS(m)
	if again != nil || m.toast != nil {
		t.Errorf("second ctrl+s: cmd = %v, toast = %+v", again != nil, m.toast)
	}
	m, _ = answer(t, m, cmd)
	if m.handoffBusy || m.overlay != overlayAgents {
		t.Errorf("busy = %v, overlay = %v after the answer", m.handoffBusy, m.overlay)
	}
	if n := len(f.calls(t)); n != 2 { // one pane get, one agent list
		t.Errorf("herdr calls = %q, want one resolution", f.calls(t))
	}
}

// ctrl+s sends from the query field too, so the footer names it there once the buffer has entries.
func TestFooterNamesCtrlSInTheQueryField(t *testing.T) {
	m, _ := press(buffered(t), "/")
	if !strings.Contains(m.View(), "ctrl+s") {
		t.Errorf("footer lacks ctrl+s in the query field:\n%s", m.View())
	}
}
