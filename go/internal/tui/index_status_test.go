package tui

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"

	"nas/volume1/data/git/okf-tools/go/internal/tagvec"
	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// settleIndex runs cmd and every command it spawns and feeds the index messages to Update. Cursor blink
// ticks and toast timers are not fed (they would never end); a command that takes longer than a
// second is left out. It returns the final model.
func settleIndex(m model, cmd tea.Cmd) model {
	pending := []tea.Cmd{cmd}
	for len(pending) > 0 {
		running := pending
		pending = nil
		msgs := make(chan tea.Msg, len(running))
		n := 0
		for _, c := range running {
			if c != nil {
				n++
				go func() { msgs <- c() }()
			}
		}
		deadline := time.After(time.Second)
	collect:
		for ; n > 0; n-- {
			select {
			case msg := <-msgs:
				if batch, ok := msg.(tea.BatchMsg); ok {
					pending = append(pending, batch...)
					continue
				}
				switch msg.(type) {
				case indexCheckedMsg, indexRefreshedMsg, semanticPlanMsg:
					next, c := m.Update(msg)
					m = next.(model)
					pending = append(pending, c)
				}
			case <-deadline:
				break collect
			}
		}
	}
	return m
}

// fakeEmbedder replaces the Voyage backend: it records every call and the number of texts, and
// fails with err when set.
type fakeEmbedder struct {
	mu    sync.Mutex
	calls int
	texts int
	err   error
}

func (f *fakeEmbedder) embed(texts []string) ([][]float32, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	f.texts += len(texts)
	out := make([][]float32, len(texts))
	for i := range out {
		out[i] = make([]float32, tagvec.Dim(tagvec.SemanticModel))
	}
	return out, nil
}

func (f *fakeEmbedder) seen() (calls, texts int) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.calls, f.texts
}

// withFake puts a fake embedder in place of Voyage; with key it also sets a dummy API key. No test
// reaches the network: without the fake the key stays unset.
func withFake(t *testing.T, key bool) *fakeEmbedder {
	t.Helper()
	f := &fakeEmbedder{}
	old := embedVectors
	embedVectors = f.embed
	t.Cleanup(func() { embedVectors = old })
	if key {
		t.Setenv("VOYAGE_API_KEY", "dummy")
	} else {
		t.Setenv("VOYAGE_API_KEY", "")
	}
	return f
}

// started is the model on root after the start checks have run.
func started(t *testing.T, root string) model {
	t.Helper()
	m := newModel(root, defaultSettings(), nil)
	next, _ := m.Update(tea.WindowSizeMsg{Width: goldenWidth, Height: goldenHeight})
	m = next.(model)
	return settleIndex(m, m.Init())
}

// leaveField moves the focus from the query field to the results pane, where `r` acts.
func leaveField(m model) model {
	m, _ = press(m, "esc")
	return m
}

func TestDotsAtStart(t *testing.T) {
	withFake(t, false)
	root := fixtureRoot(t)
	m := newModel(root, defaultSettings(), nil)
	if m.lexical.state != indexUnknown || m.semantic.state != indexUnknown {
		t.Fatal("the dots start grey before a check ran")
	}
	init := m.Init()
	if init == nil {
		t.Fatal("Init starts the checks as commands, off the UI loop")
	}
	if !strings.Contains(m.View(), "lexical") || !strings.Contains(m.View(), "semantic") {
		t.Errorf("the header shows no labelled dots:\n%s", m.View())
	}
	m = settleIndex(m, init)
	if m.lexical.state != indexAbsent {
		t.Errorf("lexical dot = %v, want red (absent): the fixture has no .fts", m.lexical.state)
	}
	if m.semantic.state != indexUnknown {
		t.Errorf("semantic dot = %v, want grey: no API key", m.semantic.state)
	}
}

func TestDotColours(t *testing.T) {
	for s, want := range map[indexState]string{
		indexUnknown: string(theme.Overlay),
		indexCurrent: string(theme.Green),
		indexStale:   string(theme.Yellow),
		indexAbsent:  string(theme.Red),
	} {
		if got := string(s.color()); got != want {
			t.Errorf("state %d colour = %s, want %s", s, got, want)
		}
	}
}

