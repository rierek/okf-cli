// Key capture order from lif internal/tui/update.go (handleKey) at commit 2056715, adapted. Written,
// not copied: the okf model has no views, forms or palette yet.

package tui

import (
	keybind "github.com/charmbracelet/bubbles/key"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
)

// Init starts the blink of the focused query field.
func (m model) Init() tea.Cmd { return tea.Batch(textinput.Blink, m.checkIndexes()) }

// Update routes a message to its handler.
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		return m, nil
	case toastExpiredMsg:
		return m.handleToastExpired(msg)
	case indexCheckedMsg:
		return m.handleIndexChecked(msg)
	case indexRefreshedMsg:
		return m.handleIndexRefreshed(msg)
	case semanticPlanMsg:
		return m.handleSemanticPlan(msg)
	case tea.KeyMsg:
		return m.handleKey(msg)
	}
	if m.focus == focusQuery { // cursor blink ticks
		var cmd tea.Cmd
		m.query, cmd = m.query.Update(msg)
		return m, cmd
	}
	return m, nil
}

// handleKey is the key capture order; the first stage that owns the key consumes it:
//
//  1. ctrl+c quits at once, from every state.
//  2. The open overlay (confirm dialog, help, refresh dialog) captures every key.
//  3. A focused text input takes the text keys; only the keys that must work inside a text field
//     (esc, tab, shift+tab, f1) are handled before it.
//  4. The global keys: ? help, q quit dialog, tab and shift+tab focus ring, / query field, esc
//     dismisses a sticky toast.
//
// A later task adds its stages at the matching place: modal editors and forms next to the
// overlays, screen keys after the global keys.
func (m model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	if keybind.Matches(msg, keys.QuitNow) {
		return m, tea.Quit
	}
	switch m.overlay {
	case overlayConfirm:
		return m.keyConfirm(msg)
	case overlayHelp:
		return m.keyHelp(msg)
	case overlayRefresh:
		return m.keyRefresh(msg)
	}
	if m.focus == focusQuery {
		return m.keyQuery(msg)
	}
	switch {
	case keybind.Matches(msg, keys.Help):
		return m.openHelp(), nil
	case keybind.Matches(msg, keys.Quit):
		return m.openConfirm(quitDialog), nil
	case keybind.Matches(msg, keys.Refresh):
		m.overlay = overlayRefresh
		return m, nil
	case keybind.Matches(msg, keys.FocusIn):
		return m.stepFocus(1)
	case keybind.Matches(msg, keys.FocusOut):
		return m.stepFocus(-1)
	case keybind.Matches(msg, keys.Search):
		return m.setFocus(focusQuery)
	case keybind.Matches(msg, keys.Back) && m.escDismissesToast():
		return m.dismissToast()
	}
	return m, nil
}

// keyQuery handles a key while the query field has the focus: esc leaves the field, tab and
// shift+tab step the focus ring, f1 opens the help; every other key goes to the field.
func (m model) keyQuery(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case keybind.Matches(msg, keys.Back):
		return m.setFocus(focusList)
	case keybind.Matches(msg, keys.FocusIn):
		return m.stepFocus(1)
	case keybind.Matches(msg, keys.FocusOut):
		return m.stepFocus(-1)
	case msg.Type == tea.KeyF1:
		return m.openHelp(), nil
	}
	var cmd tea.Cmd
	m.query, cmd = m.query.Update(msg)
	return m, cmd
}

// setFocus moves the focus to target and focuses or blurs the query field with it.
func (m model) setFocus(target focusTarget) (tea.Model, tea.Cmd) {
	m.focus = target
	if target == focusQuery {
		cmd := m.query.Focus()
		return m, cmd
	}
	m.query.Blur()
	return m, nil
}

// stepFocus moves the focus delta stops along the focus ring, wrapping at both ends.
func (m model) stepFocus(delta int) (tea.Model, tea.Cmd) {
	i := 0
	for j, t := range focusRing {
		if t == m.focus {
			i = j
		}
	}
	n := len(focusRing)
	return m.setFocus(focusRing[((i+delta)%n+n)%n])
}
