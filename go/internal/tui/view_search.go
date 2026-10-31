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
	w, h := m.size()
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
	case overlayFilterMenu:
		out = placeOverlay(out, m.filterMenuBox(), w, h)
	case overlayRoot:
		out = placeOverlay(out, m.rootMenuBox(), w, h)
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
		{keys.Run, m.inInput()},
		{keys.Open, m.focus == focusFilter},
		{keys.FieldNext, m.focus == focusFilter},
		{keys.Down, !m.inInput() && len(m.search.hits) > 0},
		{keys.Layout, !m.inInput()},
		{keys.FocusIn, len(focusRing) > 1},
		{keys.FocusOut, len(focusRing) > 1},
		{keys.Search, !m.inInput()},
		{keys.Filter, !m.inInput()},
		{keys.FilterClear, !m.inInput() && m.filters.active()},
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

// chrome is the frame around the body: the header, the footer and the rows left for the body
// panes, borders included: the frame without header, query row, filter bar, footer and the two
// dividers.
func (m model) chrome(w, h int) (head, foot string, avail int) {
	innerW := w - 2
	head = m.header(innerW)
	foot = footer(renderBindings(m.footerBindings()), innerW)
	return head, foot, h - 2 - lipgloss.Height(head) - 1 - 1 - 1 - filterBarHeight - lipgloss.Height(foot)
}

// queryRow is the query field; while a search runs the indicator stands at its right end.
func (m model) queryRow(innerW int) string {
	m.query.Width = max(innerW-lipgloss.Width(m.query.Prompt)-1, 1)
	if !m.search.running {
		return m.query.View()
	}
	indicator := m.search.spinner.View() + " searching"
	m.query.Width = max(m.query.Width-lipgloss.Width(indicator)-1, 1)
	return m.query.View() + " " + indicator
}

// viewSearch is the search screen: header, query field, result list and detail pane, footer, all
// in the outer frame of w×h cells.
func (m model) viewSearch(w, h int) string {
	innerW := w - 2
	head, foot, avail := m.chrome(w, h)
	div := theme.Dim.Render(strings.Repeat("─", innerW))
	body := m.viewBody(max(avail-2, 1))

	content := head + "\n" + div + "\n" + m.queryRow(innerW) + "\n" + m.filterBar(innerW) + "\n" + body + "\n" + div + "\n" + foot
	return outerBorder(content, innerW)
}