// The lexical dot is red without an index, green after the build, yellow once a concept is added.
func TestLexicalDotFollowsTheIndex(t *testing.T) {
	withFake(t, false)
	root := fixtureRoot(t)
	m := started(t, root)
	if m.lexical.state != indexAbsent {
		t.Fatalf("before the build: %v, want red", m.lexical.state)
	}
	m = settleIndex(m, checkIndex(root, indexLexical))
	m, cmd := m.startLexical()
	m = settleIndex(m, cmd)
	if m.lexical.state != indexCurrent {
		t.Fatalf("after the build: %v, want green", m.lexical.state)
	}
	extra := "---\ntype: Rule\ndescription: Extra\n---\n\n# Extra\n"
	if err := os.WriteFile(filepath.Join(root, "kc-gov", "extra.md"), []byte(extra), 0o644); err != nil {
		t.Fatal(err)
	}
	m = settleIndex(m, checkIndex(root, indexLexical))
	if m.lexical.state != indexStale {
		t.Errorf("after a new concept: %v, want yellow", m.lexical.state)
	}
}

func TestLexicalRefreshBuildsTheIndex(t *testing.T) {
	withFake(t, false)
	root := fixtureRoot(t)
	m := leaveField(started(t, root))
	m, _ = press(m, "r")
	if m.overlay != overlayRefresh {
		t.Fatal("r opens the refresh dialog outside the query field")
	}
	m, cmd := press(m, "l")
	if m.overlay != overlayNone || cmd == nil || !m.lexical.busy {
		t.Fatalf("l starts the lexical refresh at once: overlay %v busy %v", m.overlay, m.lexical.busy)
	}
	if m.lexical.state != indexAbsent {
		t.Error("the dot keeps its colour while the build runs")
	}
	if !strings.Contains(m.View(), "◐") {
		t.Error("a running refresh is visible in the header")
	}
	m = settleIndex(m, cmd)
	if m.lexical.state != indexCurrent || m.lexical.busy {
		t.Errorf("after the build: state %v busy %v, want green and idle", m.lexical.state, m.lexical.busy)
	}
	if _, err := os.Stat(filepath.Join(root, ".fts", "fts.sqlite")); err != nil {
		t.Errorf("no FTS index written: %v", err)
	}
	if m.toast == nil || m.toast.kind != toastInfo {
		t.Errorf("toast = %+v, want an info toast", m.toast)
	}
}

func TestRKeyTypesInTheQueryField(t *testing.T) {
	withFake(t, false)
	m := sized(t, nil)
	m, _ = press(m, "r")
	if m.overlay != overlayNone || m.query.Value() != "r" {
		t.Errorf("r inside the field must type: overlay %v value %q", m.overlay, m.query.Value())
	}
}

// The semantic refresh asks before it embeds, naming the number of concepts, and embeds them
// after the confirmation.
func TestSemanticRefreshAsksThenEmbeds(t *testing.T) {
	fake := withFake(t, true)
	root := fixtureRoot(t)
	m := leaveField(started(t, root))
	if m.semantic.state != indexAbsent {
		t.Fatalf("semantic dot = %v, want red: key set, no store", m.semantic.state)
	}
	m, _ = press(m, "r")
	m, cmd := press(m, "s")
	m = settleIndex(m, cmd)
	if m.overlay != overlayConfirm || m.confirm.kind != confirmSemanticRefresh {
		t.Fatalf("overlay = %v, want the semantic confirm dialog", m.overlay)
	}
	var n int
	if _, err := fmt.Sscanf(m.confirm.body, "Embed %d concept(s)", &n); err != nil || n == 0 {
		t.Fatalf("the dialog names no concept count: %q", m.confirm.body)
	}
	if calls, _ := fake.seen(); calls != 0 {
		t.Fatalf("%d embedding calls before the confirmation", calls)
	}
	// Cancel: still nothing embedded.
	c, _ := press(m, "n")
	if calls, _ := fake.seen(); calls != 0 || c.overlay != overlayNone {
		t.Fatalf("cancel: %d calls, overlay %v", calls, c.overlay)
	}
	m, cmd = press(m, "enter")
	m = settleIndex(m, cmd)
	if _, texts := fake.seen(); texts != n {
		t.Errorf("embedded %d texts, the dialog named %d", texts, n)
	}
	if m.semantic.state != indexCurrent || m.semantic.busy {
		t.Errorf("after the embedding: state %v busy %v, want green and idle", m.semantic.state, m.semantic.busy)
	}
}

// A partly embedded store is yellow.
func TestSemanticDotPartial(t *testing.T) {
	withFake(t, true)
	root := fixtureRoot(t)
	m := started(t, root)
	m, cmd := m.startSemantic()
	m = settleIndex(m, cmd)
	if m.semantic.state != indexCurrent {
		t.Fatalf("after the embedding: %v, want green", m.semantic.state)
	}
	extra := "---\ntype: Rule\ndescription: Extra\n---\n\n# Extra\n"
	if err := os.WriteFile(filepath.Join(root, "kc-gov", "extra.md"), []byte(extra), 0o644); err != nil {
		t.Fatal(err)
	}
	m = settleIndex(m, checkIndex(root, indexSemantic))
	if m.semantic.state != indexStale {
		t.Errorf("one concept unembedded: %v, want yellow", m.semantic.state)
	}
}

