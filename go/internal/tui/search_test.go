package tui

import (
	"errors"
	"slices"
	"strings"
	"sync"
	"testing"

	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
	"github.com/muesli/termenv"

	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/find"
	"nas/volume1/data/git/okf-tools/go/internal/navigation"
	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// searchQueries are queries with several hits on the fixture catalogue, in lexical mode.
var searchQueries = []string{"deploy", "security", "the", "ops incident", "recipe"}

// onFixture is a start model on a copy of the fixture catalogue, sized w×h. The Voyage key is
// off, so no search reaches the network.
func onFixture(t *testing.T, w, h int) model {
	t.Helper()
	t.Setenv("VOYAGE_API_KEY", "")
	next, _ := newModel(fixtureRoot(t), defaultSettings(), nil).Update(tea.WindowSizeMsg{Width: w, Height: h})
	return next.(model)
}

// settle runs the commands cmd stands for, feeds the answers back and returns the model. Commands
// the answers return (timers) and spinner ticks are dropped.
func settle(t *testing.T, m model, cmd tea.Cmd) model {
	t.Helper()
	if cmd == nil {
		return m
	}
	msg := cmd()
	if batch, ok := msg.(tea.BatchMsg); ok {
		for _, c := range batch {
			m = settle(t, m, c)
		}
		return m
	}
	if _, tick := msg.(spinner.TickMsg); tick || msg == nil {
		return m
	}
	next, _ := m.Update(msg) // the follow-up is a timer: not run
	return next.(model)
}

// search types query into the field and presses enter; done is the model after the answer.
func search(t *testing.T, m model, query string) (running model, done model) {
	t.Helper()
	running, cmd := press(m, query, "enter")
	return running, settle(t, running, cmd)
}

var (
	appOnce sync.Once
	app     *cli.App
)

// testApp is the command line of okf with the commands the tests compare against. Commands
// register once per process.
func testApp() *cli.App {
	appOnce.Do(func() {
		app = cli.NewApp()
		find.Register(app)
		navigation.Register(app)
	})
	return app
}

// cliPaths are the paths `okf find <query> --limit 50 [extra...]` lists, in order, from the
// command's own handler.
func cliPaths(t *testing.T, root, query string, extra ...string) []string {
	t.Helper()
	parsed, err := testApp().Parse(append([]string{"find", query, "--limit", "50", "--json"}, extra...))
	if err != nil {
		t.Fatal(err)
	}
	data, err := parsed.Handler(root, parsed.Args)
	if err != nil {
		t.Fatal(err)
	}
	hits, _ := data.(envelope.Obj).Get("hits")
	var paths []string
	for _, h := range hits.([]envelope.Obj) {
		p, _ := h.Get("path")
		paths = append(paths, p.(string))
	}
	return paths
}

func hitPaths(m model) []string {
	var paths []string
	for _, h := range m.search.hits {
		paths = append(paths, h.Path)
	}
	return paths
}

// US 3, criterion 1: enter lists the hits of `okf find <query> --limit 50` in the same order.
func TestEnterListsTheHitsOfOkfFind(t *testing.T) {
	m := onFixture(t, 200, 40)
	for _, q := range searchQueries {
		_, done := search(t, m, q)
		want := cliPaths(t, m.root, q)
		if got := hitPaths(done); !slices.Equal(got, want) {
			t.Errorf("query %q: list = %v, want the CLI order %v", q, got, want)
		}
		// The list column of the screen shows the titles in the same order.
		lw, _, _ := done.geometry()
		var column []string
		for _, line := range strings.Split(done.View(), "\n") {
			column = append(column, line[:min(len(line), lw)])
		}
		last := 0
		for i, h := range done.search.hits {
			at := slices.IndexFunc(column[last:], func(l string) bool { return strings.Contains(l, h.Title) })
			if at < 0 {
				t.Errorf("query %q: list column lacks hit %d %q after row %d", q, i, h.Title, last)
				break
			}
			last += at + 1
		}
	}
	if len(cliPaths(t, m.root, "deploy")) < 2 {
		t.Fatal("fixture gives fewer than two hits for deploy: the order proves nothing")
	}
}

// Criterion 9: typing never starts a search.
func TestTypingStartsNoSearch(t *testing.T) {
	m, cmd := press(onFixture(t, 100, 30), "deploy", " ", "ops")
	if m.search.running || m.search.seq != 0 || m.search.ran {
		t.Errorf("search state after typing = %+v, want none started", m.search)
	}
	if got := settle(t, m, cmd); got.search.ran || len(got.search.hits) != 0 {
		t.Errorf("typing produced hits: %+v", got.search)
	}
}

// Criterion 4: while a search runs the keys still act and an indicator shows.
func TestRunningSearchKeepsReactingToKeys(t *testing.T) {
	m, cmd := press(onFixture(t, 100, 30), "deploy", "enter")
	if !m.search.running || !strings.Contains(m.View(), "searching") {
		t.Fatalf("running = %v; want a running search with an indicator:\n%s", m.search.running, m.View())
	}
	m, _ = press(m, "?")
	if m.overlay != overlayHelp {
		t.Errorf("? during the search: overlay = %v, want the help", m.overlay)
	}
	m, _ = press(m, "esc")
	m, _ = press(m, "/", "x")
	if m.focus != focusQuery || !strings.HasSuffix(m.query.Value(), "x") {
		t.Errorf("/ and typing during the search: focus = %v, query = %q", m.focus, m.query.Value())
	}
	m = settle(t, m, cmd)
	if m.search.running || strings.Contains(m.View(), "searching") {
		t.Errorf("indicator stays after the answer:\n%s", m.View())
	}
	if len(m.search.hits) == 0 {
		t.Error("the answer of the search did not arrive")
	}
}

// Criterion 2 and 8: the detail pane shows every field of the focused hit and its H2/H3 contents.
func TestDetailPaneShowsTheFocusedHit(t *testing.T) {
	m := onFixture(t, 400, 40)
	_, m = search(t, m, "deploy")
	h := m.search.focused()
	if h == nil {
		t.Fatal("no hit")
	}
	rows := strings.Join(m.detailRows(400), "\n")
	for _, want := range []string{
		h.Title, "type", h.Type, "bundle", h.Bundle, "tags", strings.Join(h.Tags, ", "), "provenance", h.Provenance,
		"tier", h.Tier, "stale", "no", "path", h.Abs, "description", h.Description, "snippet", h.Snippet, "Contents",
	} {
		if !strings.Contains(rows, want) {
			t.Errorf("detail pane lacks %q:\n%s", want, rows)
		}
	}
	if h.Type == "" || h.Description == "" || h.Snippet == "" || len(h.Tags) == 0 {
		t.Errorf("hit %+v: fixture hit should have type, description, snippet and tags", h)
	}
	if !strings.HasPrefix(h.Abs, m.root+"/") || !strings.HasSuffix(h.Abs, h.Path+".md") {
		t.Errorf("Abs = %q, want <root>/<path>.md", h.Abs)
	}
	if !strings.Contains(m.View(), h.Abs) {
		t.Errorf("the absolute path is not on screen:\n%s", m.View())
	}
}

// tocLevels2and3 is `okf toc <path> --level 0` filtered to H2 and H3, as "level text".
func tocLevels2and3(t *testing.T, root, path string) []string {
	t.Helper()
	parsed, err := testApp().Parse([]string{"toc", path, "--level", "0", "--json"})
	if err != nil {
		t.Fatal(err)
	}
	data, err := parsed.Handler(root, parsed.Args)
	if err != nil {
		t.Fatal(err)
	}
	heads, _ := data.(envelope.Obj).Get("headings")
	var out []string
	for _, h := range heads.([]envelope.Obj) {
		level, _ := h.Get("level")
		text, _ := h.Get("text")
		if level == 2 || level == 3 {
			out = append(out, text.(string))
		}
	}
	return out
}

// Criterion 8: the contents of every hit are the H2/H3 headings `okf toc --level 0` returns, in
// document order.
func TestDetailContentsMatchOkfToc(t *testing.T) {
	m := onFixture(t, 200, 40)
	withHeadings := 0
	for _, q := range searchQueries {
		_, done := search(t, m, q)
		for i := range done.search.hits {
			done = done.moveCursor(i)
			var got []string
			for _, h := range done.search.headings {
				got = append(got, h.Text)
			}
			path := done.search.hits[i].Path
			want := tocLevels2and3(t, m.root, path)
			if !slices.Equal(got, want) {
				t.Errorf("%s: contents = %v, want %v", path, got, want)
			}
			if len(want) > 0 {
				withHeadings++
				rows := strings.Join(done.detailRows(200), "\n")
				at := -1
				for _, text := range want {
					next := strings.Index(rows[max(at, 0):], "- "+text)
					if next < 0 {
						t.Errorf("%s: detail lacks heading %q in order:\n%s", path, text, rows)
						break
					}
					at = max(at, 0) + next + 1
				}
			}
		}
	}
	if withHeadings == 0 {
		t.Fatal("no fixture hit has H2/H3 headings: the test proves nothing")
	}
}

// Criterion 3: j/k and the arrow keys move the focus by one hit and the detail pane follows.
func TestCursorMovesAndDetailFollows(t *testing.T) {
	_, m := search(t, onFixture(t, 200, 40), "the")
	if len(m.search.hits) < 3 {
		t.Fatalf("fixture gives %d hits for the, want at least 3", len(m.search.hits))
	}
	if m.focus != focusList {
		t.Fatalf("focus after the search = %v, want the list", m.focus)
	}
	steps := []struct {
		key  string
		want int
	}{{"j", 1}, {"down", 2}, {"k", 1}, {"up", 0}, {"k", 0}, {"G", len(m.search.hits) - 1}, {"j", len(m.search.hits) - 1}, {"g", 0}}
	for _, s := range steps {
		if s.key == "down" {
			m, _ = pressKey(m, tea.KeyDown)
		} else if s.key == "up" {
			m, _ = pressKey(m, tea.KeyUp)
		} else {
			m, _ = press(m, s.key)
		}
		if m.search.cursor != s.want {
			t.Fatalf("after %s: cursor = %d, want %d", s.key, m.search.cursor, s.want)
		}
		h := m.search.hits[s.want]
		if rows := strings.Join(m.detailRows(200), "\n"); !strings.Contains(rows, h.Abs) {
			t.Errorf("after %s: detail pane shows another hit, want path %s:\n%s", s.key, h.Abs, rows)
		}
	}
}

func pressKey(m model, t tea.KeyType) (model, tea.Cmd) {
	next, cmd := m.Update(tea.KeyMsg{Type: t})
	return next.(model), cmd
}

// Criterion 5: a warning of the ranking shows as a toast. The fixture has no lexical index, which
// the ranking announces.
func TestWarningShowsAsToast(t *testing.T) {
	_, m := search(t, onFixture(t, 100, 30), "deploy")
	if m.toast == nil || m.toast.kind != toastWarn || !strings.Contains(m.toast.title, "lexical index absent") {
		t.Fatalf("toast = %+v, want the warning of the missing lexical index", m.toast)
	}
	if !strings.Contains(m.View(), "lexical index absent") {
		t.Errorf("the toast is not on screen:\n%s", m.View())
	}
}

// Criterion 6: no hit says so in the list area.
func TestNoHitsSaysSo(t *testing.T) {
	_, m := search(t, onFixture(t, 100, 30), "zzzqqqxxx")
	if len(m.search.hits) != 0 {
		t.Fatalf("hits = %d, want none", len(m.search.hits))
	}
	if out := m.View(); !strings.Contains(out, `No hits for "zzzqqqxxx".`) {
		t.Errorf("view does not say there is no hit:\n%s", out)
	}
}

// A query without a searchable term finds nothing and says so like any other empty search.
func TestQueryWithoutTermsSaysNoHits(t *testing.T) {
	_, m := search(t, onFixture(t, 100, 30), "!!")
	if !m.search.ran || len(m.search.hits) != 0 || m.search.running {
		t.Fatalf("search state = %+v, want a finished search without hits", m.search)
	}
	if out := m.View(); !strings.Contains(out, `No hits for "!!".`) {
		t.Errorf("view does not say there is no hit:\n%s", out)
	}
}

// A failed search shows an error toast, ends the running indicator and keeps the old list.
func TestFailedSearchShowsErrorToast(t *testing.T) {
	_, m := search(t, onFixture(t, 100, 30), "deploy")
	before := hitPaths(m)
	m, _ = press(m, "/", " ", "x", "enter")
	if !m.search.running {
		t.Fatal("second search did not start")
	}
	next, _ := m.Update(searchDoneMsg{seq: m.search.seq, query: "deploy x", err: errors.New("boom")})
	m = next.(model)
	if m.search.running || strings.Contains(m.View(), "searching") {
		t.Error("the running indicator stays after the failure")
	}
	if m.toast == nil || m.toast.kind != toastError || m.toast.title != "Search failed" || m.toast.context != "boom" {
		t.Fatalf("toast = %+v, want the error toast naming the failure", m.toast)
	}
	if got := hitPaths(m); !slices.Equal(got, before) {
		t.Errorf("list after the failure = %v, want the old list %v", got, before)
	}
}

// Criterion 7: a second search replaces the list and the query stays editable.
func TestSecondSearchReplacesTheList(t *testing.T) {
	_, m := search(t, onFixture(t, 200, 40), "deploy")
	first := hitPaths(m)
	m, _ = press(m, "/")
	if m.focus != focusQuery || !m.query.Focused() || m.query.Value() != "deploy" {
		t.Fatalf("after /: focus = %v, query = %q; want the query field, still holding the query", m.focus, m.query.Value())
	}
	m, cmd := press(m, " ", "security", "enter")
	m = settle(t, m, cmd)
	if m.query.Value() != "deploy security" {
		t.Errorf("query = %q, want the edited text", m.query.Value())
	}
	want := cliPaths(t, m.root, "deploy security")
	if got := hitPaths(m); !slices.Equal(got, want) || slices.Equal(got, first) {
		t.Errorf("second list = %v, want %v, different from the first %v", got, want, first)
	}
	if m.search.cursor != 0 {
		t.Errorf("cursor = %d after a new search, want 0", m.search.cursor)
	}
}

// An answer of an older search never replaces the answer of a newer one.
func TestOlderAnswerIsDropped(t *testing.T) {
	m := onFixture(t, 100, 30)
	m, first := press(m, "deploy", "enter")
	m, _ = press(m, "/")
	m.query.SetValue("security")
	m, second := press(m, "enter")
	m = settle(t, m, second)
	want := hitPaths(m)
	m = settle(t, m, first)
	if got := hitPaths(m); !slices.Equal(got, want) || m.search.query != "security" {
		t.Errorf("after the late answer: query %q hits %v, want %v", m.search.query, got, want)
	}
}

// A blank query starts nothing.
func TestBlankQueryStartsNoSearch(t *testing.T) {
	m, cmd := press(onFixture(t, 100, 30), " ", "enter")
	if m.search.running || cmd != nil && m.search.seq != 0 {
		t.Errorf("blank query: search = %+v", m.search)
	}
	if m.focus != focusQuery {
		t.Errorf("focus = %v, want the query field", m.focus)
	}
}

// v steps through split, list and detail layouts and wraps; V steps back.
func TestLayoutCycle(t *testing.T) {
	_, m := search(t, onFixture(t, 200, 40), "deploy")
	for _, step := range []struct {
		key    string
		layout layoutMode
	}{{"v", layoutList}, {"v", layoutDetail}, {"v", layoutSplit}, {"V", layoutDetail}} {
		m, _ = press(m, step.key)
		if m.layout != step.layout {
			t.Fatalf("after %s: layout = %v, want %v", step.key, m.layout, step.layout)
		}
		out := m.View()
		hasDetail := strings.Contains(out, "provenance")
		hasList := strings.Contains(out, "▸ ")
		if hasDetail != (step.layout != layoutList) || hasList != (step.layout != layoutDetail) {
			t.Errorf("layout %v: detail shown = %v, list shown = %v:\n%s", step.layout, hasDetail, hasList, out)
		}
	}
}

// ctrl+d and ctrl+u scroll a detail pane taller than the screen; a new cursor position resets it.
func TestDetailScrolls(t *testing.T) {
	_, m := search(t, onFixture(t, 100, 12), "deploy")
	if len(m.detailRows(m.detailTextWidth())) <= 6 {
		t.Fatal("detail pane fits the small terminal: the test proves nothing")
	}
	m, _ = press(m, "ctrl+d")
	if m.search.detailScroll == 0 {
		t.Fatal("ctrl+d did not scroll the detail pane")
	}
	m, _ = press(m, "ctrl+u")
	if m.search.detailScroll != 0 {
		t.Errorf("ctrl+u: scroll = %d, want 0", m.search.detailScroll)
	}
	m, _ = press(m, "ctrl+d", "j")
	if m.search.detailScroll != 0 {
		t.Errorf("a new hit keeps the scroll %d, want 0", m.search.detailScroll)
	}
}

// The header names the command center inside the query field, where ? types.
func TestQueryFieldHeaderHintsCommandCenter(t *testing.T) {
	out := strings.ReplaceAll(sized(t, nil).View(), nbsp, " ")
	if !strings.Contains(out, "ctrl+k commands · ctrl+c quit now") || !strings.Contains(out, "esc back") {
		t.Errorf("view lacks the command center or esc hint inside the query field:\n%s", out)
	}
}

// Every pane of the search screen carries its title on the top border; the query field has its own
// frame, in teal while it has the focus and in the pane border colour otherwise.
func TestSearchPanesAreTitledAndQueryFramed(t *testing.T) {
	m := onFixture(t, 120, 30)
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	focused := m.queryBox(118)
	if plain := ansi.Strip(focused); !strings.Contains(plain, "─ Query ") || !strings.Contains(plain, "╭") || !strings.Contains(plain, "╯") {
		t.Errorf("query field is not a titled rounded box:\n%s", focused)
	}
	teal := lipgloss.NewStyle().Foreground(theme.Teal).Render("╭")
	if !strings.HasPrefix(focused, teal) {
		t.Errorf("focused query border is not teal: %q", focused)
	}
	m, _ = press(m, "esc")
	if blurred := m.queryBox(118); strings.HasPrefix(blurred, teal) {
		t.Errorf("unfocused query border is still teal: %q", blurred)
	}
	view := ansi.Strip(m.View())
	for _, title := range []string{"Query", "Results", "Preview"} {
		if !strings.Contains(view, "─ "+title+" ") {
			t.Errorf("no %s pane title:\n%s", title, view)
		}
	}
}

// EARS 1 and 2 of OKFT-brlv: the ranking note never toasts; any other warning toasts once per
// session for the same text.
func TestSearchWarningToastsOncePerText(t *testing.T) {
	answer := func(m model, warnings ...string) model {
		m, _ = m.handleSearchDone(searchDoneMsg{seq: m.search.seq, result: &find.Result{Warnings: warnings}})
		return m
	}
	m := onFixture(t, 100, 30)

	if m = answer(m, find.NoteSemanticOwns); m.toast != nil {
		t.Fatalf("toast = %+v, want none for the ranking note", m.toast)
	}
	if m = answer(m, find.NoteSemanticOwns, "semantic arm skipped"); m.toast == nil || m.toast.title != "semantic arm skipped" || m.toast.context != "" {
		t.Fatalf("toast = %+v, want only the other warning", m.toast)
	}
	m.toast = nil
	if m = answer(m, "semantic arm skipped"); m.toast != nil {
		t.Fatalf("toast = %+v, want none for a repeated text", m.toast)
	}
	if m = answer(m, "another warning"); m.toast == nil || m.toast.title != "another warning" {
		t.Fatalf("toast = %+v, want the new text", m.toast)
	}
}
