package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// layoutMode is what the body of the search screen shows; `v` steps through the modes.
type layoutMode int

const (
	layoutSplit  layoutMode = iota // result list at the left, detail pane at the right
	layoutList                     // result list at full width
	layoutDetail                   // detail pane of the focused hit at full width
	layoutCount
)

func (m model) nextLayout(back bool) model {
	step := layoutMode(1)
	if back {
		step = layoutCount - 1
	}
	m.layout = (m.layout + step) % layoutCount
	return m
}

// size is the terminal size, with the fallback View draws at before the first size message.
func (m model) size() (w, h int) {
	w, h = m.width, m.height
	if w <= 0 {
		w = 80
	}
	if h <= 0 {
		h = 24
	}
	return w, h
}

// geometry is the outer width of the list pane and of the detail pane (0: not shown) and the
// inner height of both.
func (m model) geometry() (listW, detailW, innerH int) {
	w, h := m.size()
	innerW := w - 2
	_, _, avail := m.chrome(w, h)
	innerH = max(avail-2, 1)
	switch m.layout {
	case layoutList:
		return innerW, 0, innerH
	case layoutDetail:
		return 0, innerW, innerH
	}
	listW = min(max(innerW*2/5, 24), max(innerW-24, 1))
	return listW, innerW - listW, innerH
}

// detailTextWidth is the width of a detail row: the pane without its border and the margin
// renderPane keeps.
func (m model) detailTextWidth() int {
	_, dw, _ := m.geometry()
	return max(dw-4, 1)
}

// viewBody is the body of the search screen: the panes the layout shows, each innerH rows high
// inside its border.
func (m model) viewBody(innerH int) string {
	lw, dw, _ := m.geometry()
	var panes []string
	if lw > 0 {
		panes = append(panes, m.listPane(lw, innerH))
	}
	if dw > 0 {
		panes = append(panes, m.detailPane(dw, innerH))
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, panes...)
}

// listPane is the result list: one row per hit, or a line that says why there is none.
func (m model) listPane(outerW, innerH int) string {
	s := m.search
	if len(s.hits) == 0 {
		rows := []string{theme.Muted.Render("No search yet."), theme.Muted.Render("Type a query, press enter.")}
		if s.ran {
			rows = []string{theme.Muted.Render(fmt.Sprintf("No hits for %q.", s.query))}
		}
		return renderPane(pane{rows: rows}, outerW-2, innerH, m.focus == focusList)
	}
	rowW := max(outerW-6, 1) // border, the cursor mark, and the margin renderPane keeps
	rows := make([]string, len(s.hits))
	for i, h := range s.hits {
		rows[i] = listRow(bufferMark(m.buffered(i)), h.Title, h.Type, h.Bundle, rowW)
	}
	start := windowStart(len(rows), innerH, s.cursor)
	return renderPane(pane{rows: windowAround(rows, innerH, s.cursor), cursor: s.cursor - start, isList: true}, outerW-2, innerH, m.focus == focusList)
}

// bufferMark is the two-cell mark of a list row that is in the buffer.
func bufferMark(buffered bool) string {
	if buffered {
		return theme.Accent.Render("◆ ")
	}
	return "  "
}

// listRow is one list row: the two-cell mark, the title, then type and bundle dimmed.
func listRow(mark, title, typ, bundle string, w int) string {
	w -= 2
	meta := truncate(typ+" · "+bundle, max(w/2, 1))
	titleW := max(w-ansi.StringWidth(meta)-2, 1)
	title = truncate(title, titleW)
	pad := strings.Repeat(" ", max(titleW-ansi.StringWidth(title), 0)+2)
	return mark + title + pad + theme.Muted.Render(meta)
}

// detailPane shows the focused hit, scrolled by the user.
func (m model) detailPane(outerW, innerH int) string {
	rows := m.detailRows(max(outerW-4, 1))
	scroll := min(m.search.detailScroll, max(len(rows)-innerH, 0))
	return renderPane(pane{rows: rows[scroll:]}, outerW-2, innerH, false)
}

const detailLabelW = 12

// detailField is one `label  value` block; a long value wraps under its own first line.
func detailField(label, value string, w int) []string {
	lines := strings.Split(wrapText(value, max(w-detailLabelW, 1)), "\n")
	out := make([]string, len(lines))
	for i, l := range lines {
		head := strings.Repeat(" ", detailLabelW)
		if i == 0 {
			head = theme.Muted.Render(fmt.Sprintf("%-*s", detailLabelW, label))
		}
		out[i] = head + l
	}
	return out
}

// detailRows are the rows of the detail pane at text width w: the metadata of the focused hit,
// its absolute path, description, snippet and the H2/H3 table of contents.
func (m model) detailRows(w int) []string {
	h := m.search.focused()
	if h == nil {
		return []string{theme.Muted.Render("(no hit selected)")}
	}
	or := func(s, none string) string {
		if s == "" {
			return none
		}
		return s
	}
	stale := "no"
	if h.Stale {
		stale = "yes"
	}
	rows := []string{theme.Header.Render(truncate(h.Title, w))}
	rows = append(rows, detailField("type", or(h.Type, "-"), w)...)
	rows = append(rows, detailField("bundle", h.Bundle, w)...)
	rows = append(rows, detailField("tags", or(strings.Join(h.Tags, ", "), "-"), w)...)
	rows = append(rows, detailField("provenance", h.Provenance, w)...)
	rows = append(rows, detailField("tier", or(h.Tier, "-"), w)...)
	rows = append(rows, detailField("stale", stale, w)...)
	rows = append(rows, detailField("path", h.Abs, w)...)
	rows = append(rows, detailField("description", or(h.Description, "-"), w)...)
	rows = append(rows, detailField("snippet", or(h.Snippet, "-"), w)...)
	rows = append(rows, "", theme.Muted.Render("Contents"))
	if len(m.search.headings) == 0 {
		rows = append(rows, theme.Muted.Render("(no H2 or H3 headings)"))
	}
	for _, hd := range m.search.headings {
		rows = append(rows, strings.Repeat("  ", hd.Level-2)+"- "+hd.Text)
	}
	return rows
}
