// Copied from lif internal/tui/overlay_palette.go at commit d0cd455 (paletteItem, palFiltered,
// openPalette, keyPalette, paletteBox), adapted: the entries come from the okf key map
// (paletteCommands) and name the same action as their key; ctrl+k opens it from every view, also
// inside the query field; an open overlay keeps the key.

package tui

import (
	"slices"
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// paletteState is the state of overlayPalette: the filter text and the cursor over the rows left.
type paletteState struct {
	query string
	list  listState
}

// command is one row of the command center: `<verb>: <object>` (or a bare verb), the key that
// runs the same action (zero for a view that has no key) and the action itself.
type command struct {
	name string
	key  keybind.Binding
	run  func(model) (tea.Model, tea.Cmd)
}

// paletteCommands lists every action of the key map and every view, sorted by name. An action
// that a key runs on the focused hit or buffer entry runs by pressing that key; the commands that
// the other keys of the map own (cursor steps, focus ring, dialogs, text box, filter menus) are
// not listed, see TestPaletteCoversKeyMap.
func paletteCommands() []command {
	k := keys
	cs := []command{
		{"add: note", k.Note, func(m model) (tea.Model, tea.Cmd) {
			if m.screen == screenBuffer && len(m.buf.entries) > 0 {
				return m.press(k.Note)
			}
			return m.pressOnHit(k.Note)
		}},
		{"add: task", k.Task, func(m model) (tea.Model, tea.Cmd) { return m.pressOnHit(k.Task) }},
		{"toggle: hit", k.BufferToggle, func(m model) (tea.Model, tea.Cmd) { return m.pressOnHit(k.BufferToggle) }},
		{"edit: hit", k.Edit, func(m model) (tea.Model, tea.Cmd) { return m.pressOnHit(k.Edit) }},
		{"go: first hit", k.Top, func(m model) (tea.Model, tea.Cmd) { return m.press(k.Top) }},
		{"go: last hit", k.Bottom, func(m model) (tea.Model, tea.Cmd) { return m.press(k.Bottom) }},
		{"scroll: detail up", k.DetailUp, func(m model) (tea.Model, tea.Cmd) { return m.toSearch().press(k.DetailUp) }},
		{"scroll: detail down", k.DetailDown, func(m model) (tea.Model, tea.Cmd) { return m.toSearch().press(k.DetailDown) }},
		{"next: layout", k.Layout, func(m model) (tea.Model, tea.Cmd) { return m.toSearch().nextLayout(false), nil }},
		{"previous: layout", k.Layout, func(m model) (tea.Model, tea.Cmd) { return m.toSearch().nextLayout(true), nil }},
		{"run: search", k.Run, func(m model) (tea.Model, tea.Cmd) { return m.toSearch().startSearch() }},
		{"focus: query", k.Search, func(m model) (tea.Model, tea.Cmd) { return m.toSearch().setFocus(focusQuery) }},
		{"focus: filters", k.Filter, func(m model) (tea.Model, tea.Cmd) { return m.toSearch().press(k.Filter) }},
		{"clear: filters", k.FilterClear, func(m model) (tea.Model, tea.Cmd) { return m.toSearch().clearFilters() }},
		{"view: search", k.BufferBack, func(m model) (tea.Model, tea.Cmd) { return m.toSearch(), nil }},
		{"view: buffer", k.Buffer, func(m model) (tea.Model, tea.Cmd) { return m.openBuffer(), nil }},
		{"view: types", keybind.Binding{}, func(m model) (tea.Model, tea.Cmd) { return m.openTypes() }},
		{"view: tags", keybind.Binding{}, func(m model) (tea.Model, tea.Cmd) { return m.openTags() }},
		{"remove: entry", k.BufferDrop, func(m model) (tea.Model, tea.Cmd) { return m.pressInBuffer("remove: entry", k.BufferDrop) }},
		{"clear: buffer", k.BufferClear, func(m model) (tea.Model, tea.Cmd) { return m.pressInBuffer("clear: buffer", k.BufferClear) }},
		{"copy: buffer", k.Copy, func(m model) (tea.Model, tea.Cmd) { return m.copyBuffer() }},
		{"send: buffer", k.Send, func(m model) (tea.Model, tea.Cmd) { return m.send() }},
		{"refresh: index", k.Refresh, func(m model) (tea.Model, tea.Cmd) { return m.press(k.Refresh) }},
		{"help", k.Help, func(m model) (tea.Model, tea.Cmd) { return m.openHelp(), nil }},
		{"quit", k.Quit, func(m model) (tea.Model, tea.Cmd) { return m.openConfirm(quitDialog), nil }},
	}
	slices.SortStableFunc(cs, func(a, b command) int { return strings.Compare(a.name, b.name) })
	return cs
}

// keyOf is the key message of the first key of b. It covers the keys the commands press: single
// characters, space, ctrl+u and ctrl+d.
func keyOf(b keybind.Binding) tea.KeyMsg {
	switch k := b.Keys()[0]; k {
	case "ctrl+u":
		return tea.KeyMsg{Type: tea.KeyCtrlU}
	case "ctrl+d":
		return tea.KeyMsg{Type: tea.KeyCtrlD}
	case " ":
		return tea.KeyMsg{Type: tea.KeySpace, Runes: []rune{' '}}
	default:
		return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(k)}
	}
}

