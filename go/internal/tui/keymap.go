// Pattern from lif internal/tui/keymap.go at commit 2056715, adapted: the okf key map. Written, not
// copied: it holds the okf bindings only.

package tui

import (
	keybind "github.com/charmbracelet/bubbles/key"
)

// keyMap is the one source of every keybinding. The footer, the header hints and the help overlay
// are generated from it, and re-binding a key changes exactly one place. A later task adds its
// bindings here and to helpGroups, nowhere else.
type keyMap struct {
	Up   keybind.Binding
	Down keybind.Binding

	// Focus ring: tab and shift+tab step the focus to the next and previous target.
	FocusIn  keybind.Binding
	FocusOut keybind.Binding

	Back    keybind.Binding // esc: leave the text field, dismiss a sticky toast, close an overlay
	Confirm keybind.Binding // enter or y: confirm a dialog (the dialog captures the key first)
	Cancel  keybind.Binding // esc or n: cancel a dialog
	Quit    keybind.Binding // q: quit, after a confirm dialog
	QuitNow keybind.Binding // ctrl+c: quit at once, from every state (handled first in handleKey)
	Help    keybind.Binding // ?: help overlay; f1 also works inside a text field
	Search  keybind.Binding // /: focus the query field
}

func newKeyMap() keyMap {
	return keyMap{
		Up:   keybind.NewBinding(keybind.WithKeys("up", "k"), keybind.WithHelp("↑/k", "up")),
		Down: keybind.NewBinding(keybind.WithKeys("down", "j"), keybind.WithHelp("↓/j", "down")),

		FocusIn:  keybind.NewBinding(keybind.WithKeys("tab"), keybind.WithHelp("tab", "next focus")),
		FocusOut: keybind.NewBinding(keybind.WithKeys("shift+tab"), keybind.WithHelp("shift+tab", "previous focus")),

		Back:    keybind.NewBinding(keybind.WithKeys("esc"), keybind.WithHelp("esc", "back")),
		Confirm: keybind.NewBinding(keybind.WithKeys("enter", "y"), keybind.WithHelp("enter/y", "confirm")),
		Cancel:  keybind.NewBinding(keybind.WithKeys("esc", "n"), keybind.WithHelp("esc/n", "cancel")),
		Quit:    keybind.NewBinding(keybind.WithKeys("q"), keybind.WithHelp("q", "quit")),
		QuitNow: keybind.NewBinding(keybind.WithKeys("ctrl+c"), keybind.WithHelp("ctrl+c", "quit now")),
		Help:    keybind.NewBinding(keybind.WithKeys("?", "f1"), keybind.WithHelp("?/f1", "help")),
		Search:  keybind.NewBinding(keybind.WithKeys("/"), keybind.WithHelp("/", "query field")),
	}
}

var keys = newKeyMap()

// helpGroup is one titled block of the help overlay.
type helpGroup struct {
	title    string
	bindings []keybind.Binding
}

// helpGroups is the structure of the help overlay: every binding of the map appears in exactly
// one group.
func (k keyMap) helpGroups() []helpGroup {
	return []helpGroup{
		{"Navigation", []keybind.Binding{k.Up, k.Down, k.FocusIn, k.FocusOut, k.Search, k.Back}},
		{"Dialogs", []keybind.Binding{k.Confirm, k.Cancel}},
		{"Global", []keybind.Binding{k.Help, k.Quit, k.QuitNow}},
	}
}

// globalBindings are the hints at the right of the header. Inside a text field the letter keys
// type, so the hints name the keys that work there.
func globalBindings(inInput bool) []keybind.Binding {
	if inInput {
		return []keybind.Binding{keys.Back, keys.QuitNow}
	}
	return []keybind.Binding{keys.Help, keys.Quit}
}
