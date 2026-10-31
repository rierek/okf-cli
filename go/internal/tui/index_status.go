// The two index dots of the header and the refresh of both indexes. The checks and the builds are
// tea.Cmds, so they run off the UI loop; their results come back as messages that carry the root
// they ran for, and a result for a root that is no longer active is dropped.

package tui

import (
	"fmt"
	"io"
	"os"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"nas/volume1/data/git/okf-tools/go/internal/fts"
	"nas/volume1/data/git/okf-tools/go/internal/semantic"
	"nas/volume1/data/git/okf-tools/go/internal/tagvec"
	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// embedVectors is the embedding backend of the semantic refresh; tests replace it, so no test
// reaches the network.
var embedVectors = tagvec.EmbedVoyage

const voyageKeyVar = "VOYAGE_API_KEY"

func voyageKeySet() bool { return os.Getenv(voyageKeyVar) != "" }

// indexKind names one of the two indexes.
type indexKind int

const (
	indexLexical indexKind = iota
	indexSemantic
)

func (k indexKind) label() string {
	if k == indexLexical {
		return "lexical"
	}
	return "semantic"
}

// indexState is the colour of a dot: grey unknown or unavailable, green current, yellow stale
// (lexical) or partial (semantic), red absent.
type indexState int

const (
	indexUnknown indexState = iota
	indexCurrent
	indexStale
	indexAbsent
)

func (s indexState) color() lipgloss.Color {
	switch s {
	case indexCurrent:
		return theme.Green
	case indexStale:
		return theme.Yellow
	case indexAbsent:
		return theme.Red
	}
	return theme.Overlay
}

// indexDot is one dot: its state and whether a check or a refresh of that index is running.
type indexDot struct {
	state indexState
	busy  bool
}

// dot returns the dot of kind k for update.
func (m *model) dot(k indexKind) *indexDot {
	if k == indexLexical {
		return &m.lexical
	}
	return &m.semantic
}

// indexCheckedMsg is the result of a check of one index.
type indexCheckedMsg struct {
	root  string
	kind  indexKind
	state indexState
	err   error
}

// indexRefreshedMsg is the end of a refresh. left counts concepts a semantic refresh could not
// embed.
type indexRefreshedMsg struct {
	root string
	kind indexKind
	left int
	err  error
}

// semanticPlanMsg is the number of concepts a semantic refresh would embed.
type semanticPlanMsg struct {
	root    string
	pending int
	err     error
}

// checkIndex checks one index of root.
func checkIndex(root string, k indexKind) tea.Cmd {
	return func() tea.Msg {
		msg := indexCheckedMsg{root: root, kind: k}
		if k == indexLexical {
			st, err := fts.Status(root)
			msg.err = err
			msg.state = map[fts.State]indexState{fts.Absent: indexAbsent, fts.Stale: indexStale, fts.Current: indexCurrent}[st]
			return msg
		}
		if !voyageKeySet() { // the semantic index cannot be used or refreshed without the key
			return msg
		}
		cov, ok, err := semantic.Coverage(root)
		switch {
		case err != nil:
			msg.err = err
		case !ok:
			msg.state = indexAbsent
		case cov.Embedded < cov.Total:
			msg.state = indexStale
		default:
			msg.state = indexCurrent
		}
		return msg
	}
}

// checkIndexes checks both indexes of the active root.
func (m model) checkIndexes() tea.Cmd {
	return tea.Batch(checkIndex(m.root, indexLexical), checkIndex(m.root, indexSemantic))
}

// setRoot makes root the active root and rechecks both dots for it. The root switch of the TUI
// calls it.
func (m model) setRoot(root string) (model, tea.Cmd) {
	m.root = root
	m.lexical, m.semantic = indexDot{}, indexDot{}
	return m, m.checkIndexes()
}

// handleIndexChecked applies a check result: an error keeps the old state and shows a toast.
func (m model) handleIndexChecked(msg indexCheckedMsg) (tea.Model, tea.Cmd) {
	if msg.root != m.root {
		return m, nil
	}
	d := m.dot(msg.kind)
	d.busy = false
	if msg.err != nil {
		return m.showToast(toastError, "Checking the "+msg.kind.label()+" index failed", msg.err.Error(), true)
	}
	d.state = msg.state
	return m, nil
}

// refreshBox is the dialog the `r` key opens: the choice of the index to refresh.
func (m model) refreshBox() string {
	sem := theme.Accent.Render("s") + "  semantic index: embed the missing concepts"
	if !voyageKeySet() {
		sem = theme.Dim.Render("s  semantic index: unavailable, " + voyageKeyVar + " is not set")
	}
	body := "\n" + theme.Accent.Render("l") + "  lexical index: rebuild\n" + sem + "\n\n" +
		theme.Accent.Render("esc") + theme.Dim.Render(": cancel")
	return modalPanel("Refresh index", body, "", 56, theme.Mauve)
}

// keyRefresh handles input while the refresh dialog is open (full capture).
func (m model) keyRefresh(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case msg.Type == tea.KeyEsc:
		m.overlay = overlayNone
	case msg.String() == "l":
		m.overlay = overlayNone
		return m.startLexical()
	case msg.String() == "s":
		m.overlay = overlayNone
		return m.startSemanticPlan()
	}
	return m, nil
}