// press sends the key of b through handleKey, the way the user presses it: the result list has
// the focus on the search screen, where the list keys act.
func (m model) press(b keybind.Binding) (tea.Model, tea.Cmd) {
	if m.screen == screenSearch {
		m.focus = focusList
		m.query.Blur()
	}
	return m.handleKey(keyOf(b))
}

// toSearch leaves the buffer, types and tags views for the search screen.
func (m model) toSearch() model {
	m.screen = screenSearch
	return m
}

// pressOnHit presses b on the focused hit of the search screen; without a hit it only says so.
func (m model) pressOnHit(b keybind.Binding) (tea.Model, tea.Cmd) {
	m = m.toSearch()
	if m.search.focused() == nil {
		return m.showToast(toastWarn, "No hit under the cursor", "Run a search first.", false)
	}
	return m.press(b)
}

// pressInBuffer presses b in the buffer view, the only place where the key acts.
func (m model) pressInBuffer(name string, b keybind.Binding) (tea.Model, tea.Cmd) {
	if m.screen != screenBuffer {
		return m.showToast(toastWarn, name, "Works in the buffer view, open it with view: buffer.", false)
	}
	return m.press(b)
}

// openBuffer is the b key and view: buffer: it shows the buffer view.
func (m model) openBuffer() model {
	m.screen = screenBuffer
	m.focus = focusList
	m.query.Blur()
	m.bufCursor = min(m.bufCursor, max(len(m.buf.entries)-1, 0))
	return m
}

// palFiltered is the commands that match the filter text, in the order of paletteCommands.
func (m model) palFiltered() []command {
	return slices.DeleteFunc(paletteCommands(), func(c command) bool { return !fuzzyMatch(m.palette.query, c.name) })
}

// openPalette opens the command center with an empty filter.
func (m model) openPalette() model {
	m.overlay = overlayPalette
	m.palette = paletteState{}
	m.palette.list.setLen(len(m.palFiltered()))
	return m
}

// keyPalette handles input while the command center is open (full capture).
func (m model) keyPalette(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case msg.Type == tea.KeyEsc, keybind.Matches(msg, keys.Palette):
		m.overlay = overlayNone
	case msg.Type == tea.KeyUp:
		m.palette.list.move(-1)
	case msg.Type == tea.KeyDown:
		m.palette.list.move(1)
	case msg.Type == tea.KeyEnter:
		if items := m.palFiltered(); m.palette.list.cursor < len(items) {
			run := items[m.palette.list.cursor].run
			m.overlay, m.palette = overlayNone, paletteState{}
			return run(m)
		}
	case msg.Type == tea.KeyBackspace:
		if r := []rune(m.palette.query); len(r) > 0 {
			m.palette.query = string(r[:len(r)-1])
			m.palette.list.setLen(len(m.palFiltered()))
		}
	case msg.Type == tea.KeyRunes, msg.Type == tea.KeySpace:
		m.palette.query += string(msg.Runes)
		m.palette.list.setLen(len(m.palFiltered()))
	}
	return m, nil
}

// paletteBox renders the floating command center: the filter line, a rule and the rows, a window
// of them when the terminal is short. The key of a command stands dimmed at the right.
func (m model) paletteBox() string {
	items := m.palFiltered()
	w := clampModalWidth(56, m.width)
	var b strings.Builder
	b.WriteString(theme.Accent.Render("> ") + m.palette.query + "▏\n")
	b.WriteString(theme.Dim.Render(strings.Repeat("─", w-4)) + "\n")
	if len(items) == 0 {
		b.WriteString(theme.Dim.Render("(no matches)") + "\n")
	}
	_, h := m.size()
	visible := max(h-8, 3) // the box adds border, title, filter line, rule and footer
	cursor := m.palette.list.cursor
	start := windowStart(len(items), visible, cursor)
	window := items[start:min(start+visible, len(items))]
	room := w - 6 // border, padding and the cursor mark
	b.WriteString(menuList(len(window), cursor-start, func(i int, sel bool) string {
		name, hint := window[i].name, window[i].key.Help().Key
		pad := strings.Repeat(" ", max(room-lipgloss.Width(name)-lipgloss.Width(hint), 1))
		if sel {
			name = theme.Header.Render(name)
		}
		return name + pad + theme.Dim.Render(hint)
	}))
	return modalPanel("Command center", b.String(), "type: filter · ↑↓: select · enter: run · esc: close", w, theme.Mauve)
}
