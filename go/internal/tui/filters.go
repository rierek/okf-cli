// The filters of the search: the bar's state, the menu values of the active root, the --where
// expression the TUI builds from the choices, and the keys of the bar and of its value menus.
// Pattern from lif internal/tui/box_filter_facets.go at commit 2056715, adapted: the facets are
// okf's, a choice reruns the search, and the expression goes to the where compiler.

package tui

import (
	"fmt"
	"slices"
	"sort"
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// filterField is one field of the filter bar, left to right.
type filterField int

const (
	fieldRoot filterField = iota
	fieldBundle
	fieldType
	fieldTag
	fieldStatus
	fieldTier
	filterFieldCount
)

var filterLabels = [filterFieldCount]string{"Root", "Bundle", "Type", "Tag", "Status", "Tier"}

// whereFields are the --where fields the value fields map to; a bundle is a `path` prefix.
var whereFields = [filterFieldCount]string{fieldBundle: "path", fieldType: "type", fieldTag: "tag", fieldStatus: "status", fieldTier: "tier"}

// Values of the two fields whose values are fixed by the OKF spec (frontmatter-and-types).
var (
	statusValues = []string{"draft", "stable", "deprecated"}
	tierValues   = []string{"unverified", "machine-confirmed", "human-reviewed"}
)

// filterState is the filter bar: the focused field, the chosen values and the menu values.
type filterState struct {
	field    filterField                // the focused field of the bar
	selected [filterFieldCount][]string // chosen values per field, in menu order; the root is no filter
	options  [filterFieldCount][]string // the menu values of the active root
	loaded   bool                       // options hold the values of the active root
	cursor   int                        // the cursor of the open value menu, over the list the query leaves
	search   menuSearch                 // the query of the open value menu
	before   string                     // the expression when the open menu opened
}

// active reports whether any value is chosen.
func (f filterState) active() bool {
	for _, v := range f.selected {
		if len(v) > 0 {
			return true
		}
	}
	return false
}

// loadOptions reads the values the menus of root offer: its search bundles, its registered types,
// the tags its concepts use, and the fixed status and tier values. A value the where grammar
// cannot express (one that holds both quote kinds) is left out.
func loadOptions(root string) (opts [filterFieldCount][]string, err error) {
	bundles, err := catalogue.ListSearchBundles(root, false, "")
	if err != nil {
		return opts, err
	}
	types, err := catalogue.LoadTypes(root, "")
	if err != nil {
		return opts, err
	}
	tags, err := catalogue.AllTags(root)
	if err != nil {
		return opts, err
	}
	opts[fieldBundle] = expressible(bundles)
	opts[fieldType] = expressible(sortedKeys(types))
	opts[fieldTag] = expressible(tags.Sorted())
	opts[fieldStatus], opts[fieldTier] = statusValues, tierValues
	return opts, nil
}

func sortedKeys(set map[string]bool) []string {
	out := make([]string, 0, len(set))
	for k := range set {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func expressible(values []string) []string {
	return slices.DeleteFunc(slices.Clone(values), func(v string) bool {
		return strings.Contains(v, `"`) && strings.Contains(v, `'`)
	})
}

// ensureOptions loads the menu values of the active root once; a failure is an error toast and the
// menus stay empty until the next try.
func (m model) ensureOptions() (model, tea.Cmd) {
	if m.filters.loaded {
		return m, nil
	}
	opts, err := loadOptions(m.root)
	if err != nil {
		return m.showToast(toastError, "Reading the filter values failed", err.Error(), false)
	}
	m.filters.options, m.filters.loaded = opts, true
	return m, nil
}

// reselect sets the chosen values of field to the menu values that are on, in menu order, with
// toggle flipped when it is not empty.
func (f filterState) reselect(field filterField, toggle string) filterState {
	var out []string
	for _, o := range f.options[field] {
		on := slices.Contains(f.selected[field], o)
		if o == toggle {
			on = !on
		}
		if on {
			out = append(out, o)
		}
	}
	f.selected[field] = out
	return f
}

// quoteValue is v as a --where value: bare when the grammar allows it, else quoted with the quote
// kind v does not hold.
func quoteValue(v string) string {
	plain := v != "" && v != "and" && v != "or" && v != "not" && v != "in"
	for _, r := range v {
		if !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || strings.ContainsRune("-_./:", r)) {
			plain = false
		}
	}
	switch {
	case plain:
		return v
	case strings.Contains(v, `"`):
		return "'" + v + "'"
	}
	return `"` + v + `"`
}

// expression is the --where expression of the chosen values: a bundle is `path ~ <bundle>/`, the
// values of one field are ORed, the fields are ANDed. Nil without a choice.
func (f filterState) expression() *string {
	var groups []string
	for field := fieldBundle; field < filterFieldCount; field++ {
		var terms []string
		for _, v := range f.selected[field] {
			if field == fieldBundle {
				terms = append(terms, "path ~ "+quoteValue(v+"/"))
			} else {
				terms = append(terms, whereFields[field]+" = "+quoteValue(v))
			}
		}
		switch len(terms) {
		case 0:
		case 1:
			groups = append(groups, terms[0])
		default:
			groups = append(groups, "("+strings.Join(terms, " or ")+")")
		}
	}
	if len(groups) == 0 {
		return nil
	}
	expr := strings.Join(groups, " and ")
	return &expr
}

// exprText is the expression as text, "" without a choice.
func (f filterState) exprText() string {
	if e := f.expression(); e != nil {
		return *e
	}
	return ""
}

// dropMissing keeps the chosen values that the options of the active root hold and reports the
// ones it dropped as `field value`.
func (m model) dropMissing() (model, []string) {
	var dropped []string
	for field := fieldBundle; field < filterFieldCount; field++ {
		before := m.filters.selected[field]
		m.filters = m.filters.reselect(field, "")
		for _, v := range before {
			if !slices.Contains(m.filters.selected[field], v) {
				dropped = append(dropped, strings.ToLower(filterLabels[field])+" "+v)
			}
		}
	}
	return m, dropped
}

// clearFilters drops every chosen value but keeps the root, and reruns the search.
func (m model) clearFilters() (model, tea.Cmd) {
	if !m.filters.active() {
		return m, nil
	}
	m.filters.selected = [filterFieldCount][]string{}
	return m.rerun()
}

// rerun runs the newest query again, with the current filters. Nothing happens before the first
// search.
func (m model) rerun() (model, tea.Cmd) {
	if m.search.asked == "" {
		return m, nil
	}
	return m.runSearch(m.search.asked)
}

// keyFilterBar handles a key while the filter bar has the focus: left and right (h, l) move
// between the fields, enter opens the menu of the focused field, esc leaves the bar. tab and
// shift+tab step the focus ring and the global keys act before.
func (m model) keyFilterBar(msg tea.KeyMsg) (model, tea.Cmd) {
	switch {
	case keybind.Matches(msg, keys.Back):
		next, _ := m.setFocus(focusList)
		return next.(model), nil
	case keybind.Matches(msg, keys.FieldPrev):
		m.filters.field = max(m.filters.field-1, 0)
	case keybind.Matches(msg, keys.FieldNext):
		m.filters.field = min(m.filters.field+1, filterFieldCount-1)
	case keybind.Matches(msg, keys.Open):
		return m.openFilterField()
	}
	return m, nil
}

// openFilterField opens the root menu for the root field, the value menu for the others. A field
// without values opens nothing and says so.
func (m model) openFilterField() (model, tea.Cmd) {
	if m.filters.field == fieldRoot {
		return m.openRootMenu()
	}
	m, toast := m.ensureOptions()
	field := m.filters.field
	if len(m.filters.options[field]) == 0 {
		if toast != nil || !m.filters.loaded {
			return m, toast
		}
		return m.showToast(toastInfo, "No "+strings.ToLower(filterLabels[field])+" values in this root", "", false)
	}
	m.filters.cursor, m.filters.search = 0, menuSearch{}
	m.filters.before = m.filters.exprText()
	m.overlay = overlayFilterMenu
	return m, nil
}

// keyFilterMenu handles input while a value menu is open (full capture): up and down move the
// cursor, space, x and enter flip the value under it, / types a query that narrows the list, X
// clears every filter, esc clears a query or else closes the menu and reruns the search when the
// choice changed. The cursor indexes the list the query leaves.
func (m model) keyFilterMenu(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	field := m.filters.field
	if search, before, handled := m.filters.search.edit(msg); handled {
		m.filters.search = search
		if search.query != before {
			m.filters.cursor = 0
		}
		return m, nil
	}
	visible := m.filters.visible()
	switch {
	case keybind.Matches(msg, keys.Up):
		m.filters.cursor = max(m.filters.cursor-1, 0)
	case keybind.Matches(msg, keys.Down):
		m.filters.cursor = max(min(m.filters.cursor+1, len(visible)-1), 0)
	case keybind.Matches(msg, keys.Toggle), keybind.Matches(msg, keys.Open):
		if m.filters.cursor < len(visible) {
			m.filters = m.filters.reselect(field, visible[m.filters.cursor])
		}
	case keybind.Matches(msg, keys.FilterClear):
		m.filters.selected = [filterFieldCount][]string{}
	case keybind.Matches(msg, keys.Back):
		m.overlay = overlayNone
		if m.filters.exprText() != m.filters.before {
			return m.rerun()
		}
	}
	return m, nil
}

// menuSearch is the query of a menu: the text and whether the keys type it. It is the `/` search
// of the help overlay: printable keys are text while typing, enter keeps the term, esc clears it.
type menuSearch struct {
	query  string
	typing bool
}

// edit applies msg when the search owns it and reports the query before the key. Up, down and
// tab stay with the menu while typing; outside typing only `/` and esc on a non-empty query
// belong to the search.
func (s menuSearch) edit(msg tea.KeyMsg) (menuSearch, string, bool) {
	before := s.query
	if !s.typing {
		switch {
		case keybind.Matches(msg, keys.Search):
			s.typing = true
			return s, before, true
		case msg.Type == tea.KeyEsc && s.query != "":
			return menuSearch{}, before, true
		}
		return s, before, false
	}
	switch msg.Type {
	case tea.KeyUp, tea.KeyDown, tea.KeyTab, tea.KeyShiftTab:
		return s, before, false
	case tea.KeyEsc:
		return menuSearch{}, before, true
	case tea.KeyEnter:
		s.typing = false
	case tea.KeyBackspace:
		if r := []rune(s.query); len(r) > 0 {
			s.query = string(r[:len(r)-1])
		}
	case tea.KeyRunes, tea.KeySpace:
		s.query += string(msg.Runes)
	}
	return s, before, true
}

// line renders the query line: the typed text with a caret while typing.
func (s menuSearch) line() string {
	line := theme.Accent.Render("/ ") + theme.Header.Render(s.query)
	if s.typing {
		line += theme.Accent.Render("▏")
	}
	return line
}

// shown reports whether the query line is on screen.
func (s menuSearch) shown() bool { return s.typing || s.query != "" }

// visible is the menu list of the focused field that the query leaves, in menu order.
func (f filterState) visible() []string {
	opts := f.options[f.field]
	if f.search.query == "" {
		return opts
	}
	return slices.DeleteFunc(slices.Clone(opts), func(o string) bool { return !fuzzyMatch(f.search.query, o) })
}

// filterMenuBox renders the value menu of the focused field. The box is as wide as the longest
// option of the field and the longer of the two hints need, up to the terminal width; a longer
// option or query line ends in an ellipsis.
func (m model) filterMenuBox() string {
	field := m.filters.field
	opts := m.filters.options[field]
	visible := m.filters.visible()
	const (
		rowChrome  = 2 + 3 + 1 // cursor column, box, space
		hintIdle   = "enter/space toggle · / search · X clear · esc"
		hintTyping = "type to search · enter done · esc clear"
	)
	hint := hintIdle
	if m.filters.search.typing {
		hint = hintTyping
	}
	// Both hints size the box, so it keeps its width when / starts the search.
	need := max(lipgloss.Width(hintIdle), lipgloss.Width(hintTyping))
	for _, o := range opts {
		need = max(need, rowChrome+lipgloss.Width(o))
	}
	w := clampModalWidth(need+2, m.width) // two columns of padding
	rows := make([]string, len(visible))
	for i, o := range visible {
		box := theme.Dim.Render("[ ]")
		if slices.Contains(m.filters.selected[field], o) {
			box = theme.Accent.Render("[x]")
		}
		o = truncate(o, w-2-rowChrome)
		cursor, label := "  ", o
		if i == m.filters.cursor {
			cursor, label = theme.Accent.Render("▸ "), theme.Header.Render(o)
		}
		rows[i] = cursor + box + " " + label
	}
	if len(rows) == 0 {
		rows = []string{theme.Dim.Render("  no match")}
	}
	_, h := m.size()
	lead := 1 // the hint
	if m.filters.search.shown() {
		lead++
	}
	rows = windowAround(rows, max(h-9-lead, 3), m.filters.cursor)
	title := filterLabels[field]
	if len(visible) > len(rows) {
		title += fmt.Sprintf(" %d/%d", m.filters.cursor+1, len(visible))
	}
	head := theme.Muted.Render(truncate(hint, w-2))
	if m.filters.search.shown() {
		head += "\n" + truncate(m.filters.search.line(), w-2)
	}
	return modalPanel(title, head+"\n"+strings.Join(rows, "\n"), "", w, theme.Mauve)
}
