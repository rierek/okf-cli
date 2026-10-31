package theme

import (
	"math"
	"strconv"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

// accentColor is the colour for a chromatic #rrggbb tone under the terminal's colour profile. A
// 256- or 16-colour terminal gets the nearest colour of the 6x6x6 cube, never a grey: termenv's
// own conversion sends some saturated tones to the grey ramp (latte red #d20f39 becomes #080808).
// Truecolor and Ascii keep the hex value. Neutral tones (text, overlay, base, surface) skip this
// and may map to grey.
func accentColor(hex string) lipgloss.Color {
	switch lipgloss.ColorProfile() {
	case termenv.ANSI256, termenv.ANSI:
		if i, ok := cubeIndex(hex); ok {
			return lipgloss.Color(strconv.Itoa(i))
		}
	}
	return lipgloss.Color(hex)
}

// cubeLevels are the channel values of the xterm 6x6x6 cube (indices 16..231).
var cubeLevels = [6]int{0, 95, 135, 175, 215, 255}

// cubeIndex returns the cube index nearest to hex, or false for a malformed value.
func cubeIndex(hex string) (int, bool) {
	if !HexColor.MatchString(hex) {
		return 0, false
	}
	v, _ := strconv.ParseUint(hex[1:], 16, 32)
	r, g, b := int(v>>16&0xff), int(v>>8&0xff), int(v&0xff)
	// Nearest cube colour by weighted RGB distance, never a grey: a grey candidate would lose the hue.
	best, bestD := 0, math.MaxFloat64
	for ri, rl := range cubeLevels {
		for gi, gl := range cubeLevels {
			for bi, bl := range cubeLevels {
				if ri == gi && gi == bi {
					continue
				}
				dr, dg, db := float64(r-rl), float64(g-gl), float64(b-bl)
				if d := 2*dr*dr + 4*dg*dg + 3*db*db; d < bestD {
					best, bestD = 16+36*ri+6*gi+bi, d
				}
			}
		}
	}
	return best, true
}
