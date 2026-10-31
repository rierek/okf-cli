// Copied from lif internal/tui/render_shared.go at commit 2056715, adapted: only renderPane (the
// tag chips and borderedPane are copied when a screen needs them).

package tui

import (
	"strings"

	"github.com/charmbracelet/lipgloss"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// pane is the content of one bordered pane: rows, plus a cursor when it is a list.
type pane struct {
	rows   []string
	cursor int
	isList bool
}

// renderPane draws p in a rounded border of outer width w and inner height h. The border is Mauve
// when the pane has focus, Overlay otherwise; a focused list shows its cursor row with "▸ ".
func renderPane(p pane, w, h int, focused bool) string {
	lines := make([]string, 0, h)
	for i := 0; i < len(p.rows) && len(lines) < h; i++ {
		row := truncate(p.rows[i], w-2)
		if p.isList && i == p.cursor && focused {
			row = theme.Accent.Render("▸ ") + row
		} else if p.isList {
			row = "  " + row
		}
		lines = append(lines, row)
	}
	for len(lines) < h { // pad to the inner height instead of forcing Height()
		lines = append(lines, "")
	}
	col := theme.Overlay
	if focused {
		col = theme.Mauve
	}
	return lipgloss.NewStyle().
		Width(w).
		Border(lipgloss.RoundedBorder()).BorderForeground(col).
		Render(strings.Join(lines, "\n"))
}
