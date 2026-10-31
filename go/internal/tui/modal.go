// Copied from lif internal/tui/modal.go at commit 2056715, adapted: no menuList (copied when a
// menu needs it); clampModalWidth comes from lif internal/tui/box_filter_facets.go.

package tui

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// rebaseBg re-opens the Base background colour after every inner ESC[0m reset. Without it, inner
// resets (theme.Header.Render, ...) let cells fall back to the terminal background. Profile aware;
// under the Ascii profile the colour carries no escape, so nothing leaks.
func rebaseBg(s string) string {
	c := lipgloss.ColorProfile().Color(string(theme.Base))
	if c == nil {
		return s
	}
	open := termenv.CSI + c.Sequence(true) + "m"
	return strings.ReplaceAll(s, "\x1b[0m", "\x1b[0m"+open)
}

// modalBox frames pre-rendered content as a floating overlay modal.
// border is theme.Mauve (default) or theme.Red (destructive dialogs).
func modalBox(inner string, width int, border lipgloss.Color) string {
	return lipgloss.NewStyle().
		Width(width).
		Border(lipgloss.RoundedBorder()).
		BorderForeground(border).
		BorderBackground(theme.Base).
		Background(theme.Base).
		Padding(0, 1).
		Render(rebaseBg(inner))
}

// modalPanel builds a standard modal: header title, body and an optional dim footer, inside
// modalBox. The body brings its own inner line breaks.
func modalPanel(title, body, footer string, width int, border lipgloss.Color) string {
	var b strings.Builder
	b.WriteString(theme.Header.Render(title) + "\n")
	b.WriteString(body)
	if footer != "" {
		b.WriteString("\n" + theme.Dim.Render(footer))
	}
	return modalBox(b.String(), width, border)
}

// clampModalWidth clamps the preferred width of a floating box to the terminal width: it shrinks
// on narrow terminals (termW-4 leaves two columns of margin on each side), floor 24.
func clampModalWidth(pref, termW int) int {
	w := pref
	if termW > 4 && termW-4 < w {
		w = termW - 4
	}
	if w < 24 {
		w = 24
	}
	return w
}
