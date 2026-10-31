// Frame composition from lif internal/tui/view_browse_repo.go (viewBrowseRepo, composeOverlays,
// footerBindings, View) at commit 2056715, adapted. Written, not copied.

package tui

import (
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	"github.com/charmbracelet/lipgloss"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// toastDismissHint is the footer hint of a sticky toast; the key is handled in handleKey.
var toastDismissHint = keybind.NewBinding(keybind.WithKeys("esc"), keybind.WithHelp("esc", "dismiss"))

// View renders the screen, the open overlay over it and the toast over both.
func (m model) View() string {
	w, h := m.width, m.height
	if w <= 0 {
		w = 80
	}
	if h <= 0 {
		h = 24
	}
	return m.renderToast(m.composeOverlays(m.viewSearch(w, h), w, h))
}

// composeOverlays draws the open overlay centered over the screen.
func (m model) composeOverlays(out string, w, h int) string {
	switch m.overlay {
	case overlayHelp:
		out = placeOverlay(out, m.helpBox(), w, h)
	case overlayConfirm:
		out = placeOverlay(out, m.confirmBox(), w, h)
	case overlayRefresh:
		out = placeOverlay(out, m.refreshBox(), w, h)
	}
	return out
}

// footerBindings are the key hints of the footer: the keys that act in the current state.
func (m model) footerBindings() []keybind.Binding {
	cands := []struct {
		b   keybind.Binding
		act bool
	}{
		{toastDismissHint, m.escDismissesToast()},
		{keys.FocusIn, len(focusRing) > 1},
		{keys.FocusOut, len(focusRing) > 1},
		{keys.Search, !m.inInput()},
		{keys.Refresh, !m.inInput()},
	}
	var out []keybind.Binding
	for _, c := range cands {
		if c.act {
			out = append(out, c.b)
		}
	}
	return out
}

// header is the first line: the active root and the screen title at the left, the global key
// hints at the right.
func (m model) header(innerW int) string {
	return breadcrumb(m.root, "Search", m.dots()+"  "+renderBindings(globalBindings(m.inInput())), innerW)
}

// viewSearch is the search screen: header, query field, results pane, footer, all in the outer
// frame of w×h cells.
func (m model) viewSearch(w, h int) string {
	innerW := w - 2
	head := m.header(innerW)
	foot := footer(renderBindings(m.footerBindings()), innerW)
	div := theme.Dim.Render(strings.Repeat("─", innerW))

	m.query.Width = max(innerW-lipgloss.Width(m.query.Prompt)-1, 1)
	queryRow := m.query.View()

	// Rows left for the results pane, borders included: the frame without header, query row,
	// footer and the two dividers.
	avail := h - 2 - lipgloss.Height(head) - 1 - 1 - 1 - lipgloss.Height(foot)
	body := renderPane(pane{rows: []string{theme.Muted.Render("No search yet.")}}, innerW-2, max(avail-2, 1), m.focus == focusList)

	content := head + "\n" + div + "\n" + queryRow + "\n" + body + "\n" + div + "\n" + foot
	return outerBorder(content, innerW)
}
