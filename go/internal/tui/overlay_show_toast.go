// Copied from lif internal/tui/overlay_show_toast.go at commit 2056715, adapted: no click target,
// toastExpiredMsg and toastTimeout from internal/tui/messages.go.

package tui

import (
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// The toast is a colour-coded box in the top-right corner. There is one slot, no stack: a new
// toast replaces the old one. It disappears after a kind-specific time, except a sticky toast,
// which stays until a newer toast replaces it or the user dismisses it with esc. A toast never
// blocks the keyboard.

type toastKind int

const (
	toastInfo  toastKind = iota // Blue: note, success
	toastWarn                   // Yellow: warning, not blocking
	toastError                  // Red: error
)

// toastState is the one toast slot. seq is the generation, drawn from model.toastSeqCounter, which
// is never reset: a toastExpiredMsg clears the toast only when seq still matches.
type toastState struct {
	kind    toastKind
	title   string
	context string // second, dimmed line (optional)
	seq     int
	sticky  bool
	setAt   time.Time
}

// toastExpiredMsg ends the auto-dismiss timer of toast generation seq.
type toastExpiredMsg struct{ seq int }

func toastTimeout(seq int, kind toastKind) tea.Cmd {
	return tea.Tick(toastDuration(kind), func(time.Time) tea.Msg {
		return toastExpiredMsg{seq}
	})
}

// toastDebounceWindow: a second showToast call within this span of the last toast replaces its
// content in place instead of starting a new generation and a new timer.
const toastDebounceWindow = 300 * time.Millisecond

// toastDuration returns the kind-specific auto-dismiss duration.
func toastDuration(kind toastKind) time.Duration {
	switch kind {
	case toastError:
		return 8 * time.Second
	case toastWarn:
		return 3 * time.Second
	default:
		return 5 * time.Second
	}
}

// showToast fills the toast slot and returns the timer command, or nil for a sticky toast and for
// a debounced replacement.
func (m model) showToast(kind toastKind, title, context string, sticky bool) (model, tea.Cmd) {
	now := time.Now()
	if m.toast != nil && now.Sub(m.toast.setAt) < toastDebounceWindow {
		t := *m.toast
		t.kind, t.title, t.context, t.sticky, t.setAt = kind, title, context, sticky, now
		m.toast = &t
		return m, nil // the running timer stays valid
	}
	m.toastSeqCounter++
	seq := m.toastSeqCounter
	m.toast = &toastState{kind: kind, title: title, context: context, seq: seq, sticky: sticky, setAt: now}
	if sticky {
		return m, nil
	}
	return m, toastTimeout(seq, kind)
}

// handleToastExpired clears the toast when the expired generation is still the current one.
func (m model) handleToastExpired(msg toastExpiredMsg) (tea.Model, tea.Cmd) {
	if m.toast != nil && msg.seq == m.toast.seq {
		m.toast = nil
	}
	return m, nil
}

// dismissToast empties the slot.
func (m model) dismissToast() (tea.Model, tea.Cmd) {
	m.toast = nil
	return m, nil
}

// escDismissesToast reports whether esc clears a sticky toast now: only outside a text input,
// where esc already has a meaning.
func (m model) escDismissesToast() bool {
	return m.toast != nil && m.toast.sticky && !m.inInput()
}

func toastKindColor(k toastKind) lipgloss.Color {
	switch k {
	case toastError:
		return theme.Red
	case toastWarn:
		return theme.Yellow
	default:
		return theme.Blue
	}
}

const (
	toastBoxMinWidth = 32
	toastBoxMaxWidth = 70
)

// toastBoxWidth sizes the toast to its content, between the floor and the cap, and never wider
// than the terminal leaves.
func toastBoxWidth(termW, contentW int) int {
	capW := toastBoxMaxWidth
	if termW > 4 && termW-4 < capW {
		capW = termW - 4
	}
	w := contentW + 4
	if w > capW {
		w = capW
	}
	if w < toastBoxMinWidth {
		w = toastBoxMinWidth
	}
	return w
}

func (m model) toastBox() string {
	t := m.toast
	col := toastKindColor(t.kind)

	contentW := ansi.StringWidth("● " + t.title)
	if t.context != "" {
		contentW = max(contentW, ansi.StringWidth(t.context))
	}
	outerW := toastBoxWidth(m.width, contentW)
	innerW := outerW - 4 // modalBox: border (2) + padding (0,1)*2 = 4

	dot := lipgloss.NewStyle().Foreground(col).Render("●")
	titleStyle := lipgloss.NewStyle().Foreground(col).Bold(true)
	titleLines := strings.Split(wrapText(t.title, innerW-2), "\n") // -2: dot and space
	line1 := dot + " " + titleStyle.Render(titleLines[0])
	for _, extra := range titleLines[1:] {
		line1 += "\n  " + titleStyle.Render(extra) // indent aligns under "● "
	}
	body := line1
	if t.context != "" {
		body += "\n" + theme.Dim.Render(wrapText(t.context, innerW))
	}
	return modalBox(body, outerW-2, col)
}

// renderToast splices the toast into the top-right corner of base.
func (m model) renderToast(base string) string {
	if m.toast == nil {
		return base
	}
	box := m.toastBox()
	fgLines := strings.Split(box, "\n")
	w := 0
	for _, l := range fgLines {
		w = max(w, ansi.StringWidth(l))
	}
	x := max(m.width-w, 0)
	bgLines := canvasLines(base, m.width, m.height)
	return placeCompose(bgLines, fgLines, x, 0)
}