// running is the toast of a refresh that is already running.
func (m model) running(k indexKind) (model, tea.Cmd) {
	return m.showToast(toastWarn, "The "+k.label()+" index is busy", "A check or a refresh is still running.", false)
}

// startLexical rebuilds the FTS index off the UI loop.
func (m model) startLexical() (model, tea.Cmd) {
	if m.lexical.busy {
		return m.running(indexLexical)
	}
	m.lexical.busy = true
	root := m.root
	run := func() tea.Msg {
		_, err := fts.Refresh(root)
		return indexRefreshedMsg{root: root, kind: indexLexical, err: err}
	}
	m, toast := m.showToast(toastInfo, "Rebuilding the lexical index…", "", false)
	return m, tea.Batch(toast, run)
}

// startSemanticPlan counts the concepts to embed; the confirm dialog follows. Without the API key
// nothing runs and the toast names the key.
func (m model) startSemanticPlan() (model, tea.Cmd) {
	if !voyageKeySet() {
		return m.showToast(toastWarn, "Semantic refresh unavailable", voyageKeyVar+" is not set", false)
	}
	if m.semantic.busy {
		return m.running(indexSemantic)
	}
	m.semantic.busy = true
	root := m.root
	return m, func() tea.Msg {
		n, err := semantic.Pending(root)
		return semanticPlanMsg{root: root, pending: n, err: err}
	}
}

// handleSemanticPlan opens the confirm dialog naming the number of concepts to embed. Nothing is
// embedded before the user confirms.
func (m model) handleSemanticPlan(msg semanticPlanMsg) (tea.Model, tea.Cmd) {
	if msg.root != m.root {
		return m, nil
	}
	m.semantic.busy = false
	switch {
	case msg.err != nil:
		return m.showToast(toastError, "Semantic refresh failed", msg.err.Error(), true)
	case msg.pending == 0:
		return m.showToast(toastInfo, "The semantic index is current", "No concept to embed.", false)
	}
	return m.openConfirm(confirmDialog{
		kind:  confirmSemanticRefresh,
		title: "Embed concepts?",
		body:  fmt.Sprintf("Embed %d concept(s) with Voyage AI?\nTheir text goes to the Voyage API.", msg.pending),
		yes:   "embed",
	}), nil
}

// startSemantic embeds the missing concepts off the UI loop, after the user confirmed.
func (m model) startSemantic() (model, tea.Cmd) {
	if m.semantic.busy {
		return m.running(indexSemantic)
	}
	m.semantic.busy = true
	root := m.root
	run := func() tea.Msg {
		_, left, err := semantic.Refresh(root, embedVectors, io.Discard)
		return indexRefreshedMsg{root: root, kind: indexSemantic, left: left, err: err}
	}
	m, toast := m.showToast(toastInfo, "Embedding the missing concepts…", "", false)
	return m, tea.Batch(toast, run)
}

// handleIndexRefreshed ends a refresh. A failure keeps the dot as it was and shows the error; a
// success rechecks the index, which sets the dot.
func (m model) handleIndexRefreshed(msg indexRefreshedMsg) (tea.Model, tea.Cmd) {
	if msg.root != m.root {
		return m, nil
	}
	label := msg.kind.label()
	if msg.err != nil {
		m.dot(msg.kind).busy = false
		return m.showToast(toastError, "Refreshing the "+label+" index failed", msg.err.Error(), true)
	}
	title, kind, ctx := "The "+label+" index is refreshed", toastInfo, ""
	if msg.left > 0 {
		title, kind = "The semantic index is incomplete", toastWarn
		ctx = fmt.Sprintf("%d concept(s) stayed unembedded, refresh again", msg.left)
	}
	m, toast := m.showToast(kind, title, ctx, false)
	return m, tea.Batch(toast, checkIndex(msg.root, msg.kind))
}

// dots renders the two labelled dots of the header. A dot of a running check or refresh is half
// filled.
func (m model) dots() string {
	one := func(k indexKind, d indexDot) string {
		glyph := "●"
		if d.busy {
			glyph = "◐"
		}
		return theme.Muted.Render(k.label()) + " " + lipgloss.NewStyle().Foreground(d.state.color()).Render(glyph)
	}
	return one(indexLexical, m.lexical) + "  " + one(indexSemantic, m.semantic)
}
