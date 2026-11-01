// Copied from lif internal/tui/view.go at commit 2056715, adapted: breadcrumb, wrapText,
// renderBindings, footer, truncate and outerBorder; no Chrome, scroll view or status line.

package tui

import (
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// breadcrumb is the header line: "> repo: title" on the left, the global key hints on the right.
// A line too narrow for both stacks them instead of overflowing.
func breadcrumb(repo, title, globalHint string, width int) string {
	left := theme.Chevron.Render("> " + repo)
	if title != "" {
		left += theme.Chevron.Render(":") + " " + theme.Header.Render(title)
	}
	right := globalHint
	if lipgloss.Width(left)+lipgloss.Width(right)+1 > width {
		return ansi.Truncate(left, width, "…") + "\n" + ansi.Truncate(right, width, "…")
	}
	gap := max(width-lipgloss.Width(left)-lipgloss.Width(right), 1)
	return left + strings.Repeat(" ", gap) + right
}

// wrapText wraps s to w cells on word boundaries, hard-wrapping overlong words.
func wrapText(s string, w int) string {
	return ansi.Hardwrap(ansi.Wordwrap(s, max(w, 1), ""), max(w, 1), true)
}

const nbsp = "\u00a0"

// renderBindings renders key hints as "key desc · key desc". Space inside a description is a
// non-breaking space so the footer wraps between hints, never inside one.
func renderBindings(bs []keybind.Binding) string {
	parts := make([]string, 0, len(bs))
	for _, b := range bs {
		h := b.Help()
		if h.Key != "" {
			desc := strings.ReplaceAll(h.Desc, " ", nbsp)
			parts = append(parts, theme.BindingKey.Render(h.Key)+nbsp+theme.BindingDesc.Render(desc))
		}
	}
	return strings.Join(parts, " · ")
}

// footer wraps the pre-rendered hint line to width.
func footer(hint string, width int) string {
	return wrapText(hint, width)
}

// truncate cuts s to w cells with an ellipsis.
func truncate(s string, w int) string {
	if w < 1 {
		return ""
	}
	return ansi.Truncate(s, w, "…")
}

// outerBorder wraps content in the rounded frame around the whole screen.
func outerBorder(content string, width int) string {
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(theme.Overlay).
		Width(width).
		Render(content)
}