func TestSemanticRefreshFailureKeepsTheDot(t *testing.T) {
	fake := withFake(t, true)
	fake.err = &tagvec.Exception{Class: "VoyageError", Message: "boom"}
	root := fixtureRoot(t)
	m := started(t, root)
	before := m.semantic.state
	m, cmd := m.startSemantic()
	m = settleIndex(m, cmd)
	if m.semantic.state != before || m.semantic.busy {
		t.Errorf("state %v busy %v, want the old colour %v and idle", m.semantic.state, m.semantic.busy, before)
	}
	if m.toast == nil || m.toast.kind != toastError || !strings.Contains(m.toast.context, "boom") {
		t.Errorf("toast = %+v, want an error toast with the cause", m.toast)
	}
}

func TestLexicalRefreshFailureKeepsTheDot(t *testing.T) {
	withFake(t, false)
	root := fixtureRoot(t)
	// A file in place of the index directory makes the build fail.
	if err := os.WriteFile(filepath.Join(root, ".fts"), nil, 0o644); err != nil {
		t.Fatal(err)
	}
	m := started(t, root)
	before := m.lexical.state
	m, cmd := m.startLexical()
	m = settleIndex(m, cmd)
	if m.lexical.state != before || m.lexical.busy {
		t.Errorf("state %v busy %v, want the old colour %v and idle", m.lexical.state, m.lexical.busy, before)
	}
	if m.toast == nil || m.toast.kind != toastError || !m.toast.sticky {
		t.Errorf("toast = %+v, want a sticky error toast", m.toast)
	}
}

// Without the API key the semantic dot is grey and the refresh names the key instead of running.
func TestSemanticWithoutKey(t *testing.T) {
	fake := withFake(t, false)
	m := leaveField(started(t, fixtureRoot(t)))
	if m.semantic.state != indexUnknown {
		t.Errorf("semantic dot = %v, want grey", m.semantic.state)
	}
	m, _ = press(m, "r")
	if !strings.Contains(m.View(), "VOYAGE_API_KEY") {
		t.Error("the dialog does not name the missing key")
	}
	m, cmd := press(m, "s")
	m = settleIndex(m, cmd)
	if m.overlay != overlayNone || m.semantic.busy {
		t.Errorf("the refresh ran: overlay %v busy %v", m.overlay, m.semantic.busy)
	}
	if m.toast == nil || !strings.Contains(m.toast.context, "VOYAGE_API_KEY") {
		t.Errorf("toast = %+v, want one naming VOYAGE_API_KEY", m.toast)
	}
	if calls, _ := fake.seen(); calls != 0 {
		t.Errorf("%d embedding calls without a key", calls)
	}
}

// A root switch rechecks both dots for the new root; a result of the old root is dropped.
func TestRootSwitchRechecks(t *testing.T) {
	withFake(t, true)
	a, b := fixtureRoot(t), fixtureRoot(t)
	m := started(t, a)
	m, cmd := m.startLexical()
	m = settleIndex(m, cmd)
	if m.lexical.state != indexCurrent {
		t.Fatalf("root A lexical = %v, want green", m.lexical.state)
	}
	slow := checkIndex(a, indexLexical) // still running when the switch happens
	m, cmd = m.setRoot(b)
	if m.root != b || m.lexical.state != indexUnknown || m.semantic.state != indexUnknown {
		t.Fatalf("the switch keeps the dots of the old root: %+v %+v", m.lexical, m.semantic)
	}
	if cmd == nil {
		t.Fatal("the switch starts no recheck")
	}
	m = settleIndex(m, slow)
	if m.lexical.state != indexUnknown {
		t.Error("a result of the old root changed the dot")
	}
	m = settleIndex(m, cmd)
	if m.lexical.state != indexAbsent || m.semantic.state != indexAbsent {
		t.Errorf("root B: lexical %v semantic %v, want both red", m.lexical.state, m.semantic.state)
	}
}

func TestRefreshDialogGolden(t *testing.T) {
	withFake(t, false)
	m := leaveField(sized(t, nil))
	m, _ = press(m, "r")
	assertGolden(t, "refresh_dialog", m)
}

