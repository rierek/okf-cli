package tui

import (
	"slices"
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/find"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// searchLimit is the number of hits one search lists (SPEC D6). The list scrolls client-side.
const searchLimit = 50

// searchState is the search of the screen: the running search and the hits of the last finished one.
type searchState struct {
	seq     int // generation of the newest search; an answer of an older one is dropped
	running bool
	asked   string // the query of the newest search, started or finished; a filter change reruns it
	spinner spinner.Model

	ran    bool   // a search has finished: an empty list means "no hits", not "no search yet"
	query  string // the query the hits answer
	hits   []find.Hit
	ids    []string // fileID of every hit, in order: the identity the buffer matches on
	cursor int

	headings     []catalogue.Heading // H2 and H3 of the focused hit, in document order
	detailScroll int                 // rows the detail pane is scrolled down
}

// searchDoneMsg is the answer of the search of generation seq.
type searchDoneMsg struct {
	seq    int
	query  string
	result *find.Result
	err    error
}

func newSearchState() searchState {
	return searchState{spinner: spinner.New(spinner.WithSpinner(spinner.MiniDot), spinner.WithStyle(theme.Accent))}
}

// focused is the hit under the cursor, nil without hits.
func (s searchState) focused() *find.Hit {
	if s.cursor < 0 || s.cursor >= len(s.hits) {
		return nil
	}
	return &s.hits[s.cursor]
}

// startSearch runs the query field's text as a search. A blank query starts nothing. Focus moves
// to the list; `/` brings it back to the query field.
func (m model) startSearch() (model, tea.Cmd) {
	query := strings.TrimSpace(m.query.Value())
	if query == "" {
		return m, nil
	}
	m.focus = focusList
	m.query.Blur()
	return m.runSearch(query)
}

// runSearch searches query with the chosen filters off the UI loop, so the program keeps reacting
// to keys while it runs. The filter expression is compiled by the same facade `okf find --where`
// uses; a compile failure comes back as the search's error.
func (m model) runSearch(query string) (model, tea.Cmd) {
	m.search.seq++
	wasRunning := m.search.running
	m.search.running = true
	m.search.asked = query
	seq, root, expr := m.search.seq, m.root, m.filters.expression()
	run := func() tea.Msg {
		filters, err := find.Compile(root, expr, false)
		if err != nil {
			return searchDoneMsg{seq: seq, query: query, err: err}
		}
		result, err := find.Search(root, find.Options{Query: query, Limit: searchLimit, Filters: filters})
		return searchDoneMsg{seq: seq, query: query, result: result, err: err}
	}
	if wasRunning { // the spinner already ticks
		return m, run
	}
	return m, tea.Batch(run, m.search.spinner.Tick)
}

// handleSearchDone replaces the list with the answer of the newest search, shows the warnings of
// the ranking as a toast and reports a failure as an error toast.
func (m model) handleSearchDone(msg searchDoneMsg) (model, tea.Cmd) {
	if msg.seq != m.search.seq {
		return m, nil
	}
	m.search.running = false
	if msg.err != nil {
		return m.showToast(toastError, "Search failed", msg.err.Error(), false)
	}
	m.search.ran, m.search.query = true, msg.query
	m.search.hits, m.search.cursor = msg.result.Hits, 0
	m.search.ids = hitIDs(m.search.hits)
	m = m.focusHit()
	if w := msg.result.Warnings; len(w) > 0 {
		return m.showToast(toastWarn, w[0], strings.Join(w[1:], " · "), false)
	}
	return m, nil
}

// moveCursor puts the cursor on hit i (clamped) and loads what the detail pane shows of it.
func (m model) moveCursor(i int) model {
	if len(m.search.hits) == 0 {
		return m
	}
	m.search.cursor = min(max(i, 0), len(m.search.hits)-1)
	return m.focusHit()
}

// focusHit loads the H2 and H3 headings of the focused hit and resets the detail scroll.
func (m model) focusHit() model {
	m.search.detailScroll = 0
	m.search.headings = nil
	if hit := m.search.focused(); hit != nil {
		m.search.headings = headingsOf(hit.Abs)
	}
	return m
}

// headingsOf lists the H2 and H3 headings of the file at abs, as `okf toc <path> --level 0` lists
// them. A file that cannot be read has none.
func headingsOf(abs string) []catalogue.Heading {
	text, err := catalogue.ReadFile(abs)
	if err != nil {
		return nil
	}
	var hs []catalogue.Heading
	for _, h := range catalogue.IterHeadings(frontmatter.Read(text).Body) {
		if h.Level == 2 || h.Level == 3 {
			hs = append(hs, h)
		}
	}
	return hs
}

// handleSpinner advances the running indicator; it stops ticking when the search ends.
func (m model) handleSpinner(msg spinner.TickMsg) (model, tea.Cmd) {
	if !m.search.running {
		return m, nil
	}
	var cmd tea.Cmd
	m.search.spinner, cmd = m.search.spinner.Update(msg)
	return m, cmd
}

// keyList handles the keys of the focused list; ok is false for a key it does not own.
func (m model) keyList(msg tea.KeyMsg) (model, bool) {
	_, _, innerH := m.geometry()
	if scroll, ok := scrollKey(msg, m.search.detailScroll, len(m.detailRows(m.detailTextWidth())), innerH); ok {
		m.search.detailScroll = scroll
		return m, true
	}
	switch {
	case keybind.Matches(msg, keys.Up):
		return m.moveCursor(m.search.cursor - 1), true
	case keybind.Matches(msg, keys.Down):
		return m.moveCursor(m.search.cursor + 1), true
	case keybind.Matches(msg, keys.Top):
		return m.moveCursor(0), true
	case keybind.Matches(msg, keys.Bottom):
		return m.moveCursor(len(m.search.hits) - 1), true
	case keybind.Matches(msg, keys.Layout):
		return m.nextLayout(msg.String() == "V"), true
	}
	return m, false
}

// handleFileEdited shows an editor failure as an error toast, and reads the edited hit again from
// disk: description, tags, type, snippet and headings. The list order, the cursor and the detail
// scroll stay; a file gone or unreadable keeps the old row and says so in a toast.
func (m model) handleFileEdited(msg fileEditedMsg) (model, tea.Cmd) {
	i := slices.IndexFunc(m.search.hits, func(h find.Hit) bool { return h.Abs == msg.path })
	var reloadErr error
	if i >= 0 {
		var fresh find.Hit
		if fresh, reloadErr = find.Reload(m.root, m.search.hits[i], m.search.query); reloadErr == nil {
			m.search.hits = slices.Clone(m.search.hits) // earlier copies of the model keep their list
			m.search.hits[i] = fresh
			m.buf = m.buf.refresh(entryOf(fresh))
			if i == m.search.cursor {
				scroll := m.search.detailScroll
				m = m.focusHit()
				_, _, innerH := m.geometry()
				m.search.detailScroll = min(scroll, max(len(m.detailRows(m.detailTextWidth()))-innerH, 0))
			}
		}
	}
	switch {
	case msg.err != nil:
		return m.showToast(toastError, "Editor failed", msg.err.Error(), false)
	case reloadErr != nil:
		return m.showToast(toastError, "Hit not reloaded", reloadErr.Error(), false)
	}
	return m, nil
}
