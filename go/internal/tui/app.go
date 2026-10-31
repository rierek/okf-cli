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
// start, it shows as a sticky error toast.
func Run(root string) error {
	settings, settingsErr := LoadSettings()
	settings.apply()
	_, err := tea.NewProgram(newModel(root, settings, settingsErr), tea.WithAltScreen()).Run()
	return err
}
