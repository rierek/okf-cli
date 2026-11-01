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

// renderPane draws p in a rounded border of outer width w and inner height h, with title on the top
// border. The border is Mauve when the pane has focus, Overlay otherwise; a focused list shows its
// cursor row with "▸ ".
func renderPane(p pane, title string, w, h int, focused bool) string {
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
	return titledBox(lines, title, w, col)
}

// titledBox frames lines in a rounded border of colour col and outer width w+2, with title in the
// top border (boxTopBorder, as lif draws a labelled panel).
func titledBox(lines []string, title string, w int, col lipgloss.Color) string {
	box := lipgloss.NewStyle().
		Width(w).
		Border(lipgloss.RoundedBorder()).BorderForeground(col).
		Render(strings.Join(lines, "\n"))
	_, rest, _ := strings.Cut(box, "\n")
	return boxTopBorder(title, w+2, lipgloss.NewStyle().Foreground(col)) + "\n" + rest
}
