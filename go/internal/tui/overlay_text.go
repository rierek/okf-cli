package tui

import (
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	"github.com/charmbracelet/bubbles/textarea"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// textOverlay is the state of overlayText, the one multi-line text box of the TUI.
//
// Use: call m.openText(caller, title, initial, save) and return its model and command. The box
// shows title over a text area filled with initial. ctrl+s closes it and calls save with the text
// (surrounding whitespace trimmed) and the model; esc closes it and drops the text; ctrl+e hands
// the text to the editor (m.editText(caller, ...)) and puts the edited text back into the area.
// caller names the asker in the editor's textEditedMsg; one open box has one caller. The save
// function runs on the model of the moment, so capture only values (ids, snapshots), not model
// state. A task prompt (first line title, rest body) splits the text in its save function.
type textOverlay struct {
	caller string
	title  string
	area   textarea.Model
	save   func(m model, text string) (model, tea.Cmd)
}

// openText opens the text box; see textOverlay.
func (m model) openText(caller, title, initial string, save func(model, string) (model, tea.Cmd)) (model, tea.Cmd) {
	a := textarea.New()
	a.Prompt, a.ShowLineNumbers, a.Placeholder = "", false, "text"
	for _, s := range []*textarea.Style{&a.FocusedStyle, &a.BlurredStyle} {
		s.CursorLine, s.Text, s.Base = lipgloss.NewStyle(), lipgloss.NewStyle(), lipgloss.NewStyle()
		s.Placeholder, s.EndOfBuffer = theme.Muted, theme.Muted
	}
	a.SetWidth(m.textWidth())
	a.SetHeight(m.textHeight())
	a.SetValue(initial)
	cmd := a.Focus()
	m.overlay, m.text = overlayText, textOverlay{caller: caller, title: title, area: a, save: save}
	return m, cmd
}

// textWidth is the width of the text box content; the box is two cells wider for its padding.
func (m model) textWidth() int { return clampModalWidth(72, m.width) - 2 }

// textHeight is the number of text rows: 8, fewer on a short terminal.
func (m model) textHeight() int {
	if m.height <= 0 {
		return 8
	}
	return min(8, max(m.height-8, 2))
}

// keyText handles input while the text box is open (full capture).
func (m model) keyText(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case keybind.Matches(msg, keys.TextSave):
		save, text := m.text.save, strings.TrimSpace(m.text.area.Value())
		m.overlay, m.text = overlayNone, textOverlay{}
		return save(m, text)
	case keybind.Matches(msg, keys.Back):
		m.overlay, m.text = overlayNone, textOverlay{}
		return m, nil
	case keybind.Matches(msg, keys.TextEdit):
		return m, m.editText(m.text.caller, m.text.area.Value())
	}
	var cmd tea.Cmd
	m.text.area, cmd = m.text.area.Update(msg)
	return m, cmd
}

// handleTextEdited puts the text of the editor back into the open text box of the same caller. An
// editor failure is a toast and leaves the text as it was. An answer for a box that is gone (or of
// another caller) is dropped.
func (m model) handleTextEdited(msg textEditedMsg) (model, tea.Cmd) {
	if m.overlay != overlayText || msg.caller != m.text.caller {
		return m, nil
	}
	if msg.err != nil {
		return m.showToast(toastError, "Editor failed", msg.err.Error(), false)
	}
	m.text.area.SetValue(strings.TrimRight(msg.text, "\r\n"))
	return m, nil
}

// textBox is the text overlay.
func (m model) textBox() string {
	footer := theme.Accent.Render("ctrl+s") + theme.Dim.Render(": save   ") +
		theme.Accent.Render("ctrl+e") + theme.Dim.Render(": editor   ") +
		theme.Accent.Render("esc") + theme.Dim.Render(": cancel")
	return modalBox(theme.Header.Render(m.text.title)+"\n"+m.text.area.View()+"\n"+footer, m.textWidth()+2, theme.Mauve)
}
