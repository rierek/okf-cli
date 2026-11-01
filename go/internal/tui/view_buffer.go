package tui

import (
	"fmt"
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

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
	cursor := m.bufCursor
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
	case keybind.Matches(msg, keys.DetailDown), keybind.Matches(msg, keys.DetailUp):
		w, h := m.size()
		_, previewW, topH, _ := m.bufferLayout(w, h)
		m.bufScroll, _ = scrollKey(msg, m.bufScroll, len(m.bufferPreviewRows(max(previewW-4, 1))), topH)
	case keybind.Matches(msg, keys.BufferDrop) && n > 0:
		m.buf = m.buf.remove(m.bufCursor)
		m.bufCursor = min(m.bufCursor, max(n-2, 0))
		return m.focusBuffer(), nil
	case keybind.Matches(msg, keys.BufferClear) && n > 0:
		return m.openConfirm(clearBufferDialog(n)), nil
	case keybind.Matches(msg, keys.Note) && n > 0:
		return m.openNote(m.buf.entries[m.bufCursor])
	}
	if m.bufCursor != cursor {
		m = m.focusBuffer()
	}
	return m, nil
}

// bufferNoteRows is the height of the note pane under the buffer list and preview, borders
// included.
const bufferNoteRows = 6

// bufferLayout is the geometry of the buffer view in w×h cells: the outer widths of the list and
// the preview, the inner height of both, and the inner height of the note pane (0: too little room
// to show it).
func (m model) bufferLayout(w, h int) (listW, previewW, topH, noteH int) {
	_, _, avail := m.chrome(w, h)
	avail += queryRows + filterBarHeight // no query field and no filter bar on this screen
	noteOuter := 0
	if avail >= 2*bufferNoteRows {
		noteOuter = bufferNoteRows
	}
	listW, previewW = splitWidths(w - 2)
	return listW, previewW, max(avail-noteOuter-2, 1), max(noteOuter-2, 0)
}

// viewBuffer is the buffer screen: header, the entries in the order they were added beside the
// preview of the entry under the cursor, its note below, footer, in the outer frame of w×h cells.
func (m model) viewBuffer(w, h int) string {
	innerW := w - 2
	head, foot, _ := m.chrome(w, h)
	div := theme.Dim.Render(strings.Repeat("─", innerW))
	listW, previewW, topH, noteH := m.bufferLayout(w, h)

	body := lipgloss.JoinHorizontal(lipgloss.Top, m.bufferList(listW, topH), m.bufferPreview(previewW, topH))
	if noteH > 0 {
		body += "\n" + m.bufferNote(innerW, noteH)
	}
	content := head + "\n" + div + "\n" + body + "\n" + div + "\n" + foot
	return outerBorder(content, innerW)
}

// focusBuffer loads the headings of the entry under the cursor and resets the preview scroll.
func (m model) focusBuffer() model {
	m.bufScroll, m.bufHeadings = 0, nil
	if m.bufCursor < len(m.buf.entries) {
		m.bufHeadings = headingsOf(m.buf.entries[m.bufCursor].Abs)
	}
	return m
}

// bufferList is the entry list: one row per entry in insertion order, with a note marker, title,
// type and bundle.
func (m model) bufferList(outerW, innerH int) string {
	es := m.buf.entries
	if len(es) == 0 {
		rows := []string{theme.Muted.Render("The buffer is empty."), theme.Muted.Render("Press space on a hit to add it.")}
		return renderPane(pane{rows: rows}, "Buffer", outerW-2, innerH, true)
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
	return renderPane(pane{rows: windowAround(rows, innerH, m.bufCursor), cursor: m.bufCursor - start, isList: true}, "Buffer", outerW-2, innerH, true)
}

// bufferPreviewRows are the rows of the preview of the entry under the cursor at text width w:
// what the search preview shows of a hit, path included.
func (m model) bufferPreviewRows(w int) []string {
	if m.bufCursor >= len(m.buf.entries) {
		return []string{theme.Muted.Render("(no entry selected)")}
	}
	hit := m.buf.entries[m.bufCursor].hit()
	return previewRows(&hit, m.bufHeadings, w)
}

// bufferPreview is the preview pane of the entry under the cursor, scrolled by the user.
func (m model) bufferPreview(outerW, innerH int) string {
	return previewPane(m.bufferPreviewRows(max(outerW-4, 1)), m.bufScroll, outerW, innerH)
}

// bufferNote shows the note of the entry under the cursor, or says there is none.
func (m model) bufferNote(outerW, innerH int) string {
	var rows []string
	if m.bufCursor < len(m.buf.entries) {
		if note := m.buf.entries[m.bufCursor].Note; note != "" {
			rows = strings.Split(wrapText(note, max(outerW-4, 1)), "\n")
		} else {
			rows = []string{theme.Muted.Render("No note, press n to write one.")}
		}
	}
	return renderPane(pane{rows: rows}, "Note", outerW-2, innerH, false)
}

// bufferCount is the header's buffer count.
func (m model) bufferCount() string {
	return theme.Muted.Render("buffer ") + theme.Accent.Render(fmt.Sprint(len(m.buf.entries)))
}
