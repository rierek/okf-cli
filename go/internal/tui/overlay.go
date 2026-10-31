// Copied from lif internal/tui/overlay.go at commit 2056715, adapted: no placeOverlayAt (copied
// when a dropdown needs it).

package tui

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// overlayPad is the background fill for narrow modal lines. Every modal box uses theme.Base as
// background, so the padding carries the same colour.
func overlayPad() lipgloss.Style { return lipgloss.NewStyle().Background(theme.Base) }

// canvasLines normalizes bg into a gapless tw×th rectangle with theme.Base background: every cell
// the overlay does not cover itself is then Base instead of the terminal default.
func canvasLines(bg string, tw, th int) []string {
	lines := strings.Split(bg, "\n")
	if tw <= 0 {
		return lines // width unknown (init, tests): leave bg unchanged
	}
	n := len(lines)
	if th > n {
		n = th
	}
	out := make([]string, 0, n)
	for i := range n {
		var l string
		if i < len(lines) {
			l = lines[i]
		}
		if pad := tw - ansi.StringWidth(l); pad > 0 {
			l += overlayPad().Render(strings.Repeat(" ", pad))
		}
		out = append(out, l)
	}
	return out
}

// placeOverlay places fg centered over bg (painter's algorithm, ANSI safe). bg stays visible all
// around; only the cells the modal occupies are overwritten.
func placeOverlay(bg, fg string, tw, th int) string {
	bgLines := canvasLines(bg, tw, th)
	fgLines := strings.Split(fg, "\n")

	fgW := 0
	for _, l := range fgLines {
		if w := ansi.StringWidth(l); w > fgW {
			fgW = w
		}
	}
	fgH := len(fgLines)

	bgW := tw
	if bgW <= 0 {
		for _, l := range bgLines {
			if w := ansi.StringWidth(l); w > bgW {
				bgW = w
			}
		}
	}

	x := max((bgW-fgW)/2, 0)
	y := max((len(bgLines)-fgH)/2, 0)
	return placeCompose(bgLines, fgLines, x, y)
}

// placeCompose overlays fgLines onto bgLines at (x, y), padding every fg line to the width of the
// widest one: the overlay is a gapless rectangle and nothing behind it bleeds through. fg rows
// outside bgLines are skipped.
func placeCompose(bgLines, fgLines []string, x, y int) string {
	x = max(x, 0)
	fgW := 0
	for _, l := range fgLines {
		if w := ansi.StringWidth(l); w > fgW {
			fgW = w
		}
	}
	for i, fl := range fgLines {
		row := y + i
		if row < 0 || row >= len(bgLines) {
			continue
		}
		if pad := fgW - ansi.StringWidth(fl); pad > 0 {
			fl += overlayPad().Render(strings.Repeat(" ", pad))
		}
		bgLines[row] = spliceLine(bgLines[row], fl, x, fgW)
	}
	return strings.Join(bgLines, "\n")
}

// spliceLine replaces cells [x, x+fgW) of bg with fg (ANSI safe).
func spliceLine(bg, fg string, x, fgW int) string {
	left := ansi.Truncate(bg, x, "")
	if lw := ansi.StringWidth(left); lw < x {
		left += strings.Repeat(" ", x-lw)
	}
	right := ansi.TruncateLeft(bg, x+fgW, "")
	return left + "\x1b[0m" + fg + "\x1b[0m" + right
}
