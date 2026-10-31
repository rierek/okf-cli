// Adapted from lif internal/tui/box_confirm_quit.go and box_confirm_delete.go at commit 2056715:
// one confirm dialog for every action, with the red border of box_confirm_delete.go for
// destructive ones.

package tui

import (
	keybind "github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// confirmKind names the action a confirm dialog guards; keyConfirm runs it on confirm. A later
// task adds its kind here and its case to runConfirm.
type confirmKind int

const (
	confirmQuit confirmKind = iota
)

// confirmDialog describes one confirm dialog. A destructive one gets a red border and title.
type confirmDialog struct {
	kind        confirmKind
	title       string
	body        string
	yes         string // what enter/y does, e.g. "quit"
	destructive bool
}

// quitDialog is the dialog of `q`.
var quitDialog = confirmDialog{kind: confirmQuit, title: "Quit?", body: "Really quit okf?", yes: "quit"}

// openConfirm shows d, replacing any other overlay: there is one overlay at a time.
func (m model) openConfirm(d confirmDialog) model {
	m.overlay, m.confirm = overlayConfirm, d
	return m
}

// keyConfirm handles input while a confirm dialog is open (full capture).
func (m model) keyConfirm(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case keybind.Matches(msg, keys.Confirm):
		kind := m.confirm.kind
		m.overlay = overlayNone
		return m.runConfirm(kind)
	case keybind.Matches(msg, keys.Cancel):
		m.overlay = overlayNone
	}
	return m, nil
}

// runConfirm runs the action a confirmed dialog guards.
func (m model) runConfirm(kind confirmKind) (tea.Model, tea.Cmd) {
	switch kind {
	case confirmQuit:
		return m, tea.Quit
	}
	return m, nil
}

func (m model) confirmBox() string {
	d := m.confirm
	hint := theme.Accent.Render("enter/y") + theme.Dim.Render(": "+d.yes+"   ") +
		theme.Accent.Render("esc/n") + theme.Dim.Render(": cancel")
	body := "\n" + theme.Dim.Render(d.body) + "\n\n" + hint
	if !d.destructive {
		return modalPanel(d.title, body, "", 40, theme.Mauve)
	}
	title := lipgloss.NewStyle().Foreground(theme.Red).Bold(true).Render(d.title)
	return modalBox(title+body, clampModalWidth(48, m.width), theme.Red)
}
