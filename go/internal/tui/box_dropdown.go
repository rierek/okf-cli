// Copied from lif internal/tui/box_dropdown.go (clampVisible, borderDashes, boxTopBorder,
// dropdownBox) and internal/tui/box_detail_form.go (gridColWidths, gridRow) at commit 2056715,
// adapted: no hotkey badge, a cell is a label and a value.

package tui

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// boxGap is the blank column between two adjacent boxes of a row.
const boxGap = 1

func clampVisible(s string, n int) string {
	if n < 0 {
		n = 0
	}
	return ansi.Truncate(s, n, "")
}

func borderDashes(n int) string {
	if n < 1 {
		return ""
	}
	return strings.Repeat("─", n)
}

// boxTopBorder builds the ╭─ label ─…─╮ row at exactly width cells: the label in its own style,
// dashes and corners in frame.
func boxTopBorder(label string, width int, frame lipgloss.Style) string {
	labelStyle := lipgloss.NewStyle().Foreground(theme.Subtext)
	labelText := clampVisible(label, width-6)
	labelSeg := frame.Render("─ ") + labelStyle.Render(labelText) + frame.Render(" ")
	topFill := width - 2 - (2 + lipgloss.Width(labelText) + 1)
	return frame.Render("╭") + labelSeg + frame.Render(borderDashes(topFill)) + frame.Render("╮")
}

// dropdownBox renders the three-line widget in exactly width cells: the label in the top border,
// the (already styled) value and a ▾ inside. A focused box has the accent frame.
func dropdownBox(label, value string, width int, focused bool) string {
	if width < 8 {
		width = 8
	}
	borderColor := theme.Overlay
	if focused {
		borderColor = theme.Mauve
	}
	frame := lipgloss.NewStyle().Foreground(borderColor)

	inner := width - 6
	val := clampVisible(value, inner)
	pad := max(inner-lipgloss.Width(val), 0)
	mid := frame.Render("│") + " " + val + strings.Repeat(" ", pad) + " " + theme.Chevron.Render("▾") + " " + frame.Render("│")
	bot := frame.Render("╰") + frame.Render(borderDashes(width-2)) + frame.Render("╯")
	return boxTopBorder(label, width, frame) + "\n" + mid + "\n" + bot
}

// gridColWidths is the width of each of n columns that fill width cells with boxGap between
// them; the remainder goes to the first columns.
func gridColWidths(n, width int) []int {
	if n <= 0 {
		return nil
	}
	avail := width - (n-1)*boxGap
	widths := make([]int, n)
	for i := range widths {
		widths[i] = avail / n
		if i < avail%n {
			widths[i]++
		}
	}
	return widths
}

// gridCell is one column of gridRow.
type gridCell struct{ label, value string }

// gridRow renders cells as one row of dropdown boxes in exactly width cells; focusedCol is the
// column with the focus frame, -1 for none.
func gridRow(cells []gridCell, width, focusedCol int) string {
	widths := gridColWidths(len(cells), width)
	var row string
	for i, c := range cells {
		box := dropdownBox(c.label, c.value, widths[i], i == focusedCol)
		if i == 0 {
			row = box
			continue
		}
		row = lipgloss.JoinHorizontal(lipgloss.Top, row, " \n \n ", box)
	}
	return row
}
