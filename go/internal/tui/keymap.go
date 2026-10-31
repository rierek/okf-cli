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
	Up     keybind.Binding
	Down   keybind.Binding
	Top    keybind.Binding // g: first hit
	Bottom keybind.Binding // G: last hit

	DetailUp   keybind.Binding // ctrl+u: scroll the detail pane up
	DetailDown keybind.Binding // ctrl+d: scroll the detail pane down
	Layout     keybind.Binding // v, V: next and previous layout of the body
	Edit       keybind.Binding // e: open the focused hit in the editor

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
	Refresh keybind.Binding // r: choose an index to refresh (outside text inputs)
	Run     keybind.Binding // enter inside the query field: run the search

	Filter      keybind.Binding // f: focus the filter bar
	FieldPrev   keybind.Binding // left, h: previous filter field
	FieldNext   keybind.Binding // right, l: next filter field
	Open        keybind.Binding // enter: open the menu of the focused filter field, take a menu row
	Toggle      keybind.Binding // space, x: flip a menu value
	FilterClear keybind.Binding // X: clear every filter but the root
}

func newKeyMap() keyMap {
	return keyMap{
		Up:     keybind.NewBinding(keybind.WithKeys("up", "k"), keybind.WithHelp("↑/k", "up")),
		Down:   keybind.NewBinding(keybind.WithKeys("down", "j"), keybind.WithHelp("↓/j", "down")),
		Top:    keybind.NewBinding(keybind.WithKeys("g", "home"), keybind.WithHelp("g", "first hit")),
		Bottom: keybind.NewBinding(keybind.WithKeys("G", "end"), keybind.WithHelp("G", "last hit")),

		DetailUp:   keybind.NewBinding(keybind.WithKeys("ctrl+u"), keybind.WithHelp("ctrl+u", "detail up")),
		DetailDown: keybind.NewBinding(keybind.WithKeys("ctrl+d"), keybind.WithHelp("ctrl+d", "detail down")),
		Layout:     keybind.NewBinding(keybind.WithKeys("v", "V"), keybind.WithHelp("v/V", "layout")),
		Edit:       keybind.NewBinding(keybind.WithKeys("e"), keybind.WithHelp("e", "edit hit")),

		FocusIn:  keybind.NewBinding(keybind.WithKeys("tab"), keybind.WithHelp("tab", "next focus")),
		FocusOut: keybind.NewBinding(keybind.WithKeys("shift+tab"), keybind.WithHelp("shift+tab", "previous focus")),

		Back:    keybind.NewBinding(keybind.WithKeys("esc"), keybind.WithHelp("esc", "back")),
		Confirm: keybind.NewBinding(keybind.WithKeys("enter", "y"), keybind.WithHelp("enter/y", "confirm")),
		Cancel:  keybind.NewBinding(keybind.WithKeys("esc", "n"), keybind.WithHelp("esc/n", "cancel")),
		Quit:    keybind.NewBinding(keybind.WithKeys("q"), keybind.WithHelp("q", "quit")),
		QuitNow: keybind.NewBinding(keybind.WithKeys("ctrl+c"), keybind.WithHelp("ctrl+c", "quit now")),
		Help:    keybind.NewBinding(keybind.WithKeys("?", "f1"), keybind.WithHelp("?/f1", "help")),
		Search:  keybind.NewBinding(keybind.WithKeys("/"), keybind.WithHelp("/", "query field")),
		Refresh: keybind.NewBinding(keybind.WithKeys("r"), keybind.WithHelp("r", "refresh index")),
		Run:     keybind.NewBinding(keybind.WithKeys("enter"), keybind.WithHelp("enter", "search")),

		Filter:      keybind.NewBinding(keybind.WithKeys("f"), keybind.WithHelp("f", "filter bar")),
		FieldPrev:   keybind.NewBinding(keybind.WithKeys("left", "h"), keybind.WithHelp("←/h", "previous field")),
		FieldNext:   keybind.NewBinding(keybind.WithKeys("right", "l"), keybind.WithHelp("→/l", "next field")),
		Open:        keybind.NewBinding(keybind.WithKeys("enter"), keybind.WithHelp("enter", "open menu")),
		Toggle:      keybind.NewBinding(keybind.WithKeys(" ", "x"), keybind.WithHelp("space/x", "toggle value")),
		FilterClear: keybind.NewBinding(keybind.WithKeys("X"), keybind.WithHelp("X", "clear filters")),
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
		{"Navigation", []keybind.Binding{k.Up, k.Down, k.Top, k.Bottom, k.FocusIn, k.FocusOut, k.Search, k.Run, k.Back}},
		{"Detail", []keybind.Binding{k.DetailUp, k.DetailDown, k.Layout, k.Edit}},
		{"Dialogs", []keybind.Binding{k.Confirm, k.Cancel}},
		{"Global", []keybind.Binding{k.Help, k.Quit, k.QuitNow}},
		{"Index", []keybind.Binding{k.Refresh}},
		{"Filters", []keybind.Binding{k.Filter, k.FieldPrev, k.FieldNext, k.Open, k.Toggle, k.FilterClear}},
	}
}

// fieldHelpHint is the help hint inside a text field, where only f1 opens the help.
var fieldHelpHint = keybind.NewBinding(keybind.WithKeys("f1"), keybind.WithHelp("f1", "help"))

// globalBindings are the hints at the right of the header. Inside a text field the letter keys
// type, so the hints name the keys that work there.
func globalBindings(inInput bool) []keybind.Binding {
	if inInput {
		return []keybind.Binding{keys.Back, fieldHelpHint, keys.QuitNow}
	}
	return []keybind.Binding{keys.Help, keys.Quit}
}
