// Program runner from lif internal/tui/app.go (Run) at commit 2056715, adapted: alt screen, no
// mouse, no store.

// Package tui is `okf tui`, the keyboard-first terminal UI of the catalogue. The look and the key
// handling follow lif-tui; the generic parts are copied from lif, each file names its source.
package tui

import (
	tea "github.com/charmbracelet/bubbletea"
)

// Run starts the TUI on root and blocks until the user quits. It loads the [tui] settings first
// and puts the theme in force before anything renders; an invalid section does not stop the
// start, it shows as a sticky error toast. The root is remembered for later sessions; a state
// file that cannot be written shows as a sticky toast unless the settings error holds the slot.
func Run(root string) error {
	settings, settingsErr := LoadSettings()
	settings.apply()
	m := newModel(root, settings, settingsErr)
	if err := rememberRoot(root); err != nil && m.toast == nil {
		m, _ = m.showToast(toastWarn, "Could not remember the root", err.Error(), true)
	}
	_, err := tea.NewProgram(m, tea.WithAltScreen()).Run()
	return err
}
