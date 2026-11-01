package tui

import (
	"fmt"
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// noteCaller names the note box in the editor's textEditedMsg.
const noteCaller = "note"

// noteMark is the two-cell mark of a buffer row that carries a note.
const noteMark = "✎ "

// keyBufferHit handles the buffer keys of the focused hit on the search screen: space adds or
// removes it, n writes its note, b opens the buffer view. ok is false for a key it does not own.
func (m model) keyBufferHit(msg tea.KeyMsg) (next model, cmd tea.Cmd, ok bool) {
	switch {
	case keybind.Matches(msg, keys.Buffer):
		return m.openBuffer(), nil, true
	case keybind.Matches(msg, keys.BufferToggle) && m.search.focused() != nil:
		m.buf = m.buf.toggle(entryOf(*m.search.focused()))
		return m, nil, true
	case keybind.Matches(msg, keys.Note) && m.search.focused() != nil:
		next, cmd = m.openNote(entryOf(*m.search.focused()))
		return next, cmd, true
	}
	return m, nil, false
}

// openNote opens the note box of e, filled with its current note. A file that is not buffered yet
// joins the buffer when the note is saved non-empty.
func (m model) openNote(e bufferEntry) (model, tea.Cmd) {
	if i := m.buf.index(e.id); i >= 0 {
		e.Note = m.buf.entries[i].Note
	}
	title := "Note: " + truncate(e.Title, max(m.textWidth()-8, 1))
	return m.openText(noteCaller, title, e.Note, func(m model, text string) (model, tea.Cmd) {
		m.buf = m.buf.setNote(e, text)
		return m, nil
	})
}

// keyBuffer handles the keys of the buffer view: the cursor, x removes the entry, c clears the
// buffer after a confirm dialog, n writes the note, b or esc leaves the view.
func (m model) keyBuffer(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	n := len(m.buf.entries)
	switch {
	case keybind.Matches(msg, keys.BufferBack):
		m.screen = screenSearch
	case keybind.Matches(msg, keys.Up):
		m.bufCursor = max(m.bufCursor-1, 0)
	case keybind.Matches(msg, keys.Down):
		m.bufCursor = min(m.bufCursor+1, max(n-1, 0))
	case keybind.Matches(msg, keys.Top):
		m.bufCursor = 0
	case keybind.Matches(msg, keys.Bottom):
		m.bufCursor = max(n-1, 0)
	case keybind.Matches(msg, keys.BufferDrop) && n > 0:
		m.buf = m.buf.remove(m.bufCursor)
		m.bufCursor = min(m.bufCursor, max(n-2, 0))
	case keybind.Matches(msg, keys.BufferClear) && n > 0:
		return m.openConfirm(clearBufferDialog(n)), nil
	case keybind.Matches(msg, keys.Note) && n > 0:
		return m.openNote(m.buf.entries[m.bufCursor])
	}
	return m, nil
}

// bufferDetailRows is the height of the entry pane under the buffer list, borders included.
const bufferDetailRows = 8

// viewBuffer is the buffer screen: header, the entries in the order they were added, the path
// and note of the entry under the cursor, footer, in the outer frame of w×h cells.
func (m model) viewBuffer(w, h int) string {
	innerW := w - 2
	head, foot, avail := m.chrome(w, h)
	avail += 1 + filterBarHeight // no query row and no filter bar on this screen
	div := theme.Dim.Render(strings.Repeat("─", innerW))

	detailH := 0
	if avail >= 2*bufferDetailRows {
		detailH = bufferDetailRows
	}
	list := m.bufferList(innerW, max(avail-detailH-2, 1))
	body := list
	if detailH > 0 {
		body += "\n" + m.bufferDetail(innerW, detailH-2)
	}
	content := head + "\n" + div + "\n" + body + "\n" + div + "\n" + foot
	return outerBorder(content, innerW)
}

// bufferList is the entry list: one row per entry in insertion order, with a note marker, title,
// type and bundle.
func (m model) bufferList(outerW, innerH int) string {
	es := m.buf.entries
	if len(es) == 0 {
		rows := []string{theme.Muted.Render("The buffer is empty."), theme.Muted.Render("Press space on a hit to add it.")}
		return renderPane(pane{rows: rows}, outerW-2, innerH, true)
	}
	rowW := max(outerW-6, 1)
	rows := make([]string, len(es))
	for i, e := range es {
		mark := "  "
		if e.Note != "" {
			mark = theme.Accent.Render(noteMark)
		}
		rows[i] = listRow(mark, e.Title, e.Type, e.Bundle, rowW)
	}
	start := windowStart(len(rows), innerH, m.bufCursor)
	return renderPane(pane{rows: windowAround(rows, innerH, m.bufCursor), cursor: m.bufCursor - start, isList: true}, outerW-2, innerH, true)
}

// bufferDetail shows the path, tags and note of the entry under the cursor.
func (m model) bufferDetail(outerW, innerH int) string {
	var rows []string
	if m.bufCursor < len(m.buf.entries) {
		e := m.buf.entries[m.bufCursor]
		tw := max(outerW-4, 1)
		rows = append(rows, detailField("path", e.Abs, tw)...)
		if len(e.Tags) > 0 {
			rows = append(rows, detailField("tags", strings.Join(e.Tags, ", "), tw)...)
		}
		if e.Note == "" {
			rows = append(rows, detailField("note", theme.Muted.Render("none, press n"), tw)...)
		} else {
			rows = append(rows, detailField("note", e.Note, tw)...)
		}
	}
	return renderPane(pane{rows: rows}, outerW-2, innerH, false)
}

// bufferCount is the header's buffer count.
func (m model) bufferCount() string {
	return theme.Muted.Render("buffer ") + theme.Accent.Render(fmt.Sprint(len(m.buf.entries)))
}
