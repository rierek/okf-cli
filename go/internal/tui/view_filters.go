// The filter bar of the search screen: six titled boxes, root first. A box with chosen values shows
// them in the accent colour, an empty one shows "(any)". Pattern from lif internal/tui/
// box_filter_bar.go at commit 2056715, adapted: okf's fields and values.

package tui

import (
	"os"
	"strconv"
	"strings"

	"github.com/charmbracelet/lipgloss"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// filterBarHeight is the rows of the bar: every box is three rows high.
const filterBarHeight = 3

// tildePath shortens a path under the home directory to `~/...`.
func tildePath(p string) string {
	if home, err := os.UserHomeDir(); err == nil && home != "" && home != "/" && strings.HasPrefix(p, home+"/") {
		return "~" + p[len(home):]
	}
	return p
}

// tail keeps the last w cells of s behind an ellipsis, as the end of a path tells roots apart.
func tail(s string, w int) string {
	if lipgloss.Width(s) <= w || w < 2 {
		return s
	}
	r := []rune(s)
	for len(r) > 0 && lipgloss.Width(string(r))+1 > w {
		r = r[1:]
	}
	return "…" + string(r)
}

// filterValue is the text of a value box of w cells: the chosen value, "<first> +N" for several,
// "(any)" for none.
func (f filterState) filterValue(field filterField, w int) string {
	sel := f.selected[field]
	peach := lipgloss.NewStyle().Foreground(theme.Peach)
	switch len(sel) {
	case 0:
		return theme.Muted.Render("(any)")
	case 1:
		return peach.Render(sel[0])
	}
	more := " +" + strconv.Itoa(len(sel)-1)
	return peach.Render(truncate(sel[0], w-len(more)) + more)
}

// filterBar renders the bar in exactly width cells.
func (m model) filterBar(width int) string {
	widths := gridColWidths(int(filterFieldCount), width)
	cells := make([]gridCell, filterFieldCount)
	for i := range cells {
		field := filterField(i)
		cells[i] = gridCell{label: filterLabels[i], value: m.filters.filterValue(field, widths[i]-6)}
	}
	cells[fieldRoot].value = tail(tildePath(m.root), widths[0]-6)
	focused := -1
	if m.focus == focusFilter {
		focused = int(m.filters.field)
	}
	return gridRow(cells, width, focused)
}
