// Copied from lif internal/tui/overlay_shortcuts.go at commit 2056715, adapted: no Views block, no
// task actions, help state in model.help.

package tui

import (
	"fmt"
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// helpState is the state of the help overlay: the search term, whether the search line takes
// input, and the scroll offset.
type helpState struct {
	query     string
	searching bool
	scroll    int
}

// helpEntry is one row of the help overlay.
type helpEntry struct{ group, key, desc string }

// helpEntries is the help content, generated from the key map.
func helpEntries() []helpEntry {
	var out []helpEntry
	for _, g := range keys.helpGroups() {
		for _, b := range g.bindings {
			h := b.Help()
			out = append(out, helpEntry{g.title, h.Key, h.Desc})
		}
	}
	return out
}

// filterHelpEntries keeps the entries whose key, description or group name contains term
// (case-insensitive substring, no ranking).
func filterHelpEntries(es []helpEntry, term string) []helpEntry {
	if term == "" {
		return es
	}
	term = strings.ToLower(term)
	var out []helpEntry
	for _, e := range es {
		if strings.Contains(strings.ToLower(e.key+"\x00"+e.desc+"\x00"+e.group), term) {
			out = append(out, e)
		}
	}
	return out
}

// helpWidth is the box width; helpHeight the number of content rows that fit the terminal (box =
// rows + border 2 + title + search line + footer, one row margin). 0 means no limit (terminal
// size unknown).
func (m model) helpWidth() int { return clampModalWidth(72, m.width) }
func (m model) helpHeight() int {
	if m.height <= 0 {
		return 0
	}
	return max(3, m.height-6)
}

// helpLines renders the filtered content, one string per row: group headers only for groups with
// matches, a no-match line when nothing matches. The key column is as wide as the widest shown
// key; long descriptions wrap with a hanging indent.
func (m model) helpLines() []string {
	es := filterHelpEntries(helpEntries(), m.help.query)
	if len(es) == 0 {
		return []string{"  " + theme.Dim.Render("No matching key bindings")}
	}
	keyW := 0
	for _, e := range es {
		keyW = max(keyW, lipgloss.Width(e.key))
	}
	descW := max(10, m.helpWidth()-6-keyW)
	var lines []string
	group := ""
	for _, e := range es {
		if e.group != group {
			if group != "" {
				lines = append(lines, "")
			}
			lines = append(lines, theme.Accent.Render(e.group))
			group = e.group
		}
		pad := strings.Repeat(" ", keyW-lipgloss.Width(e.key))
		for i, l := range strings.Split(wrapText(e.desc, descW), "\n") {
			if i == 0 {
				lines = append(lines, "  "+theme.Header.Render(e.key)+pad+"  "+theme.Dim.Render(l))
			} else {
				lines = append(lines, strings.Repeat(" ", keyW+4)+theme.Dim.Render(l))
			}
		}
	}
	return lines
}

// helpBox is the help overlay: a scrollable, searchable list of every binding.
func (m model) helpBox() string {
	lines := m.helpLines()
	footer := "/: search · ↑/↓/pgup/pgdn: scroll · esc/?/q: close"
	if m.help.searching {
		footer = "type to search · enter: done · esc: clear"
	}
	if h := m.helpHeight(); h > 0 && len(lines) > h {
		off := min(max(m.help.scroll, 0), len(lines)-h)
		footer += fmt.Sprintf(" · %d-%d/%d", off+1, off+h, len(lines))
		lines = lines[off : off+h]
	}
	search := theme.Dim.Render("press / to search")
	switch {
	case m.help.searching:
		search = theme.Accent.Render("/ ") + theme.Header.Render(m.help.query) + theme.Accent.Render("▏")
	case m.help.query != "":
		search = theme.Accent.Render("/ ") + theme.Header.Render(m.help.query)
	}
	return modalPanel("Keyboard shortcuts", search+"\n"+strings.Join(lines, "\n"), footer, m.helpWidth(), theme.Mauve)
}

// openHelp shows the help overlay.
func (m model) openHelp() model {
	m.overlay = overlayHelp
	return m
}

// closeHelp closes the help and drops search and scroll state.
func (m model) closeHelp() model {
	m.overlay, m.help = overlayNone, helpState{}
	return m
}

// scrollHelp moves the window by delta rows, clamped to the content.
func (m model) scrollHelp(delta int) model {
	if m.helpHeight() > 0 {
		m.help.scroll = min(max(m.help.scroll+delta, 0), max(0, len(m.helpLines())-m.helpHeight()))
	}
	return m
}

// keyHelp handles input while the help overlay is open (full capture). `/` focuses the search
// (printable keys are text, enter keeps the term, esc clears it); otherwise esc, ? and q close it
// and ↑/↓/pgup/pgdn scroll.
func (m model) keyHelp(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.Type {
	case tea.KeyEsc:
		if m.help.searching || m.help.query != "" {
			m.help.query, m.help.searching, m.help.scroll = "", false, 0
			return m, nil
		}
		return m.closeHelp(), nil
	case tea.KeyUp:
		return m.scrollHelp(-1), nil
	case tea.KeyDown:
		return m.scrollHelp(1), nil
	case tea.KeyPgUp:
		return m.scrollHelp(-m.helpHeight()), nil
	case tea.KeyPgDown:
		return m.scrollHelp(m.helpHeight()), nil
	}
	if m.help.searching {
		switch msg.Type {
		case tea.KeyEnter:
			m.help.searching = false
		case tea.KeyBackspace:
			if r := []rune(m.help.query); len(r) > 0 {
				m.help.query, m.help.scroll = string(r[:len(r)-1]), 0
			}
		case tea.KeyRunes, tea.KeySpace:
			m.help.query, m.help.scroll = m.help.query+string(msg.Runes), 0
		}
		return m, nil
	}
	switch {
	case keybind.Matches(msg, keys.Help), keybind.Matches(msg, keys.Quit):
		return m.closeHelp(), nil
	case keybind.Matches(msg, keys.Search):
		m.help.searching = true
	case keybind.Matches(msg, keys.Up):
		return m.scrollHelp(-1), nil
	case keybind.Matches(msg, keys.Down):
		return m.scrollHelp(1), nil
	}
	return m, nil
}
