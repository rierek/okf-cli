// The root menu and the root switch. The menu lists the active root, the configured root and the
// roots used in earlier sessions (the TUI state file), plus a field for a typed path. A root that
// is no catalogue is refused with a toast and the active root stays.

package tui

import (
	"errors"
	"fmt"
	"slices"
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// rootMenu is the state of overlayRoot: the roots on offer, the cursor over them and the path
// field below them (cursor == len(roots)).
type rootMenu struct {
	roots  []string
	cursor int // over the roots the query leaves, then the path field
	search menuSearch
	input  textinput.Model
}

// validateRoot resolves a typed or chosen path as the CLI resolves --root (`~` expanded, made
// absolute) and refuses a path that is no directory or holds no catalogue.
func validateRoot(input string) (string, error) {
	input = strings.TrimSpace(input)
	if input == "" {
		return "", errors.New("enter a path")
	}
	root, err := catalogue.CatalogueRoot(input, false)
	if err != nil {
		return "", err
	}
	if !catalogue.RealFS.IsDir(root) {
		return "", fmt.Errorf("root not found: %s", root)
	}
	if !catalogue.HasMarker(root) {
		return "", fmt.Errorf("no catalogue in %s (it needs .okf.toml, or SPEC.md and TYPES.md)", root)
	}
	return root, nil
}

// rootRememberedMsg is the end of remembering the start root; err is a failed write of the state
// file.
type rootRememberedMsg struct{ err error }

// rememberStartRoot remembers the root the TUI started on for later sessions, off the UI loop. A
// root that fails validateRoot (no directory, no catalogue marker) is not remembered, so the menu
// never offers a root the user could not switch to.
func rememberStartRoot(root string) tea.Cmd {
	return func() tea.Msg {
		valid, err := validateRoot(root)
		if err != nil {
			return nil
		}
		return rootRememberedMsg{err: rememberRoot(valid)}
	}
}

// handleRootRemembered shows a state file that cannot be written as a sticky toast, unless the
// toast slot already holds a message (an invalid [tui] section).
func (m model) handleRootRemembered(msg rootRememberedMsg) (tea.Model, tea.Cmd) {
	if msg.err == nil || m.toast != nil {
		return m, nil
	}
	return m.showToast(toastWarn, "Could not remember the root", msg.err.Error(), true)
}

// openRootMenu opens the root menu with the cursor on the active root. A configured root or a
// state file that cannot be read shows as a toast; the menu lists what could be read.
func (m model) openRootMenu() (model, tea.Cmd) {
	roots := []string{m.root}
	var problems []string
	configured, err := catalogue.ConfiguredRoot()
	if err != nil {
		problems = append(problems, err.Error())
	}
	state, err := loadState()
	if err != nil {
		problems = append(problems, err.Error())
	}
	seen := map[string]bool{fileID(m.root): true}
	for _, r := range append([]string{configured}, state.Roots...) {
		if r != "" && !seen[fileID(r)] {
			seen[fileID(r)] = true
			roots = append(roots, r)
		}
	}
	in := textinput.New()
	in.Prompt = "path: "
	in.PromptStyle = theme.Accent
	in.Placeholder = "another catalogue"
	in.PlaceholderStyle = theme.Muted
	m.rootMenu = rootMenu{roots: roots, input: in}
	m.overlay = overlayRoot
	if len(problems) > 0 {
		return m.showToast(toastError, "Reading the known roots failed", strings.Join(problems, "\n"), false)
	}
	return m, nil
}

// keyRoot handles input while the root menu is open (full capture): up and down (tab, shift+tab)
// walk the roots and the path field, enter or space takes the root under the cursor, enter also
// the typed path, / types a query that narrows the roots, esc clears a query or else closes. In
// the path field every other key types, space and / too.
func (m model) keyRoot(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	rm := m.rootMenu
	roots := rm.visible()
	inField := rm.cursor == len(roots)
	move := func(to int) {
		rm.cursor = min(max(to, 0), len(roots))
		if rm.cursor == len(roots) {
			rm.input.Focus()
		} else {
			rm.input.Blur()
		}
	}
	// The path field types every key, but a query that left no root stays editable from it.
	if !inField || rm.search.typing || (msg.Type == tea.KeyEsc && rm.search.query != "") {
		if search, before, handled := rm.search.edit(msg); handled {
			rm.search = search
			if search.query != before {
				roots = rm.visible()
				move(0)
			}
			m.rootMenu = rm
			return m, nil
		}
	}
	switch {
	case keybind.Matches(msg, keys.Back):
		m.overlay = overlayNone
		return m, nil
	case msg.Type == tea.KeyUp, msg.Type == tea.KeyShiftTab, !inField && keybind.Matches(msg, keys.Up):
		move(rm.cursor - 1)
		rm.search.typing = rm.search.typing && rm.cursor < len(roots)
	case msg.Type == tea.KeyDown, msg.Type == tea.KeyTab, !inField && keybind.Matches(msg, keys.Down):
		move(rm.cursor + 1)
		rm.search.typing = rm.search.typing && rm.cursor < len(roots)
	case keybind.Matches(msg, keys.Open), !inField && msg.String() == " ":
		input := rm.input.Value()
		if !inField {
			input = roots[rm.cursor]
		}
		m.rootMenu = rm
		return m.pickRoot(input)
	case inField:
		var cmd tea.Cmd
		rm.input, cmd = rm.input.Update(msg)
		m.rootMenu = rm
		return m, cmd
	}
	m.rootMenu = rm
	return m, nil
}

// visible is the roots the query leaves, in menu order.
func (rm rootMenu) visible() []string {
	if rm.search.query == "" {
		return rm.roots
	}
	return slices.DeleteFunc(slices.Clone(rm.roots), func(r string) bool { return !fuzzyMatch(rm.search.query, r) })
}

// pickRoot validates input and makes it the active root. A refused root keeps the menu open, the
// active root and its search; the error is a toast.
func (m model) pickRoot(input string) (tea.Model, tea.Cmd) {
	root, err := validateRoot(input)
	if err != nil {
		return m.showToast(toastError, "Root not changed", err.Error(), false)
	}
	m.overlay = overlayNone
	if root == m.root {
		return m, nil
	}
	return m.switchRoot(root)
}

// switchRoot makes root the active root: the index dots are rechecked, the list of the old root is
// dropped, filter values that the new root does not hold are dropped (a toast names them), and the
// newest query runs again on the new root. The root is remembered for later sessions.
func (m model) switchRoot(root string) (tea.Model, tea.Cmd) {
	query, running := m.search.asked, m.search.running
	m, check := m.setRoot(root)
	seq, spin := m.search.seq, m.search.spinner
	m.search = newSearchState()
	m.search.seq = seq // a late answer of the old root keeps being dropped
	// a running search keeps its spinner: a new one would drop the ticks of the running chain
	m.search.running, m.search.spinner = running, spin
	cmds := []tea.Cmd{check}

	m.filters.loaded = false
	var notice []string
	if m.filters.active() {
		var toast tea.Cmd
		if m, toast = m.ensureOptions(); m.filters.loaded {
			m, notice = m.dropMissing()
		} else { // the new root's values are unknown: the old root's choices do not carry over
			m.filters.selected = [filterFieldCount][]string{}
			cmds = append(cmds, toast)
		}
	}
	if len(notice) > 0 {
		var toast tea.Cmd
		m, toast = m.showToast(toastInfo, "Filters not in this root are dropped", strings.Join(notice, " · "), false)
		cmds = append(cmds, toast)
	}
	if err := rememberRoot(root); err != nil {
		var toast tea.Cmd
		m, toast = m.showToast(toastWarn, "Could not remember the root", err.Error(), false)
		cmds = append(cmds, toast)
	}
	if query != "" {
		var run tea.Cmd
		m, run = m.runSearch(query)
		cmds = append(cmds, run)
	}
	return m, tea.Batch(cmds...)
}

// rootMenuBox renders the root menu; a long path shows its tail. The query line shows once `/`
// is pressed or a query stands.
func (m model) rootMenuBox() string {
	rm := m.rootMenu
	w := clampModalWidth(72, m.width)
	const active = " (active)"
	roots := rm.visible()
	rows := make([]string, 0, len(roots)+2)
	for i, r := range roots {
		room := w - 4 // padding and the cursor column
		if r == m.root {
			room -= len(active)
		}
		cursor, label := "  ", tail(tildePath(r), room)
		if i == rm.cursor {
			cursor, label = theme.Accent.Render("▸ "), theme.Header.Render(label)
		}
		if r == m.root {
			label += theme.Muted.Render(active)
		}
		rows = append(rows, cursor+label)
	}
	cursor := "  "
	if rm.cursor == len(roots) {
		cursor = theme.Accent.Render("▸ ")
	}
	rm.input.Width = max(w-2-len(rm.input.Prompt)-4, 8)
	rows = append(rows, cursor+rm.input.View())
	hint := "↑/↓ choose · enter/space switch · / search · esc"
	if rm.search.typing {
		hint = "type to search · enter done · esc clear"
	}
	head := theme.Muted.Render(hint)
	if rm.search.shown() {
		head += "\n" + rm.search.line()
	}
	return modalPanel("Root", head+"\n"+strings.Join(rows, "\n"), "", w, theme.Mauve)
}
