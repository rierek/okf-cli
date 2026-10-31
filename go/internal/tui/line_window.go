// Copied from lif internal/tui/view_browse_repo.go (windowStart, windowAround) at commit 2056715.
// Not copied from lif's line_window.go: its block windowing serves wrapped list rows, and every
// row here is one line.

package tui

// windowStart computes the window start index so cursor stays visible: centered when there is
// room, clamped at both edges. Deterministic in (n, height, cursor) alone, so it never jitters.
func windowStart(n, height, cursor int) int {
	if height <= 0 || n <= height {
		return 0
	}
	start := cursor - height/2
	if start < 0 {
		start = 0
	}
	if start+height > n {
		start = n - height
	}
	return start
}

// windowAround windows rows to height entries so the cursor stays visible. A no-op when
// everything already fits.
func windowAround(rows []string, height, cursor int) []string {
	if height <= 0 || len(rows) <= height {
		return rows
	}
	start := windowStart(len(rows), height, cursor)
	return rows[start : start+height]
}
