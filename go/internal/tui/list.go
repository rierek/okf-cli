// Copied from lif internal/tui/list.go at commit d0cd455.

package tui

// listState is a minimal cursor over a list of a given length.
type listState struct {
	length int
	cursor int
}

// setLen updates the list length and clamps the cursor into [0, n).
func (l *listState) setLen(n int) {
	l.length = n
	if l.cursor >= n {
		l.cursor = n - 1
	}
	if l.cursor < 0 {
		l.cursor = 0
	}
}

// move shifts the cursor by d, clamped to the list bounds.
func (l *listState) move(d int) {
	if l.length == 0 {
		l.cursor = 0
		return
	}
	l.cursor = min(max(l.cursor+d, 0), l.length-1)
}
