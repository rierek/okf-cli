// The types and tags views: secondary screens that only the command center opens. Types lists
// the catalogue's TYPES.md (name and description, read as `okf info` reads it); tags lists the
// tags with their usage counts, as `okf tags` lists them. Both read in process on opening.

package tui

import (
	"fmt"
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/ansi"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/info"
	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// catalogueView is the data and the cursor of screenTypes and screenTags.
type catalogueView struct {
	types        []info.TypeDef
	typesMissing bool // the root has no TYPES.md
	tags         []catalogue.TagCount
	cursor       int
}

// openTypes reads TYPES.md of the root and shows the types view. A read error stays a toast and
// the screen stays.
func (m model) openTypes() (tea.Model, tea.Cmd) {
	defs, ok, err := info.Types(m.root)
	if err != nil {
		return m.showToast(toastError, "Types not read", err.Error(), true)
	}
	m.cat = catalogueView{types: defs, typesMissing: !ok}
	return m.openCatalogue(screenTypes), nil
}

// openTags counts the tags of the root, most used first, and shows the tags view. ponytail: the
// scan runs on the UI loop; move it behind a message if a catalogue gets slow to read.
func (m model) openTags() (tea.Model, tea.Cmd) {
	counts, err := catalogue.AllTags(m.root)
	if err != nil {
		return m.showToast(toastError, "Tags not read", err.Error(), true)
	}
	m.cat = catalogueView{tags: counts.Ranked()}
	return m.openCatalogue(screenTags), nil
}

func (m model) openCatalogue(s screenKind) model {
	m.screen = s
	m.focus = focusList
	m.query.Blur()
	return m
}

// catalogueLen is the number of rows of the open types or tags view.
func (m model) catalogueLen() int {
	if m.screen == screenTypes {
		return len(m.cat.types)
	}
	return len(m.cat.tags)
}

// keyCatalogue handles the keys of the types and tags views: the cursor, b or esc leaves.
func (m model) keyCatalogue(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	last := max(m.catalogueLen()-1, 0)
	switch {
	case keybind.Matches(msg, keys.BufferBack):
		m.screen = screenSearch
	case keybind.Matches(msg, keys.Up):
		m.cat.cursor = max(m.cat.cursor-1, 0)
	case keybind.Matches(msg, keys.Down):
		m.cat.cursor = min(m.cat.cursor+1, last)
	case keybind.Matches(msg, keys.Top):
		m.cat.cursor = 0
	case keybind.Matches(msg, keys.Bottom):
		m.cat.cursor = last
	}
	return m, nil
}

// viewCatalogue is the types or tags screen: header, one list, footer, in the outer frame of w×h
// cells.
func (m model) viewCatalogue(w, h int) string {
	innerW := w - 2
	head, foot, avail := m.chrome(w, h)
	avail += queryRows + filterBarHeight // no query box and no filter bar on this screen
	div := theme.Dim.Render(strings.Repeat("─", innerW))
	content := head + "\n" + div + "\n" + m.cataloguePane(innerW, max(avail-2, 1)) + "\n" + div + "\n" + foot
	return outerBorder(content, innerW)
}

// cataloguePane is the row list of the open view: a type is its name and description, a tag its
// name and usage count, both in columns.
func (m model) cataloguePane(outerW, innerH int) string {
	var rows []string
	title := map[screenKind]string{screenTypes: "Types", screenTags: "Tags"}[m.screen]
	switch {
	case m.screen == screenTypes && m.cat.typesMissing:
		rows = []string{theme.Muted.Render("(missing: TYPES.md)")}
	case m.screen == screenTypes:
		nameW := 0
		for _, t := range m.cat.types {
			nameW = max(nameW, ansi.StringWidth(t.Name))
		}
		for _, t := range m.cat.types {
			rows = append(rows, theme.Accent.Render(padRight(t.Name, nameW))+"  "+theme.Muted.Render(t.Description))
		}
	default:
		nameW, countW := 0, 0
		for _, t := range m.cat.tags {
			nameW = max(nameW, ansi.StringWidth(t.Tag))
			countW = max(countW, len(fmt.Sprint(t.Count)))
		}
		for _, t := range m.cat.tags {
			rows = append(rows, padRight(t.Tag, nameW)+"  "+theme.Muted.Render(fmt.Sprintf("%*d", countW, t.Count)))
		}
	}
	if len(rows) == 0 {
		msg := map[screenKind]string{screenTypes: "No types in TYPES.md.", screenTags: "No tags found."}[m.screen]
		return renderPane(pane{rows: []string{theme.Muted.Render(msg)}}, title, outerW-2, innerH, true)
	}
	start := windowStart(len(rows), innerH, m.cat.cursor)
	return renderPane(pane{rows: windowAround(rows, innerH, m.cat.cursor), cursor: m.cat.cursor - start, isList: true}, title, outerW-2, innerH, true)
}

// padRight pads s with spaces to w cells.
func padRight(s string, w int) string {
	return s + strings.Repeat(" ", max(w-ansi.StringWidth(s), 0))
}