// A second refresh of an index that is still being refreshed does not start; a toast says why.
func TestRefreshWhileBusyDoesNotStartAgain(t *testing.T) {
	withFake(t, true)
	root := fixtureRoot(t)
	m := started(t, root)
	busy := func(m model, title string) {
		t.Helper()
		if m.toast == nil || m.toast.kind != toastWarn || !strings.Contains(m.toast.title, "busy") {
			t.Errorf("%s: toast = %+v, want the busy warning", title, m.toast)
		}
	}
	m, lex := m.startLexical()
	again, _ := m.startLexical()
	busy(again, "lexical")
	m = settleIndex(m, lex)

	m, sem := m.startSemantic()
	again, _ = m.startSemantic()
	busy(again, "semantic")
	again, _ = m.startSemanticPlan()
	busy(again, "semantic plan")
	settleIndex(m, sem)
}

// With every concept embedded, the semantic refresh opens no confirm dialog and says so.
func TestSemanticRefreshNothingToEmbed(t *testing.T) {
	withFake(t, true)
	root := fixtureRoot(t)
	m := started(t, root)
	m, cmd := m.startSemantic()
	m = leaveField(settleIndex(m, cmd))
	m, _ = press(m, "r")
	m, cmd = press(m, "s")
	m = settleIndex(m, cmd)
	if m.overlay != overlayNone {
		t.Errorf("overlay = %v, want none: nothing to embed", m.overlay)
	}
	if m.toast == nil || !strings.Contains(m.toast.title, "current") {
		t.Errorf("toast = %+v, want one saying the index is current", m.toast)
	}
}

// A refresh or a plan that ends after a root switch changes nothing for the new root.
func TestRefreshOfAnOldRootIsDropped(t *testing.T) {
	withFake(t, true)
	a, b := fixtureRoot(t), fixtureRoot(t)
	m := started(t, a)
	m, lex := m.startLexical()
	m, plan := m.startSemanticPlan()
	m, _ = m.setRoot(b)
	m = settleIndex(m, tea.Batch(lex, plan))
	if m.overlay == overlayConfirm {
		t.Error("the plan of the old root opened the confirm dialog")
	}
	if m.toast != nil && strings.Contains(m.toast.title, "refreshed") {
		t.Errorf("toast = %+v: the refresh of the old root reported on the new one", m.toast)
	}
}

// A failed check keeps the dot as it was and shows the error.
func TestCheckFailureKeepsTheDot(t *testing.T) {
	withFake(t, true)
	root := fixtureRoot(t)
	m := started(t, root)
	m, cmd := m.startSemantic()
	m = settleIndex(m, cmd)
	if m.semantic.state != indexCurrent {
		t.Fatalf("after the embedding: %v, want green", m.semantic.state)
	}
	concept := filepath.Join(root, "kc-gov", "naming.md")
	if err := os.Chmod(concept, 0); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chmod(concept, 0o644) })
	m = settleIndex(m, checkIndex(root, indexSemantic))
	if m.semantic.state != indexCurrent {
		t.Errorf("state %v, want the old colour green", m.semantic.state)
	}
	if m.toast == nil || m.toast.kind != toastError || !m.toast.sticky {
		t.Errorf("toast = %+v, want a sticky error toast", m.toast)
	}
}

// While the start check runs, a refresh does not start (it would race the check), and a check
// result never clears the busy mark of a refresh that runs: a second refresh stays refused.
func TestRefreshWaitsForCheckAndCheckKeepsRefreshBusy(t *testing.T) {
	withFake(t, true)
	root := fixtureRoot(t)

	early := newModel(root, defaultSettings(), nil)
	early = leaveField(early)
	early, _ = press(early, "r")
	early, _ = press(early, "l")
	if early.lexical.busy || early.toast == nil || !strings.Contains(early.toast.title, "busy") {
		t.Fatalf("r l before the start check returned: busy %v toast %+v, want a busy warning and no build",
			early.lexical.busy, early.toast)
	}

	m := started(t, root)
	m, build := m.startLexical()
	next, _ := m.Update(indexCheckedMsg{root: root, kind: indexLexical, state: indexAbsent})
	m = next.(model)
	if !m.lexical.busy {
		t.Fatal("a check result cleared the busy mark of the running build")
	}
	again, againCmd := m.startLexical()
	if againCmd != nil || !strings.Contains(again.toast.title, "busy") {
		t.Fatal("a second build started while the first one runs")
	}
	m = settleIndex(m, build)
	if m.lexical.busy || m.lexical.checking || m.lexical.state != indexCurrent {
		t.Errorf("after the build: %+v, want green and idle", m.lexical)
	}

	m, sem := m.startSemantic()
	next, _ = m.Update(indexCheckedMsg{root: root, kind: indexSemantic, state: indexAbsent})
	m = next.(model)
	if !m.semantic.busy {
		t.Fatal("a check result cleared the busy mark of the running embedding")
	}
	settleIndex(m, sem)
}
