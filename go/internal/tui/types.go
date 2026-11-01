package tui

import (
	"github.com/charmbracelet/bubbles/textinput"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// focusTarget is one stop of the focus ring of the search screen.
type focusTarget int

const (
	focusQuery  focusTarget = iota // the query field, a text input
	focusFilter                    // the filter bar
	focusList                      // the results pane
)

// focusRing is the tab order of the search screen. A later task inserts its targets (detail
// pane) here.
var focusRing = []focusTarget{focusQuery, focusFilter, focusList}

// overlayKind names the overlay on top of the screen. There is one overlay at a time; it captures
// every key until it closes.
type overlayKind int

const (
	overlayNone overlayKind = iota
	overlayHelp
	overlayConfirm
	overlayRefresh
	overlayText
	overlayFilterMenu // value menu of the focused filter field
	overlayRoot       // root menu
	overlayAgents     // agent picker of the hand-off
	overlayPalette    // command center
)

// screenKind is the screen under the overlays.
type screenKind int

const (
	screenSearch screenKind = iota // query field, result list, detail pane
	screenBuffer                   // the session buffer
	screenTypes                    // the catalogue's types, reached from the command center
	screenTags                     // the catalogue's tags, reached from the command center
)

// model is the whole state of the TUI. Bubble Tea copies it on every message, so it holds values
// and small structs; Update returns the changed copy.
type model struct {
	root     string // active catalogue root, absolute
	settings Settings

	width, height int

	focus  focusTarget
	query  textinput.Model
	search searchState
	layout layoutMode

	screen    screenKind
	buf       buffer // the session buffer: kept across searches, filter changes and root changes
	bufCursor int    // entry under the cursor of screenBuffer

	filters  filterState
	rootMenu rootMenu // state of overlayRoot

	overlay overlayKind
	help    helpState     // state of overlayHelp
	confirm confirmDialog // dialog of overlayConfirm
	text    textOverlay   // box of overlayText
	agents  agentPicker   // state of overlayAgents
	palette paletteState  // state of overlayPalette
	cat     catalogueView // data and cursor of screenTypes and screenTags

	lexical, semantic indexDot // the two index dots of the header

	toast           *toastState
	toastSeqCounter int
	handoffBusy     bool // a hand-off resolves or sends off the UI loop
}

// newModel builds the model of the search screen on root: the query field is focused. A non-nil
// settingsErr (an invalid [tui] section, see LoadSettings) becomes a sticky error toast.
func newModel(root string, settings Settings, settingsErr error) model {
	q := textinput.New()
	q.Prompt = "/ "
	q.Placeholder = "query"
	q.PromptStyle = theme.Accent
	q.PlaceholderStyle = theme.Muted
	q.Focus()
	m := model{root: root, settings: settings, focus: focusQuery, query: q, search: newSearchState()}
	m.lexical.checking, m.semantic.checking = true, true // Init starts both checks
	if settingsErr != nil {
		m, _ = m.showToast(toastError, "Invalid [tui] settings, defaults in use", settingsErr.Error(), true)
	}
	return m
}

// inInput reports whether the focus sits in a text input, where letter keys type instead of
// acting.
func (m model) inInput() bool { return m.focus == focusQuery }
