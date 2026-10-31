package tui

import (
	"github.com/charmbracelet/bubbles/textinput"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// focusTarget is one stop of the focus ring of the search screen.
type focusTarget int

const (
	focusQuery focusTarget = iota // the query field, a text input
	focusList                     // the results pane
)

// focusRing is the tab order of the search screen. A later task inserts its targets (filter bar,
// detail pane) here.
var focusRing = []focusTarget{focusQuery, focusList}

// overlayKind names the overlay on top of the screen. There is one overlay at a time; it captures
// every key until it closes.
type overlayKind int

const (
	overlayNone overlayKind = iota
	overlayHelp
	overlayConfirm
)

// model is the whole state of the TUI. Bubble Tea copies it on every message, so it holds values
// and small structs; Update returns the changed copy.
type model struct {
	root     string // active catalogue root, absolute
	settings Settings

	width, height int

	focus focusTarget
	query textinput.Model

	overlay overlayKind
	help    helpState     // state of overlayHelp
	confirm confirmDialog // dialog of overlayConfirm

	toast           *toastState
	toastSeqCounter int
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
	m := model{root: root, settings: settings, focus: focusQuery, query: q}
	if settingsErr != nil {
		m, _ = m.showToast(toastError, "Invalid [tui] settings, defaults in use", settingsErr.Error(), true)
	}
	return m
}

// inInput reports whether the focus sits in a text input, where letter keys type instead of
// acting.
func (m model) inInput() bool { return m.focus == focusQuery }
