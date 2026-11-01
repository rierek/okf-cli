package theme

import (
	"math"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

func hsv(t *testing.T, c termenv.Color) (h, s float64) {
	t.Helper()
	h, s, _ = termenv.ConvertToRGB(c).Hsv()
	return h, s
}

func hueDiff(a, b float64) float64 {
	d := math.Abs(a - b)
	return math.Min(d, 360-d)
}

// Under a 256-colour profile every chromatic tone of every flavour keeps its hue family and is
// never a grey; latte red stays red (termenv alone maps it to #080808).
func TestChromaticTonesKeepHueOn256Colours(t *testing.T) {
	defer Apply(palettes["mocha"]) // runs last, under the restored profile
	defer lipgloss.SetColorProfile(termenv.Ascii)
	lipgloss.SetColorProfile(termenv.ANSI256)

	for _, name := range Names {
		p := palettes[name]
		Apply(p)
		for tone, got := range map[string]lipgloss.Color{
			"rosewater": Rosewater, "flamingo": Flamingo, "pink": Pink, "mauve": Mauve, "red": Red,
			"maroon": Maroon, "peach": Peach, "yellow": Yellow, "green": Green, "teal": Teal,
			"sky": Sky, "sapphire": Sapphire, "blue": Blue, "lavender": Lavender,
		} {
			want := termenv.TrueColor.Color(p.Hex(tone))
			wantH, wantS := hsv(t, want)
			gotC := termenv.ANSI256.Color(string(got))
			gotH, gotS := hsv(t, gotC)
			if gotS < 0.1 {
				t.Errorf("%s %s: %s maps to grey %v", name, tone, p.Hex(tone), gotC)
			}
			if wantS >= 0.25 && hueDiff(wantH, gotH) > 30 {
				t.Errorf("%s %s: %s hue %.0f maps to hue %.0f (%v)", name, tone, p.Hex(tone), wantH, gotH, gotC)
			}
		}
	}

	Apply(palettes["latte"])
	rgb := termenv.ConvertToRGB(termenv.ANSI256.Color(string(Red)))
	if !(rgb.R > 0.6 && rgb.G < 0.3 && rgb.B < 0.4) {
		t.Errorf("latte red on 256 colours = %v, want red", rgb.Hex())
	}
}

// Truecolor keeps the palette value.
func TestTruecolorKeepsHex(t *testing.T) {
	defer Apply(palettes["mocha"]) // runs last, under the restored profile
	defer lipgloss.SetColorProfile(termenv.Ascii)
	lipgloss.SetColorProfile(termenv.TrueColor)
	Apply(palettes["latte"])
	if Red != lipgloss.Color("#d20f39") {
		t.Errorf("latte red = %v, want #d20f39", Red)
	}
}
